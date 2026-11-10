"""Magicbricks transport: plain curl_cffi with browser-impersonated TLS. No
browser, no cookies, no token. Egress: the pod's own IP first
(config.MAGICBRICKS_EXIT, knob in config's "--- magicbricks ---" block);
Akamai refuses US datacenter proxy exits with
"Access Denied" on every surface while Indian residential exits pass all
of them (pod probe 2026-11-07, scrapers-patchright-depl-74fddd498d-rfmk6),
so a block or a 5xx on the own IP drops the session and the retry rides a
sticky Indian residential exit for MAGICBRICKS_BLOCK_HOLD_S seconds.

Upstream surfaces (research 2026-11-07, all open to curl_cffi chrome):

  * SEARCH   GET /mbsrp/propertySearch.html?category=S|R&cityName=..&page=N
             -> JSON {resultList[30], editAdditionalDataBean{resultCount,
             pageCount, searchSummary, cityName, localityNames}}. Readable
             site-URL params (proptype=, bedroom=, Locality=) and coded
             ones (budgetMin/Max, areaFrom/To, furnished, possessionStatus,
             sortBy, keyword, psmid, oid, locality) both apply. Pages 1-100
             are real; 101+ repeat page 1. An unknown city answers 200 with
             cityName.value null.
  * PROPERTY GET /propertyDetails/x&id=<hex> -> HTML whose
             window.SERVER_PRELOADED_STATE_DETAILS holds the record (1.5 MB).
             An unknown id answers 200 with a search page (no DETAILS
             global) -> NotFound.
  * PROJECT  GET /x-pdpid-<hex> (slug ignored) -> HTML with
             window.SERVER_PRELOADED_STATE_.projectDetailData; unknown 404.
  * RERA     GET /<project-slug>-rera-details-nprid-<hex> (the slug is
             required: the project page's reraUrl) -> state newReraPageData.
  * PROJECTS GET /new-projects-<City>[/page-N], /new-projects-<Locality>-in-<City>
             -> state searchResult[20] + totalCount; an unknown city serves
             the generic /magichomes page (reqUrl) -> NotFound.
  * AGENTS   GET /mbsearch/fetchTopAgentByCityOrLocality?city=|locality=&category=
             -> HTML fragment of agent cards (no paging, ~100 cards).
  * SUGGEST  GET /mbutility/homepageAutoSuggest?searchtxt=&city= -> JSON.
  * TRENDS   POST /mbutility/trends/trendsdata + /tableData.html, JSON body
             {locality, saleRent, propType, otherLocs, maxYear} -> JSON
             series / HTML table; an unknown locality answers an empty body.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  MagicbricksUpstreamError  transport failure / 5xx            — retryable
  MagicbricksBlocked        403 / 429 / Akamai "Access Denied"  — retryable
  MagicbricksBadRequest     upstream 400 on a search            — never retried
  MagicbricksNotFound       404 / unknown id / unknown place    — never retried
"""
import json
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from magicbricks.refs import SITE, encode_id, projects_list_path

IMPERSONATE = "chrome"
PAGE_TIMEOUT = 40      # property pages are ~2.6 MB
JSON_TIMEOUT = 25

PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "upgrade-insecure-requests": "1",
}
JSON_HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "referer": SITE + "/",
}
FRAGMENT_HEADERS = {
    "accept": "text/html, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "referer": SITE + "/",
}

_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I | re.S)
_ACCESS_DENIED_RE = re.compile(r"<title>\s*Access Denied\s*</title>", re.I)
MISSING_TITLE = "Oops... Something is missing"


class MagicbricksUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class MagicbricksBlocked(MagicbricksUpstreamError, Blocked):
    """403 / 429 / Akamai 'Access Denied' — retryable on a fresh exit."""


class MagicbricksBadRequest(BadRequest):
    """Upstream 400 on a search — never retried."""


class MagicbricksNotFound(NotFound):
    """Unknown listing / project / place — never retried."""


# ---- sessions ------------------------------------------------------------------------
# One curl session per cheroot worker thread and per tier; a curl handle is
# never shared across threads. The thread remembers a block on the primary
# tier (block_until) so its next sessions ride the fallback residential
# exit for MAGICBRICKS_BLOCK_HOLD_S seconds.
_local = threading.local()


def _tier():
    until = getattr(_local, "block_until", 0)
    if until and time.monotonic() < until:
        return "fallback"
    return "primary"


def _session():
    tier = _tier()
    sessions = getattr(_local, "sessions", None)
    if sessions is None:
        sessions = _local.sessions = {}
    sess = sessions.get(tier)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.magicbricks_fallback_proxy() if tier == "fallback" else config.magicbricks_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        # the language of the exit the session leaves through, never a literal
        sess.headers["accept-language"] = egress.accept_language(proxy)
        sessions[tier] = sess
    return sess


def _drop_session(blocked=False):
    """Close the thread's current session so a poisoned keep-alive
    connection (and its exit) dies; a block on the primary tier moves the
    thread to the fallback exit for the hold window."""
    tier = _tier()
    sessions = getattr(_local, "sessions", None) or {}
    sess = sessions.pop(tier, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass
    if blocked and tier == "primary" and config.MAGICBRICKS_BLOCK_HOLD_S:
        _local.block_until = time.monotonic() + config.MAGICBRICKS_BLOCK_HOLD_S


def _retrying(fn):
    """Run fn() under the shared retry policy (MagicbricksUpstreamError
    only; NotFound / BadRequest surface at once). Every retryable failure
    drops the session so the retry rides a fresh exit; a block (or a 5xx,
    which the own IP draws on some pages that residential serves) also
    moves the thread to the fallback exit."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except MagicbricksUpstreamError as e:
            last = e
            _drop_session(blocked=True)
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _page_title(text):
    match = _TITLE_RE.search(text or "")
    return " ".join(match.group(1).split()) if match else ""


def _classify(resp, label):
    """HTTP status -> error taxonomy; returns the body text on 200."""
    text = resp.text
    if resp.status_code == 404:
        raise MagicbricksNotFound(f"{label} not found")
    if resp.status_code in (401, 403, 429) or _ACCESS_DENIED_RE.search(text[:600]):
        raise MagicbricksBlocked(f"HTTP {resp.status_code} for {label}")
    if resp.status_code == 400:
        # the site's own "Oops" page on a malformed slug / id is a 400
        if MISSING_TITLE in text[:3000]:
            raise MagicbricksNotFound(f"{label} not found")
        raise MagicbricksBadRequest(f"upstream rejected {label}")
    if resp.status_code != 200:
        raise MagicbricksUpstreamError(f"HTTP {resp.status_code} for {label}")
    return text


def _get(path, headers, label, timeout, params=None):
    def once():
        try:
            resp = _session().get(SITE + path, params=params, headers=headers, timeout=timeout)
        except Exception as e:
            raise MagicbricksUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _classify(resp, label)
    return _retrying(once)


def _post_json(path, body, headers, label, timeout):
    def once():
        try:
            resp = _session().post(SITE + path, json=body, headers=headers, timeout=timeout)
        except Exception as e:
            raise MagicbricksUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _classify(resp, label)
    return _retrying(once)


def _json(text, label):
    try:
        return json.loads(text)
    except ValueError:
        raise MagicbricksBlocked(f"non-JSON {label} response: {text[:120]!r}")


# ---- surfaces ------------------------------------------------------------------------

def fetch_search(params):
    """GET /mbsrp/propertySearch.html with the site's own query params ->
    the raw JSON dict (resultList + editAdditionalDataBean)."""
    try:
        text = _get("/mbsrp/propertySearch.html", JSON_HEADERS, "search", JSON_TIMEOUT, params=params)
    except MagicbricksNotFound:
        # a page past the end answers HTTP 404; the API reports an empty
        # page instead so paging clients stop cleanly
        if int(params.get("page") or 1) > 1:
            return None
        raise
    payload = _json(text, "search")
    if not isinstance(payload, dict) or "resultList" not in payload:
        raise MagicbricksUpstreamError(f"unexpected search payload shape: {text[:120]!r}")
    return payload


def fetch_property(property_id):
    """GET the listing page (the slug is ignored upstream). A 200 without the
    DETAILS state is the site's search-page fallback for an unknown id."""
    path = f"/propertyDetails/property&id={encode_id(property_id)}"
    html = _get(path, PAGE_HEADERS, f"property {property_id}", PAGE_TIMEOUT)
    if "SERVER_PRELOADED_STATE_DETAILS" not in html:
        raise MagicbricksNotFound(f"property {property_id} not found")
    return html


def fetch_project(psmid):
    """GET the project page by hex id (slug ignored); unknown ids are 404."""
    path = f"/project-pdpid-{encode_id(psmid)}"
    html = _get(path, PAGE_HEADERS, f"project {psmid}", PAGE_TIMEOUT)
    if "projectDetailData" not in html:
        raise MagicbricksNotFound(f"project {psmid} not found")
    return html


def fetch_rera(rera_slug, psmid):
    """GET the project's RERA page by the slug the project page publishes."""
    html = _get("/" + rera_slug.lstrip("/"), PAGE_HEADERS, f"RERA page of project {psmid}", PAGE_TIMEOUT)
    if "newReraPageData" not in html:
        raise MagicbricksNotFound(f"RERA page of project {psmid} not found")
    return html


def fetch_projects_list(city, locality=None, page=1):
    """GET one /new-projects-* directory page (20 projects)."""
    path = projects_list_path(city, locality, page)
    return _get(path, PAGE_HEADERS, f"projects in {locality + ', ' if locality else ''}{city}", PAGE_TIMEOUT)


def fetch_agents(category, city=None, locality=None):
    """GET the top-agents fragment for a city code or a locality id."""
    params = {"category": category}
    if locality:
        params["locality"] = locality
    else:
        params["city"] = city
    return _get("/mbsearch/fetchTopAgentByCityOrLocality", FRAGMENT_HEADERS, "agents", PAGE_TIMEOUT,
                params=params)


def fetch_autosuggest(text, city=None):
    """GET the place / project autosuggest -> {locationMap, landmarkMap}."""
    params = {"searchtxt": text}
    if city:
        params["city"] = city
    text = _get("/mbutility/homepageAutoSuggest", JSON_HEADERS, "autosuggest", JSON_TIMEOUT, params=params)
    payload = _json(text, "autosuggest")
    if not isinstance(payload, dict):
        raise MagicbricksUpstreamError("unexpected autosuggest payload shape")
    return payload


def _trends_body(locality_id, sale_rent, prop_type, years):
    return {"locality": str(locality_id), "saleRent": sale_rent, "propType": prop_type,
            "otherLocs": [], "maxYear": years}


def fetch_trends(locality_id, sale_rent, prop_type, years=5):
    """POST /mbutility/trends/trendsdata -> {labels, datasets} (None when
    the locality is unknown: the site answers an empty body)."""
    text = _post_json("/mbutility/trends/trendsdata", _trends_body(locality_id, sale_rent, prop_type, years),
                      JSON_HEADERS, "trends", JSON_TIMEOUT)
    if not text.strip():
        return None
    payload = _json(text, "trends")
    return payload if isinstance(payload, dict) else None


def fetch_trends_table(locality_id, sale_rent, prop_type, years=5):
    """POST /mbutility/trends/tableData.html -> the HTML tables (quarterly
    and yearly ₹/sqft with the change %)."""
    return _post_json("/mbutility/trends/tableData.html", _trends_body(locality_id, sale_rent, prop_type, years),
                      FRAGMENT_HEADERS, "trends table", JSON_TIMEOUT)
