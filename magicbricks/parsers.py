"""Raw magicbricks.com JSON / HTML -> clean dicts for every /magicbricks/*
endpoint. Pure functions, no I/O.

Where the data lives (research 2026-11-07):
  * search          the /mbsrp/propertySearch.html JSON (one row per listing,
                    ~200 keys; the readable ones end in "D": priceD, bathD)
  * property page   window.SERVER_PRELOADED_STATE_DETAILS (detailBean with
                    164 keys, projectViewBean, the 12-month price trend,
                    nearby places, similar listings)
  * project page    window.SERVER_PRELOADED_STATE_.projectDetailData +
                    projectPageSeoStaticData (reviews, floor plans, trends,
                    locality profile, FAQs, similar projects)
  * RERA page       window.SERVER_PRELOADED_STATE_.newReraPageData / reraData
  * projects list   window.SERVER_PRELOADED_STATE_.searchResult[20]
  * agents          an HTML fragment of .prefagent cards
  * autosuggest     {locationMap{LOCATION, PROJECT}, landmarkMap{category: []}}
  * trends          {labels[], datasets[{label, data[]}]} + an HTML table

Value conventions (shared with the other scraper packages):
  * prices   numeric INR + a `currency` field; the site's own display text
             ("6.76 Cr") kept as `display`
  * dates    ISO: "Nov 06, '2026" -> "2026-11-06"; "Mar '27" -> "2027-03";
             "20270301" -> "2027-03-01"; "27/10/2026" -> "2026-10-27"
  * flags    'Y' / 'N' -> true / false, questions as booleans (is_verified)
  * masks    "", "NA", "null", "-" and the site's masked phone -> null
  * keys     snake_case; `link` not `url`

Fixtures captured 2026-11-07 (magicbricks/fixtures/): a sale listing in a
project (Juhu, Mumbai), a rent listing (Hebbal, Bangalore), a commercial
office listing, the search-page fallback an unknown id serves, a project
page, two /new-projects-Mumbai pages, a RERA page, the Mumbai top-agents
fragment, two autosuggest payloads, a trends series + table, four search
payloads (sale / rent / commercial / empty).
"""
import html as html_lib
from collections import Counter
import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from magicbricks.refs import (
    AMENITIES, LANDMARK_CATEGORIES, SITE, TRENDS_PROPERTY_TYPES, agent_link, decode_id, project_link,
    property_link, rera_link, site_link,
)

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MASKS = {"", "-", "na", "n/a", "null", "none", "undefined"}
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_MASKED_PHONE_RE = re.compile(r"X{3,}", re.I)
_RERA_IMG = "https://img.staticmb.com/mbimages/reradoc/"
_PROJECT_IMG = "https://img.staticmb.com/mbimages/project/"


# ---- primitives ----------------------------------------------------------------------

def clean(value):
    """Collapse whitespace; placeholder masks -> None; non-strings pass."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = " ".join(str(value).split())
    return None if text.lower() in _MASKS else text


def to_int(value):
    value = clean(value)
    if value is None or value is False or value is True:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = _NUMBER_RE.search(value)
    if not match:
        return None
    try:
        return int(float(match.group(0).replace(",", "")))
    except ValueError:
        return None


def to_float(value):
    value = clean(value)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUMBER_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def positive(value):
    """A numeric field where the site writes 0 for 'unknown'."""
    number = to_float(value)
    return number if number and number > 0 else None


def yn(value):
    """'Y' / 'N' / 'true' / 'false' -> bool; anything else -> None."""
    if isinstance(value, bool):
        return value
    text = clean(value)
    if text is None:
        return None
    text = text.lower()
    if text in ("y", "yes", "true", "1"):
        return True
    if text in ("n", "no", "false", "0"):
        return False
    return None


def iso_date(value):
    """The site's date spellings -> ISO date / month / datetime (UTC)."""
    text = clean(value)
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return _epoch(text)
    # 2026-11-06T17:38:09.000Z / 2026-10-31T08:01:58.000+00:00
    match = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", text)
    if match:
        date_part, time_part, zone = match.groups()
        if zone and zone != "Z" and zone.replace(":", "") not in ("+0000", "-0000"):
            try:
                stamp = datetime.fromisoformat(f"{date_part}T{time_part}{zone}")
                return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass
        return f"{date_part}T{time_part}Z"
    # 2027-03-01 00:00:00
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?: \d{2}:\d{2}:\d{2})?$", text)
    if match:
        return match.group(1)
    # 20270301
    match = re.match(r"^(\d{4})(\d{2})(\d{2})$", text)
    if match:
        return "-".join(match.groups())
    # 27/10/2026
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    # 03/2027 (RERA validity)
    match = re.match(r"^(\d{1,2})/(\d{4})$", text)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}"
    # Nov 06, '2026 / Nov 06, '26 / 05 Nov 26 / 07 November 2026
    match = re.match(r"^([A-Za-z]{3,9})\.? (\d{1,2}),? '?(\d{2,4})$", text)
    if not match:
        swapped = re.match(r"^(\d{1,2}) ([A-Za-z]{3,9}),? '?(\d{2,4})$", text)
        if swapped:
            match = (swapped.group(2), swapped.group(1), swapped.group(3))
    else:
        match = match.groups()
    if match:
        month_name, day, year = match
        month = _MONTHS.get(month_name.lower()[:3])
        if month:
            return f"{_year(year)}-{month:02d}-{int(day):02d}"
    # Mar '27 / Mar 2027 / Mar, 2027 / Oct-26 / Oct'26
    match = re.match(r"^([A-Za-z]{3,9}),?[ '-]+'?(\d{2,4})$", text)
    if match:
        month = _MONTHS.get(match.group(1).lower()[:3])
        if month:
            return f"{_year(match.group(2))}-{month:02d}"
    return None


def _year(value):
    return f"20{value}" if len(value) == 2 else value


def _epoch(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1e11:   # milliseconds
        number /= 1000.0
    try:
        return datetime.fromtimestamp(number, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def extract_state(html, key):
    """`window.<key> = {...};` -> dict (JSON object parsed in place), else None."""
    if not html:
        return None
    match = re.search(r"window\." + re.escape(key) + r"\s*=\s*", html)
    if not match:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(html, match.end())
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def snake(key):
    """'constQuality' / 'Public Transport' / 'Places of Interest' ->
    'const_quality' / 'public_transport' / 'places_of_interest'."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key))
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()


# The site's rating keys -> public names (ratingBean "<x>Rt" keys of a
# project; localityDetailDTO "<x>Rating" keys + three bare ones).
_PROJECT_RATINGS = {
    "water": "water", "electricity": "electricity", "backup": "power_backup", "sewage": "sewage",
    "sports": "sports", "parking": "parking", "garden": "gardens", "shops": "shops",
    "constQuality": "construction_quality", "maintenance": "maintenance", "staff": "staff",
    "security": "security", "prjMaintainance": "project_maintenance", "prjInfra": "project_infrastructure",
    "prjAmenity": "project_amenities",
}
_LOCALITY_RATINGS = {
    "road": "roads", "neighbour": "neighbourhood", "safety": "safety", "clean": "cleanliness",
    "transport": "public_transport", "parking": "parking", "connectivity": "connectivity",
    "traffic": "traffic", "school": "schools", "restuarant": "restaurants", "restaurant": "restaurants",
    "hospital": "hospitals", "market": "markets", "environment": "environment", "commuting": "commuting",
    "placeOfInterest": "places_of_interest",
}


def _project_ratings(source, skip=("psmAvg",)):
    """{'<x>Rt': value} -> {public name: float} (None when nothing rated)."""
    out = {}
    for key, value in (source or {}).items():
        if not key.endswith("Rt") or key[:-2] in skip or to_float(value) is None:
            continue
        name = key[:-2]
        out[_PROJECT_RATINGS.get(name, snake(name))] = to_float(value)
    return out or None


def _rich_text(value):
    """User-written text that may carry <br> / tags / entities -> plain
    text, line breaks kept as \\n, spaces collapsed per line."""
    if value is None:
        return None
    text = re.sub(r"<br\s*/?>|</p\s*>", "\n", str(value), flags=re.I)
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = [" ".join(line.split()) for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    return text if clean(text) else None


def _range_display(value):
    """Project cards join a price range with a comma ('60.6 Lac,1.20 Cr'); the project
    page writes '10.12 Cr - 12.50 Cr' -> the page's form. 'Call For Price' passes."""
    text = clean(value)
    if not isinstance(text, str):
        return text
    return re.sub(r"^([\d.]+ (?:Lac|Cr)),\s*([\d.]+ (?:Lac|Cr))$", r"\1 - \2", text)


def _month(*values):
    """Launch / possession dates are months on the site ('Jun, 2021', '20180601',
    '2022-12-01 00:00:00' - the day is always a filler 01) -> 'YYYY-MM' from the first
    value that reads as a date."""
    for value in values:
        iso = iso_date(value)
        if isinstance(iso, str) and re.match(r"^\d{4}-\d{2}", iso):
            return iso[:7]
    return None


def _booking_or_deposit(listing_type, *amounts):
    """The site keeps a rental's security deposit in the booking-amount field (the rent page
    labels the same figure 'Security Deposit'; priceBreakUp.securityDeposit repeats it) ->
    {booking_amount, security_deposit}, the first positive amount going to the one that applies."""
    amount = next((to_int(a) for a in (positive(x) for x in amounts) if a), None)
    if listing_type == "rent":
        return {"booking_amount": None, "security_deposit": amount}
    return {"booking_amount": amount, "security_deposit": None}


def _facing(value):
    """'North - East' / 'South -West' (the site spaces them either way) -> 'North-East'."""
    text = clean(value)
    return re.sub(r"\s*-\s*", "-", text) if isinstance(text, str) else text


def _maintenance(amount, frequency):
    """maintenanceCharges + its frequency ('Monthly', 'Quarterly', 'Per sq.
    Unit Monthly', ...) -> {amount, currency, period, is_per_sqft}. The
    amount is the lister's own figure, shown as-is by the site."""
    amount = positive(amount)
    if not amount:
        return None
    text = (clean(frequency) or "").lower()
    period = None
    for word, value in (("month", "monthly"), ("quarter", "quarterly"), ("annual", "yearly"),
                        ("year", "yearly"), ("one", "one-time")):
        if word in text:
            period = value
            break
    return {"amount": int(amount) if float(amount).is_integer() else round(amount, 2), "currency": "INR",
            "period": period, "is_per_sqft": "per sq" in text}


def _strip_html(value):
    """Rich-text blobs (project description, developer about) -> plain text;
    block tags become sentence breaks so a <table> row reads as a line."""
    text = clean(value)
    if not text:
        return None
    text = re.sub(r"</(?:p|div|li|tr|h\d|br)\s*>|<br\s*/?>", " | ", text, flags=re.I)
    text = re.sub(r"</t[dh]\s*>", ": ", text, flags=re.I)
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text))     # &nbsp; / &amp; after the tags go
    text = re.sub(r"\s*\|\s*(\|\s*)+", " | ", text)
    text = re.sub(r"(?:\s*:\s*)+\|", " |", text)
    return clean(text.strip(" |:")) or None


def page_title(html):
    match = re.search(r"<title>(.*?)</title>", html or "", re.I | re.S)
    return " ".join(match.group(1).split()) if match else None


def _ld_json(html):
    out = []
    for match in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html or "", re.S):
        try:
            out.append(json.loads(match.group(1)))
        except ValueError:
            continue
    return out


def _price(amount, display=None, per_sqft=None):
    amount = positive(amount)
    out = {"amount": int(amount) if amount is not None else None,
           "currency": "INR" if amount is not None else None,
           "display": clean(display) if amount is not None or clean(display) else None}
    if per_sqft is not None:
        out["per_sqft"] = positive(per_sqft)
    return out


def _area(value, unit):
    number = positive(value)
    if number is None:
        return None
    return {"value": number, "unit": _unit(unit)}


def _unit(unit):
    text = clean(unit)
    if not text:
        return "sqft"
    text = text.lower().replace("-", "").replace(".", "").replace(" ", "")
    return {"sqft": "sqft", "sqm": "sqm", "sqyrd": "sqyrd", "acre": "acre", "hectare": "hectare",
            "cent": "cent", "ground": "ground", "guntha": "guntha", "bigha": "bigha",
            "kanal": "kanal", "marla": "marla", "biswa": "biswa", "ares": "ares"}.get(text, text)


def _latlng(text):
    text = clean(text)
    if not text or "," not in text:
        return None, None
    lat, lng = text.split(",", 1)
    return to_float(lat), to_float(lng)


def _coords(lat, lng, fallback_text=None):
    lat, lng = positive(lat), positive(lng)
    if lat is None or lng is None:
        lat, lng = _latlng(fallback_text)
    return lat, lng


_AMENITY_IDS_BY_NAME = {}
for _id, _name in AMENITIES.items():
    _AMENITY_IDS_BY_NAME.setdefault(_name.lower(), []).append(_id)


def _amenities(ids_text, *maps):
    """'12201 12202' + the row's own id->name maps -> [{id, name}]."""
    names = {}
    for mapping in maps:
        if isinstance(mapping, dict):
            names.update({str(k): clean(v) for k, v in mapping.items() if clean(v)})
    ids = []
    if isinstance(ids_text, list):
        ids = [str(i) for i in ids_text if clean(i)]
    elif clean(ids_text):
        ids = str(ids_text).split()
    out, seen = [], set()
    for amenity_id in ids:
        if amenity_id in seen:
            continue
        seen.add(amenity_id)
        out.append({"id": amenity_id, "name": names.get(amenity_id) or AMENITIES.get(amenity_id)})
    return out


def _landmarks(items):
    """'19210|Juhu Beach Bus Stop||160529|19250' -> {category, name, id}."""
    out = []
    for item in items or []:
        parts = str(item).split("|")
        if len(parts) < 2 or not clean(parts[1]):
            continue
        out.append({"id": clean(parts[3]) if len(parts) > 3 else None,
                    "name": clean(parts[1]),
                    "category": LANDMARK_CATEGORIES.get(clean(parts[0]) or ""),
                    "distance_km": to_float(parts[2]) if len(parts) > 2 else None})
    return out


def _rera(text):
    """'NA|null,P51800046724|-1' -> [registration ids]; masks dropped."""
    out = []
    for chunk in str(text or "").replace("[", "").replace("]", "").split(","):
        rera_id = clean(chunk.split("|")[0])
        if rera_id and rera_id.lower() not in ("na", "null"):
            out.append(rera_id)
    return out


def _listing_type(value):
    text = (clean(value) or "").lower()
    if text in ("s", "sale", "b", "buy"):
        return "sale"
    if text in ("r", "rent"):
        return "rent"
    return None


def _furnishing(value):
    text = clean(value)
    return text.lower().replace(" ", "-") if text else None


# ---- search -------------------------------------------------------------------------------

def parse_search_row(row):
    """One /mbsrp/propertySearch.html result -> the public listing card."""
    row = row or {}
    property_id = clean(row.get("id"))
    lat, lng = _coords(row.get("pmtLat"), row.get("pmtLong"), row.get("ltcoordGeo"))
    listing_type = _listing_type(row.get("transType")) or _listing_type(row.get("cg"))
    cover = clean(row.get("image")) or clean(row.get("psmImage"))
    images = [clean(i) for i in (row.get("allImgPath") or []) if clean(i)]
    project_id = clean(row.get("psmid"))
    project_slug = clean(row.get("projectSocietyLink"))
    return {
        "id": property_id,
        "link": property_link(property_id, clean(row.get("url")).split("&id=")[0] if clean(row.get("url")) else None)
                if property_id else None,
        "title": clean(row.get("propertyTitle")),
        "listing_type": listing_type,
        "property_type": clean(row.get("propTypeD")),
        "transaction_type": clean(row.get("transactionTypeD")),
        "description": _rich_text(row.get("dtldesc")) or clean(row.get("seoDesc")),
        "price": {
            **_price(row.get("price"), row.get("priceD"), row.get("sqFtPrice")),
            "maintenance": _maintenance(row.get("maintenanceCharges"), row.get("maintenanceD")),
            **_booking_or_deposit(listing_type, row.get("bookingAmtExact")),
        },
        "bedrooms": to_int(row.get("bedroomD")),
        "bathrooms": to_int(row.get("bathD")),
        "balconies": to_int(row.get("balconiesD")),
        "area": {
            "carpet": _area(row.get("carpetArea"), row.get("carpAreaUnit")),
            "covered": _area(row.get("coveredArea"), row.get("coverAreaUnitD")),
        },
        "furnishing": _furnishing(row.get("furnishedD")),
        "floor": {"number": to_int(row.get("floorNo")), "total": to_int(row.get("floors")),
                  "display": clean(row.get("floorD"))},
        "facing": _facing(row.get("facingD")),
        "overlooking": clean(row.get("amenFacingD")),
        "possession": {"status": clean(row.get("possStatusD")),
                       "available_from": iso_date(row.get("availableFrom")) or clean(row.get("availableFrom"))},
        "age": clean(row.get("acD")),
        "ownership": clean(row.get("OwnershipTypeD")),
        "parking": clean(row.get("parkingD")),
        "flooring": clean(row.get("flooringTyD")),
        "power_backup": clean(row.get("powerStatusD")),
        "water": clean(row.get("waterStatus")),
        "additional_rooms": clean(row.get("adroomD")),
        "tenant_preference": clean(row.get("tenantsPreference")),
        "location": {
            "locality": {"id": clean(row.get("lt")) and str(row.get("lt")), "name": clean(row.get("lmtDName"))},
            "city": {"id": clean(row.get("ct")), "name": clean(row.get("ctName"))},
            "landmark": clean(row.get("landmark")) or clean(row.get("ltOther")),
            "address": clean(row.get("psmAdd")) or clean(row.get("defaultAdddressGoogle")),
            "latitude": lat, "longitude": lng,
        },
        "project": {
            "id": project_id, "name": clean(row.get("prjname")),
            "link": site_link(project_slug) if project_slug else (project_link(project_id) if project_id else None),
            "developer": clean(row.get("devName")),
            "rera_ids": _rera(row.get("reraValidity")),
        } if project_id or clean(row.get("prjname")) else None,
        "amenities": _amenities(row.get("amenities"), row.get("nonluxAmenMap"), row.get("luxAmenMap")),
        "landmarks": _landmarks(row.get("landmarkDetails")),
        "lister": {
            "id": clean(row.get("oid")),
            "name": clean(row.get("oname")) or clean(row.get("contName")),
            "company": clean(row.get("companyname")),
            "type": clean(row.get("userType")),
            "operating_since": to_int(row.get("opSnD")),
            "is_rera_agent": yn(row.get("isReraAgent")),
            "rera_id": clean(row.get("agentReraState")),
            "rating": to_float(row.get("crisilStarRating")),
            "buyers_served": clean(row.get("agentContinuityStr")),
            "photo": clean(row.get("imgUrl")),
            "link": agent_link(clean(row.get("oid"))) if clean(row.get("oid")) and clean(row.get("userType")) != "Owner" else None,
        },
        "images": {"count": to_int(row.get("imgCt")) or to_int(row.get("allImgCt")), "cover": cover, "all": images},
        "is_verified": yn(row.get("ctVerifd")),
        "is_project_listing": yn(row.get("isProjProp")),
        "posted_on": iso_date(row.get("postDateT")),
        "posted_label": clean(row.get("postedLabelD")),
        "updated_on": iso_date(row.get("lCtDate")),
        "expires_on": iso_date(row.get("endDateT")),
    }


def parse_search(payload):
    """The search JSON -> {results, total_count, total_pages, summary, city,
    localities}. An unknown city leaves city.name null (the caller 404s)."""
    payload = payload or {}
    extra = payload.get("editAdditionalDataBean") or {}
    city = extra.get("cityName") if isinstance(extra.get("cityName"), dict) else {}
    localities = [{"id": clean(l.get("key")), "name": clean(l.get("value"))}
                  for l in (extra.get("localityNames") or []) if isinstance(l, dict)]
    return {
        "results": [parse_search_row(r) for r in (payload.get("resultList") or []) if isinstance(r, dict)],
        "total_count": to_int(extra.get("resultCount")) or 0,
        "total_pages": to_int(extra.get("pageCount")) or 0,
        "items_per_page": to_int(extra.get("resultPerPageCount")) or 30,
        "summary": clean(extra.get("searchSummary")),
        "city": {"id": clean(city.get("key")), "name": clean(city.get("value"))},
        "localities": localities,
        "project_count": to_int(extra.get("projectCount")),
    }


# ---- property page ------------------------------------------------------------------------

def _similar_row(row):
    row = row or {}
    property_id = clean(row.get("id"))
    if not property_id:
        decoded = decode_id((clean(row.get("url")) or "").split("&id=")[-1])
        property_id = decoded
    lat, lng = _latlng(row.get("ltcoordGeo"))
    return {
        "id": property_id,
        "link": property_link(property_id, (clean(row.get("url")) or "").split("&id=")[0] or None) if property_id else None,
        "title": clean(row.get("propertyTitle")) or clean(row.get("seoDesc")),
        "price": _price(row.get("price"), row.get("priceD")),
        "possession": clean(row.get("possStatusD")),
        "available_from": clean(row.get("availableFrom")),
        "floor": to_int(row.get("floorNo")),
        "developer": clean(row.get("devName")),
        "project_link": site_link(clean(row.get("projectSocietyLink"))),
        "image": clean(row.get("psmImage")) or (clean((row.get("propAllImg") or [None])[0]) if isinstance(row.get("propAllImg"), list) else None),
        "image_count": to_int(row.get("imgCt")),
        "latitude": lat, "longitude": lng,
        "posted_on": iso_date(row.get("postDateT")),
    }


def _nearby_places(factoids):
    out = []
    for group in factoids or []:
        if not isinstance(group, dict):
            continue
        category = clean(group.get("catDesc"))
        places = group.get("eachCategoryFactoidList")
        if isinstance(places, list) and places:
            for place in places:
                if not isinstance(place, dict):
                    continue
                out.append({"name": clean(place.get("name")), "category": category,
                            "distance_km": to_float(place.get("distanceFromProject")),
                            "latitude": to_float(place.get("latitude")),
                            "longitude": to_float(place.get("longitude"))})
        else:
            for name in group.get("name") or []:
                out.append({"name": clean(name), "category": category, "distance_km": None,
                            "latitude": None, "longitude": None})
    return [p for p in out if p["name"]]


def _price_trend(trend):
    """The 12-month ₹/sqft series of the locality and the project
    (priceTrendData: month labels + per-series data, numbers or
    {y, dataLabels} points)."""
    if not isinstance(trend, dict):
        return None
    months = [iso_date(m.strip().strip('"')) or m.strip().strip('"')
              for m in str(trend.get("monthYrAvgPriceStr") or "").split(",") if m.strip()]
    names = trend.get("localitiesDescMap") or {}
    series = []
    for key, raw in (trend.get("localitiesDataMap") or {}).items():
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        values = []
        for point in data.get("data") or []:
            values.append(to_float(point.get("y")) if isinstance(point, dict) else to_float(point))
        series.append({"id": str(key), "name": clean(data.get("name")), "kind": clean(names.get(key)),
                       "values": values})
    if not series:
        return None
    return {"unit": "INR per sqft", "months": months, "series": series,
            "last_month": iso_date(str(trend.get("lastMonth") or "").strip('"'))}


def _agent_block(bean):
    pdp = bean.get("agentDetailsPDP") if isinstance(bean.get("agentDetailsPDP"), dict) else {}
    details = bean.get("agentDetails") if isinstance(bean.get("agentDetails"), dict) else {}
    agent_id = clean(bean.get("agentId")) or clean(bean.get("propertyOwner"))
    lister_type = clean(bean.get("postedBy")) or clean(bean.get("agentType"))
    address = clean(bean.get("contactAddress"))
    return {
        "id": agent_id,
        "name": clean(bean.get("contactPersonName")) or clean(bean.get("oname")),
        "company": clean(bean.get("companyName")),
        "type": lister_type,
        "operating_since": to_int(bean.get("operatingSince")),
        "address": address.strip(" ,") if address else None,
        "phone": None,            # masked upstream ("85XXXXXXXX"); OTP contact form only
        "email": None,            # OTP contact form only
        "is_rera_agent": yn(bean.get("isReraAgent")),
        "rera_ids": [clean(x) for x in str(bean.get("agentReraIds") or "").split(",") if clean(x)],
        "rating": to_float(bean.get("crisilRating")),
        "quality_score": to_float(details.get("agentQulityScore")),
        "expertise": clean(details.get("expertiseIn")),
        "buyers_served": to_int(pdp.get("noOfBuyersServed")) or clean(bean.get("agentContinuityStr")),
        "verified_properties": to_int(pdp.get("noOfVerifiedProperties")),
        "sale_listings": to_int(bean.get("saleProperties")),
        "rent_listings": to_int(bean.get("rentProperties")),
        "commercial_listings": to_int(bean.get("commercialPropertyCount")),
        "rent_price_range": {"min": clean(pdp.get("rmin")), "max": clean(pdp.get("rmax"))} if clean(pdp.get("rmin")) else None,
        "sale_price_range": {"min": clean(pdp.get("smin")), "max": clean(pdp.get("smax"))} if clean(pdp.get("smin")) else None,
        "dealing_in": clean(pdp.get("dealingIn")),
        "operating_in": [clean(x) for x in (pdp.get("operatingIn") or []) if clean(x)],
        "link": clean(bean.get("agentBuildSeoUrl")) or (agent_link(agent_id) if agent_id and lister_type != "Owner" else None),
    }


def _project_view(view, bean):
    if not isinstance(view, dict) or not view:
        return None
    project_id = clean(view.get("projectId")) or clean(bean.get("propPsm"))
    slug = clean(bean.get("projectLink"))
    ratings = _project_ratings(view)
    return {
        "id": project_id,
        "name": clean(view.get("projectName")),
        "link": site_link(slug) if slug else (project_link(project_id) if project_id else None),
        "developer": clean(view.get("developerName")),
        "builder_link": site_link(clean(bean.get("builderUrl"))),
        "status": clean(view.get("possessionStatus")),
        "launched": _month(view.get("launchdate")) or clean(view.get("launchdate")),
        "possession_by": _month(view.get("possdate")),
        "total_units": to_int(view.get("totalUnits")),
        "towers": to_int(view.get("numberOfTowers")),
        "configurations": clean(view.get("projectUnits")) or clean(view.get("bhkConfig")),
        "price_range": clean(view.get("displayPrice")),
        "price_per_sqft_range": clean(view.get("displayPricePerSqft")),
        "brochure": clean(view.get("psmbrochurelink")),
        "approved_by_bank": clean(view.get("projectApprovedByBankName")),
        "image": clean(view.get("projectImage")),
        "is_premium": bool(view.get("isPremiumProject")),
        "rating": to_float(view.get("psmAvgRt")),
        "review_count": to_int(view.get("totalReview")),
        "ratings": ratings or None,
    }


def parse_property(html, property_id=None):
    """The listing page -> the full record (details + the similar lists)."""
    state = extract_state(html, "SERVER_PRELOADED_STATE_DETAILS") or {}
    info = state.get("propertyDetailInfoBeanData") or {}
    detail = info.get("propertyDetail") or {}
    bean = detail.get("detailBean") or {}
    extra = state.get("searchAdditionalDataBean") or {}
    property_id = clean(bean.get("propertyId")) or clean(info.get("propertyId")) or property_id
    listing_type = _listing_type(bean.get("saleOrRent")) or _listing_type(info.get("category"))
    # amenityMap holds the standard amenities; the luxury ones come as luxAmenities ids
    # named by luxuryAmenitiesList / luxuryAmenitiesMap (parallel id / name lists)
    lux_map = bean.get("luxuryAmenitiesMap") or {}
    lux_ids = lux_map.get("luxAmentiesIdList") or []
    lux_names = lux_map.get("luxAmentiesNameList") or []
    lux_pairs = dict(zip(lux_ids, lux_names)) if len(lux_ids) == len(lux_names) else {}
    lux_list = {a.get("amenRfnum"): a.get("name") for a in (bean.get("luxuryAmenitiesList") or [])
                if isinstance(a, dict)}
    amenity_ids = list((bean.get("amenityMap") or {}).keys()) + str(bean.get("luxAmenities") or "").split()
    amenities = _amenities(amenity_ids, bean.get("amenityMap"), bean.get("propertyAmenities"),
                           lux_pairs, lux_list)
    # facilitiesDesc names every facility the lister ticked; a name the id lists missed gets
    # its id from the site's table when exactly one id carries it, else id None
    known = {(a["name"] or "").lower() for a in amenities}
    have = {a["id"] for a in amenities}
    for name in str(bean.get("facilitiesDesc") or "").split(","):
        name = clean(name)
        if name and name.lower() not in known:
            known.add(name.lower())
            ids = _AMENITY_IDS_BY_NAME.get(name.lower(), [])
            amenity_id = ids[0] if len(ids) == 1 and ids[0] not in have else None
            amenities.append({"id": amenity_id, "name": name})
    breakup = bean.get("priceBreakUp") if isinstance(bean.get("priceBreakUp"), dict) else {}
    lat, lng = positive(bean.get("latitude")), positive(bean.get("longitude"))
    if lat is None or lng is None:
        lat, lng = None, None
    ld = next((d for d in _ld_json(html) if isinstance(d, dict) and "offers" in d), {})
    offers = ld.get("offers") if isinstance(ld.get("offers"), dict) else {}
    images = [clean(i) for i in (bean.get("allImgPath") or []) if clean(i)]
    rera_text = bean.get("reraValidity")
    price_amount = positive(bean.get("exactSaleRentPrice")) or positive(bean.get("price")) or positive(offers.get("price"))
    carpet = _area(bean.get("carpetArea"), bean.get("carpetAreaUnit"))
    per_sqft = positive(bean.get("sqftPrice"))
    if per_sqft is None and price_amount and carpet and carpet["unit"] == "sqft":
        per_sqft = round(price_amount / carpet["value"])   # the site's own figure (carpetAreaSqft) is this ratio
    locality = bean.get("localityDetails") if isinstance(bean.get("localityDetails"), dict) else {}
    return {
        "id": property_id,
        "link": clean(bean.get("url")) or (property_link(property_id) if property_id else None),
        "title": clean(bean.get("h1TagText")) or clean(bean.get("title")),
        "listing_type": listing_type,
        "property_type": clean(bean.get("propertyType")),
        "transaction_type": clean(bean.get("transactionType")),
        "description": _rich_text(bean.get("propertyDescription")),
        "price": {
            "amount": int(price_amount) if price_amount else None,
            "currency": "INR" if price_amount else None,
            "display": clean(bean.get("saleRentPrice")),
            "per_sqft": per_sqft,
            "market_estimate": to_int(positive(bean.get("marketPrice"))),
            "emi_per_month": to_int(positive(bean.get("emiPrice"))),
            "maintenance": _maintenance(bean.get("maintenanceCharges"),
                                        bean.get("maintenanceChargesFrequency") or bean.get("maintenanceD")),
            **_booking_or_deposit(listing_type, bean.get("bookingAmountExact"), bean.get("bookingAmt"),
                                  bean.get("securityDeposit"), breakup.get("securityDeposit")),
            "brokerage": clean(bean.get("brokerage")),
            "is_negotiable": yn(bean.get("priceNegotiable")),
            "includes_other_charges": yn(breakup.get("isOtherThanBasicPrice")) if breakup else None,
        },
        "bedrooms": to_int(bean.get("bedrooms")),
        "bathrooms": to_int(bean.get("bathrooms")),
        "balconies": to_int(bean.get("numberOfBalconiedDesc")) or to_int(bean.get("balconies")),
        "additional_rooms": [clean(x) for x in str(bean.get("additionalRooms") or "").split(",") if clean(x)],
        "area": {
            "carpet": carpet,
            "covered": _area(bean.get("coveredArea"), bean.get("coveredAreaUnit")),
            "super": _area(bean.get("superArea"), bean.get("superAreaUnit")),
            "plot": _area(bean.get("plotArea"), bean.get("plotAreaUnit")),
        },
        "furnishing": _furnishing(bean.get("furnished")),
        "floor": {"number": to_int(bean.get("floorNumber")), "total": to_int(bean.get("totalFloorNumber")),
                  "units_on_floor": to_int(positive(bean.get("unitCountonFloor")))},
        "facing": _facing(bean.get("facing")),
        "overlooking": [clean(x) for x in str(bean.get("amenitiesFacing") or "").split(",") if clean(x)],
        "possession": {"status": clean(bean.get("possessionStatus")) or clean(bean.get("ageofcons")),
                       "available_from": iso_date(bean.get("possdate")) or clean(bean.get("possdate"))},
        "age": clean(bean.get("ageofcons")),
        "ownership": clean(bean.get("ownershipType")) or clean(bean.get("ownership")),
        "parking": clean(bean.get("parking")),
        "flooring": clean(bean.get("flooringType")),
        "water": clean(bean.get("waterStatus")),
        "electricity": clean(bean.get("electricityStatus")),
        "tenant_preference": clean(bean.get("tenantPrefer")),
        "is_bachelor_friendly": yn(bean.get("bachelor")),
        "is_cooking_allowed": bean.get("cookingAllowed") if isinstance(bean.get("cookingAllowed"), bool) else None,
        "is_guest_allowed": bean.get("guestAllowed") if isinstance(bean.get("guestAllowed"), bool) else None,
        "is_corner_property": bean.get("cornerProperty") if isinstance(bean.get("cornerProperty"), bool) else None,
        "highlights": [x for x in (clean(bean.get("psmUsp")),) if x],
        "location": {
            "locality": {"id": clean(bean.get("localityId")) or clean(locality.get("localityId")),
                         "name": clean(bean.get("locality")) or clean(locality.get("localityName"))},
            "city": {"id": clean(bean.get("cityCode")), "name": clean(bean.get("city"))},
            "address": clean(bean.get("propertyAddress")),
            "landmark": clean(bean.get("landmark")),
            "latitude": lat, "longitude": lng,
            "locality_video": f"https://www.youtube.com/watch?v={locality['videoID']}" if clean(locality.get("videoID")) else None,
        },
        "project": _project_view(detail.get("projectViewBean"), bean),
        "rera_ids": _rera(rera_text),
        # the state RERA authority's website (maharera.mahaonline.gov.in for
        # Mumbai), not a page of this listing
        "rera_authority_link": clean(bean.get("reraUrl")),
        "amenities": amenities,
        "images": {"count": to_int(bean.get("propImageCount")), "cover": clean(bean.get("image")), "all": images},
        "lister": _agent_block(bean),
        "nearby_places": _nearby_places((extra.get("factoidList") or {}).get("localityInfoData")),
        "price_trend": _price_trend(extra.get("priceTrendData")),
        "is_verified": yn(bean.get("isVerified")),
        "is_paid_listing": yn(bean.get("isPaidUser")),
        "posted_on": iso_date(bean.get("postedOn")) or iso_date(bean.get("postingDate")),
        "similar": [_similar_row(r) for r in (extra.get("siproProp") or []) if isinstance(r, dict)],
        "also_viewed": [_similar_row(r) for r in (extra.get("alsoLikedProp") or []) if isinstance(r, dict)],
    }


# ---- projects ----------------------------------------------------------------------------------

def _project_card(row):
    """A project card (new-projects directory / similar projects / the
    property page's project strip) -> the public summary."""
    row = row or {}
    psmid = clean(row.get("psmid"))
    slug = clean(row.get("pdpUrl")) or clean(row.get("oldPdpUrl"))
    min_price, max_price = positive(row.get("minPriceF")) or positive(row.get("minPrice")), \
        positive(row.get("maxPriceF")) or positive(row.get("maxPrice"))
    bhk = [to_int(b) for b in str(row.get("visBd") or "").split(",") if to_int(b) is not None]
    image = clean(row.get("imageUrl"))
    if not image and clean(row.get("image")):
        image = _PROJECT_IMG + str(row["image"]).split(",")[0].strip()
    return {
        "id": psmid,
        "name": clean(row.get("psmName")),
        "link": site_link(slug) if slug else (project_link(psmid) if psmid else None),
        "developer": {"id": clean(row.get("devId")) and str(row.get("devId")), "name": clean(row.get("devName")),
                      "logo": _PROJECT_IMG + str(row["devLogo"]).strip() if clean(row.get("devLogo")) and not str(row["devLogo"]).startswith("http") else clean(row.get("devLogo"))},
        "property_type": clean(row.get("propertyTypeDesc")),
        "bedrooms": bhk,
        "price": {"min": int(min_price) if min_price else None, "max": int(max_price) if max_price else None,
                  "currency": "INR" if min_price or max_price else None,
                  "display": _range_display(row.get("showPriceRange")) or (f"{clean(row.get('minPriceDesc'))} - {clean(row.get('maxPriceDesc'))}" if clean(row.get("minPriceDesc")) else None),
                  "per_sqft_min": positive(row.get("sqFtPrice")), "per_sqft_max": positive(row.get("sqFtPrMx"))},
        "status": clean(row.get("showReadyToMove")) or clean(row.get("newHomesPossStatus")),
        "launched": _month(row.get("launchDateStr"), row.get("launchDate")),
        "possession_by": _month(row.get("prjPossDate")),
        "total_units": to_int(positive(row.get("totalUnits"))),
        "towers": to_int(positive(row.get("noTower"))) or to_int(positive(row.get("towersConstructed"))),
        "area": {"value": positive(row.get("projArea")), "unit": (clean(row.get("projAreaUnitDesc")) or "").lower() or None}
                if positive(row.get("projArea")) else None,
        "location": {"locality": {"id": clean(row.get("lt")) and str(row.get("lt")), "name": clean(row.get("lmtDName"))},
                     "city": {"name": clean(row.get("ctname"))}, "pincode": clean(row.get("pincode"))},
        "has_rera": yn(row.get("isRera")) if row.get("isRera") is not None else yn(row.get("isReraAvl")),
        "rera_updated_on": iso_date(row.get("reraUpDt")),
        "rating": round(positive(row.get("psmavgRt")), 1) if positive(row.get("psmavgRt")) else None,
        "review_count": to_int(positive(row.get("totRev"))),
        "rank": to_int(positive(row.get("psmDRanking"))),
        "tag": clean(row.get("topTag")),
        "highlights": [clean(x) for x in (row.get("projectUsp") or []) if clean(x)],
        "description": clean(row.get("mhDesc")),
        "image": image,
        "image_count": to_int(positive(row.get("totalImgCt"))),
        "brochure": clean(row.get("sblink")),
        "video": clean(row.get("vlink")) or clean(row.get("psmRevlink")),
        "amenities": _amenities(row.get("amenities") if isinstance(row.get("amenities"), list) else row.get("amenitiesDisp")),
    }


def parse_projects_list(html):
    """A /new-projects-* page -> {results, total_count, page, city, locality};
    the generic /magichomes fallback (unknown city) -> None."""
    state = extract_state(html, "SERVER_PRELOADED_STATE_") or {}
    extra = state.get("searchAdditionalDataBean") or {}
    req_url = str(extra.get("reqUrl") or "")
    if "magichomes" in req_url.lower() or not state.get("searchResult"):
        if "magichomes" in req_url.lower():
            return None
    return {
        "results": [_project_card(r) for r in (state.get("searchResult") or []) if isinstance(r, dict)],
        "total_count": to_int(extra.get("totalCount")) or 0,
        "total_pages": to_int(extra.get("pageCount")) or 0,
        "items_per_page": to_int(extra.get("cardsCount")) or 20,
        "page": to_int(extra.get("seoPageNo")) or 1,
        "city": {"id": clean(extra.get("cityId")) and str(extra.get("cityId")), "name": clean(extra.get("cityName"))},
        "locality": {"id": str(extra["localityId"]) if positive(extra.get("localityId")) else None,
                     "name": clean(extra.get("localityName"))},
    }


def _unit_plans(pricing):
    out = []
    for unit in (pricing or {}).get("All") or []:
        if not isinstance(unit, dict):
            continue
        out.append({"configuration": clean(unit.get("bhkType")),
                    "carpet_area": _area(unit.get("carpetAr") or unit.get("carpetArea"), unit.get("coverAreaUnitD")),
                    "floor_plan": clean(unit.get("planImgUrl")),
                    # monthly rents of this unit's listings, plain rupee figures ("420000")
                    "rent_price": {"min": to_int(positive(unit.get("minRentPriceD"))),
                                   "max": to_int(positive(unit.get("maxRentPriceD")))}
                                  if positive(unit.get("minRentPriceD")) else None})
    return out


def _category_ratings(value):
    """{'Environment': {'Neighborhood': 4, 'Public Transport': 5}, ...} ->
    the same tree with snake_case keys and numeric scores."""
    if not isinstance(value, dict):
        return None
    out = {}
    for key, inner in value.items():
        if isinstance(inner, dict):
            scores = {snake(k): to_float(v) for k, v in inner.items() if to_float(v) is not None}
            if scores:
                out[snake(key)] = scores
        elif to_float(inner) is not None:
            out[snake(key)] = to_float(inner)
    return out or None


def _review(row):
    row = row or {}
    return {
        "id": clean(row.get("reviewId")),
        "title": clean(_rich_text(row.get("reviewTitle"))),
        "text": _rich_text(row.get("reviewDescription")),
        "rating": to_float(row.get("overAllRating")),
        "category_ratings": _category_ratings(row.get("categoryRatingMap")),
        "reviewer": {"name": clean(row.get("userName")), "type": clean(row.get("userType")),
                     "relation": clean(row.get("userRelation")), "photo": clean(row.get("userPhoto"))},
        "recommended_for": clean(row.get("recommendedFor")),
        "is_sponsored": yn(row.get("isSponsered")),
        "posted_on": iso_date(row.get("postedOn")),
        "reviewed_on": iso_date(row.get("reviewedOn")),
    }


def _merge_review(a, b):
    """Two copies of one review -> one: the copy with ratings wins, the other fills its gaps."""
    base, other = (a, b) if (a["rating"] is not None or b["rating"] is None) else (b, a)
    out = {k: (other[k] if v is None else v) for k, v in base.items()}
    out["reviewer"] = {k: (other["reviewer"].get(k) if v is None else v) for k, v in base["reviewer"].items()}
    return out


def _reviews(block):
    block = block if isinstance(block, dict) else {}
    # the site lists a featured review twice: a copy at the top without its ratings, and the
    # original further down -> one entry per review id, at the first position
    results, at = [], {}
    for row in block.get("resultList") or []:
        if not isinstance(row, dict):
            continue
        review = _review(row)
        if review["id"] is not None and review["id"] in at:
            results[at[review["id"]]] = _merge_review(results[at[review["id"]]], review)
            continue
        if review["id"] is not None:
            at[review["id"]] = len(results)
        results.append(review)
    return {"count": to_int(block.get("count")) or 0,
            "total_pages": to_int(block.get("pageCount")),
            "star_breakdown": {str(k): to_int(v) for k, v in (block.get("starWiseRatingMap") or {}).items()} or None,
            "results": results}


def _month_series(graph):
    """projectTrendsGraph / localityTrendsGraph -> {months, series}."""
    if not isinstance(graph, dict) or not graph.get("monthwiseData"):
        return None
    months = [iso_date(m.strip().strip('"')) or m.strip().strip('"')
              for m in str(graph.get("monthYrAvgPriceStr") or "").split(",") if m.strip()]
    names = graph.get("localitiesDescMap") or {}
    series = [{"id": str(k), "name": clean(names.get(k)), "values": [to_float(v) for v in (vals or [])]}
              for k, vals in (graph.get("monthwiseData") or {}).items() if isinstance(vals, list)]
    return {"unit": "INR per sqft", "months": months, "series": series,
            "last_month": iso_date(str(graph.get("lastMonth") or "").strip('"')),
            "project_change_percent": to_float(graph.get("projectPercentChange")),
            "locality_change_percent": to_float(graph.get("localityPercentChange"))}


def _locality_profile(bean):
    dto = (bean or {}).get("localityDetailDTO") if isinstance(bean, dict) else None
    if not isinstance(dto, dict):
        return None
    ratings = {}
    for key, value in dto.items():
        name = key[:-len("Rating")] if key.endswith("Rating") else key
        if (key.endswith("Rating") or key in ("environment", "commuting", "placeOfInterest")) \
                and to_float(value) is not None:
            ratings[_LOCALITY_RATINGS.get(name, snake(name))] = to_float(value)
    quarter = dto.get("quarterPrice") if isinstance(dto.get("quarterPrice"), dict) else {}
    return {
        "id": clean(dto.get("locId")), "name": clean(dto.get("locName")), "city": clean(dto.get("cityName")),
        "rank": to_int(dto.get("locRank")), "localities_in_city": to_int(dto.get("totalLoc")),
        "rating": to_float(dto.get("ratingAvgCount")), "rating_count": to_int(dto.get("ratingCount")),
        "review_count": to_int(dto.get("reviewCount")),
        "ratings": ratings or None,
        "price_per_sqft": {"current_quarter": to_float(quarter.get("currentQuarterPrice")),
                           "previous_quarter": to_float(quarter.get("prevQuarterPrice")),
                           "quarter_change_percent": to_float(dto.get("percentageQuarterGrowth"))},
        "introduction": clean(dto.get("locIntroduction")),
        "physical_infrastructure": clean(dto.get("locPhysicalInfra")),
        "social_infrastructure": clean(dto.get("locSocialInfra")),
        "nearby_hubs": clean(dto.get("locNearbyHubs")),
        "pros": [clean(dto.get(k)) for k in ("pros1", "pros2", "pros3") if clean(dto.get(k))],
        "cons": [clean(dto.get(k)) for k in ("cons1", "cons2", "cons3") if clean(dto.get(k))],
        "nearby_places": _nearby_places(dto.get("localityFactoidBean")),
        "video": clean(dto.get("videoUrls")),
    }


def _faqs(block):
    out = []
    for item in (block or {}).get("qaList") or []:
        if isinstance(item, dict):
            for question, answer in item.items():
                answer = re.sub(r"<[^>]+>", "", str(answer or ""))
                out.append({"question": clean(question), "answer": clean(answer)})
    return out


def parse_project(html, psmid=None):
    """The project page -> the full record."""
    state = extract_state(html, "SERVER_PRELOADED_STATE_") or {}
    data = state.get("projectDetailData") or {}
    mobile = data.get("prjMobileBean") or {}
    bean = mobile.get("detailBean") or {}
    info = mobile.get("infoBean") or {}
    developer = mobile.get("projectDeveloperList") or {}
    ratings = mobile.get("ratingBean") or {}
    seo = state.get("projectPageSeoStaticData") or {}
    psmid = clean(mobile.get("psmId")) or clean(info.get("psmid")) or psmid
    slug = clean(mobile.get("projectUrl"))
    rera_slug = clean(data.get("reraUrl")) or clean((seo.get("psmDataBean") or {}).get("reraUrl"))
    min_price, max_price = positive(info.get("minPrice")), positive(info.get("maxPrice"))
    rate = clean(bean.get("rate"))
    rate_min, rate_max = (to_float(rate.split("-")[0]), to_float(rate.split("-")[-1])) if rate else (None, None)
    amenities = [{"id": clean(a.get("amenityId")), "name": clean(a.get("amenityName")),
                  "icon": clean(a.get("amenityImg"))}
                 for a in (mobile.get("amenitiesList") or []) if isinstance(a, dict) and clean(a.get("amenityName"))]
    gallery = data.get("galleryData") if isinstance(data.get("galleryData"), dict) else {}
    photos = [{"link": clean(p.get("src")), "caption": clean(p.get("caption")) or clean(p.get("title"))}
              for p in (mobile.get("projectImages") or []) if isinstance(p, dict) and clean(p.get("src"))]
    videos = [k for k in (gallery.get("Videos") or {}) if str(k).startswith("http")]
    floor_plans = [k for k in (gallery.get("Floor Plan") or {}) if str(k).startswith("http")]
    construction_photos = [k for k in (gallery.get("Construction Photos") or {}) if str(k).startswith("http")]
    brochure = clean(bean.get("brochurelink"))
    if brochure and not brochure.startswith("http"):
        brochure = _PROJECT_IMG + brochure
    category_ratings = _project_ratings(ratings)
    specs = mobile.get("projectSpecificationList") if isinstance(mobile.get("projectSpecificationList"), dict) else {}
    specifications = {k.replace("Detail", ""): v for k, v in specs.items() if v}
    description = _strip_html((mobile.get("projectDescription") or {}).get("fullDesc")) \
        if isinstance(mobile.get("projectDescription"), dict) else None
    return {
        "id": psmid,
        "name": clean(info.get("projectName")) or clean(mobile.get("opsmname")),
        "link": site_link(slug) if slug else (project_link(psmid) if psmid else None),
        "status": clean(bean.get("status")),
        "property_type": clean(bean.get("propType")),
        "project_type": clean(bean.get("projectType")),
        "configurations": clean(bean.get("prjConfig")) or clean(seo.get("unitInfo")),
        "bedrooms": [to_int(b) for b in str(bean.get("bedroom") or "").split(",") if to_int(b) is not None],
        "description": description,
        "specifications_text": _strip_html(bean.get("specifications")),
        "specifications": specifications or None,
        "price": {"min": int(min_price) if min_price else None, "max": int(max_price) if max_price else None,
                  "currency": "INR" if min_price or max_price else None,
                  "display": clean(info.get("price")),
                  "per_sqft_min": rate_min, "per_sqft_max": rate_max},
        "launched": _month(bean.get("launchDateStr"), bean.get("launchDate")),
        "possession_by": _month(bean.get("possessionByDate"), bean.get("possdateStr")),
        "total_units": to_int(bean.get("units")),
        "towers": to_int(bean.get("towers")),
        "floors": to_int(bean.get("numOfFloors")),
        "area": {"value": to_float(bean.get("projArea")), "unit": _unit(re.sub(r"[\d. ]", "", str(bean.get("projArea") or "")) or None)}
                if to_float(bean.get("projArea")) else None,
        "location": {
            "locality": {"id": clean(info.get("localityId")), "name": clean(info.get("localityName"))},
            "city": {"id": clean(info.get("cityId")), "name": clean(info.get("cityName"))},
            "state": clean(bean.get("stateDesc")),
            "address": clean(bean.get("fullAddress")) or clean(bean.get("ad")),
            "pincode": clean(bean.get("pincode")),
            "latitude": to_float(info.get("psmLatitude")), "longitude": to_float(info.get("psmLongitude")),
        },
        "developer": {
            "id": clean(mobile.get("devid")),
            "name": clean(developer.get("developerName")) or clean(info.get("devName")),
            "link": site_link(clean(developer.get("builderUrl"))),
            "logo": clean(developer.get("logo")),
            "experience_years": to_int(developer.get("developerExp")),
            "total_projects": to_int(developer.get("devTotalProj")),
            "completed_projects": to_int(developer.get("devCompProj")),
            "ongoing_projects": to_int(developer.get("devOngoingProj")),
            "cities": [clean(c) for c in (developer.get("devCities") or []) if clean(c)],
            "about": _strip_html(developer.get("fullDesc")),
        },
        "rera": {"ids": [clean(r) for r in (bean.get("reraIdList") or []) if clean(r)] or _rera(info.get("reraValidity")),
                 "link": rera_link(rera_slug), "slug": rera_slug,
                 "updated_on": iso_date((seo.get("psmDataBean") or {}).get("reraUpDt")),
                 "authority_link": clean(data.get("pdpReraUrl")),
                 "is_available": yn(data.get("isReraAvl"))},
        "approved_by_banks": [clean(b) for b in (bean.get("bankListMap") or {}).keys() if clean(b)]
                             if isinstance(bean.get("bankListMap"), dict) else [],
        "certificates": {"commencement": yn(bean.get("ccObtained")), "occupancy": yn(bean.get("ocObtained"))},
        "amenities": amenities,
        "unit_plans": _unit_plans(seo.get("pdpUnitPricing")),
        "gallery": {"photo_count": to_int(mobile.get("allImgCount")) or len(photos), "photos": photos,
                    "floor_plans": floor_plans, "construction_photos": construction_photos, "videos": videos,
                    "brochure": brochure},
        "rating": to_float(ratings.get("psmAvgRt")),
        "review_count": to_int(ratings.get("totalReview")),
        "ratings": category_ratings or None,
        "rank": {"in_locality": to_int(((data.get("projectRank") or {}).get("data") or {}).get("rank")) if isinstance(data.get("projectRank"), dict) else None,
                 "of": ((data.get("projectRank") or {}).get("data") or {}).get("total") if isinstance(data.get("projectRank"), dict) else None},
        "listings_for_sale": to_int(mobile.get("sellCountProperty")),
        "is_prelaunch": yn(data.get("isPrelaunch")),
        "is_blacklisted": yn(data.get("isBlacklisted")),
        "price_trend": _month_series(seo.get("projectTrendsGraph")),
        "locality_price_trend": _month_series(seo.get("localityTrendsGraph")),
        "locality": _locality_profile(seo.get("localityDetailsBean")),
        "faqs": _faqs(seo.get("pdpFAQs")),
        "reviews": _reviews(seo.get("projectReviews")),
        "locality_reviews": _reviews(seo.get("localityReviews")),
        "similar_projects": [_project_card(r) for r in ((seo.get("similarProjects") or {}).get("dataList") or [])
                             if isinstance(r, dict)],
        "developer_projects": [_project_card(r) for r in ((seo.get("similarBuilderProjects") or {}).get("dataList") or [])
                               if isinstance(r, dict)],
        "updated_on": iso_date(info.get("psmLastModiDate")) or iso_date(mobile.get("lud")),
    }


_TYPE_BY_TRENDS_CODE = {code: name for name, code in TRENDS_PROPERTY_TYPES.items()}


def _unit_configurations(value):
    """mUnitInfo '3 , 10002 , 1590 Sq-ft | 4 , 10002 , 1965 Sq-ft' (BHK, property-type
    code, carpet area) -> [{bedrooms, property_type, carpet_area{value, unit}}]."""
    out = []
    for part in str(value or "").split("|"):
        fields = [clean(f) for f in part.split(",")]
        if len(fields) != 3 or not fields[2]:
            continue
        match = re.match(r"^([\d.]+)\s*(.*)$", fields[2])
        out.append({"bedrooms": to_int(fields[0]),
                    "property_type": _TYPE_BY_TRENDS_CODE.get(fields[1]),
                    "carpet_area": _area(match.group(1), match.group(2)) if match else None})
    return out


def _doc_groups(items):
    """DocData.Data / reraData rows -> [{group, documents[{name, link}]}]."""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        value = item.get("dataValue")
        if isinstance(value, list):
            out.extend(_doc_groups(value))
            continue
        if not isinstance(value, dict):
            continue
        docs, links = [], set()
        for name, path in value.items():
            if not clean(path):
                continue
            link = _RERA_IMG + str(path).lstrip("/") if not str(path).startswith("http") else clean(path)
            if link in links:       # the site lists one PDF under several numbered names
                continue
            links.add(link)
            docs.append({"name": clean(name), "link": link})
        out.append({"group": clean(item.get("dataKey")), "documents": docs})
    return out


def parse_rera(html, psmid=None):
    """The RERA page -> registration + document lists."""
    state = extract_state(html, "SERVER_PRELOADED_STATE_") or {}
    page = state.get("newReraPageData") or {}
    psm = page.get("psmData") or {}
    doc_data = page.get("DocData") if isinstance(page.get("DocData"), dict) else {}
    groups = _doc_groups(doc_data.get("Data"))
    if not groups:
        groups = _doc_groups((state.get("reraData") or {}).get("reraData"))
    registrations = []
    for entry in psm.get("reraValidity") or []:
        parts = str(entry).split("|")
        if clean(parts[0]) and clean(parts[0]).lower() not in ("na", "null"):
            registrations.append({"id": clean(parts[0]),
                                  "valid_until": iso_date(parts[-1]) if len(parts) > 1 else None,
                                  "phase": clean(parts[-2]) if len(parts) > 3 else None})
    return {
        "id": clean(psm.get("psmid")) or psmid,
        "name": clean(psm.get("psmName")),
        "link": site_link(clean(psm.get("pdpUrl"))),
        "rera_link": site_link(clean(psm.get("reraUrl"))),
        "developer": clean(psm.get("devName")),
        "registrations": registrations,
        "has_legal_certificates": yn(doc_data.get("LegalDocs")),
        "has_quarterly_reports": yn(doc_data.get("QuarterReport")),
        "updated_on": iso_date(psm.get("reraUpDt")),
        "document_groups": groups,
        "unit_configurations": _unit_configurations(psm.get("mUnitInfo")),
        "total_units": to_int(positive(psm.get("totalUnits"))),
        "possession_by": _month(psm.get("prjPossDate")),
    }


# ---- agents --------------------------------------------------------------------------------

_STAT_KEYS = {"properties for sale": "sale_listings", "properties for rent": "rent_listings",
              "deals closed": "deals_closed", "team members": "team_size"}


def _text(node):
    return " ".join(node.get_text(" ", strip=True).split()) if node is not None else None


def settle_agent_cities(agents, searched_city=None):
    """A card without a base locality reads 'Company, Mumbai', so parse_agents takes the
    lone place for a locality. When that place is the city searched (or the city most
    cards name), it is the agent's city -> city set, locality None. In place, returns agents."""
    named = Counter(a["city"].lower() for a in agents if a.get("city"))
    cities = {str(searched_city).lower()} if searched_city and not str(searched_city).isdigit() else set()
    if named:
        cities.add(named.most_common(1)[0][0])
    for agent in agents:
        if not agent.get("city") and (agent.get("locality") or "").lower() in cities:
            agent["city"], agent["locality"] = agent["locality"], None
    return agents


def parse_agents(html):
    """The top-agents fragment -> [agent cards]. An empty fragment -> []."""
    if not html or "prefagent" not in html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select("div.prefagent"):
        name = _text(card.select_one(".prefagent__headersec__name"))
        if not name:
            continue
        line = card.select_one(".prefagent__headersec__txt1")
        company_node = line.select_one(".prefagent__headersec__txt1--bold") if line else None
        company = _text(company_node)
        if company_node is not None:
            company_node.extract()
        place = _text(line)
        locality, city = (place.rsplit(",", 1) + [None])[:2] if place else (None, None)
        since = _text(card.select_one(".prefagent__headersec__txt2"))
        stats = {}
        for col in card.select(".prefagent__detlsec__stats__col"):
            label = (_text(col.select_one(".prefagent__detlsec__stats__txt")) or "").lower()
            key = _STAT_KEYS.get(label)
            if key:
                stats[key] = to_int(_text(col.select_one(".prefagent__detlsec__stats__num")))
        deals = {}
        headings = card.select(".prefagent__detlsec__deals__heading")
        for heading in headings:
            value = heading.find_next_sibling(class_="prefagent__detlsec__deals__val")
            deals[(_text(heading) or "").lower()] = _text(value)
        about_node = card.select_one(".prefagent__detlsec__abtagent__txt")
        about = None
        if about_node is not None:
            for junk in about_node.select(".dots, .showmore"):
                junk.extract()
            about = _text(about_node)
        agent_id = None
        button = card.select_one("[id^=contactBtn]")
        if button is not None:
            agent_id = button.get("id", "").replace("contactBtn", "") or None
        link = None
        for anchor in card.select("a"):
            match = re.search(r"https?://[^'\"]+agentid-[0-9a-f]+", anchor.get("onclick") or "")
            if match:
                link = match.group(0).replace("http://", "https://")
                break
        if not link and agent_id:
            link = agent_link(agent_id)
        out.append({
            "id": agent_id,
            "name": name,
            "company": company.rstrip(", ").strip() if company else None,
            "link": link,
            "locality": clean(locality),
            "city": clean(city),
            "operating_since": to_int(since),
            "badge": _text(card.select_one(".prefagent__headersec__tagblk__txt")),
            "sale_listings": stats.get("sale_listings"),
            "rent_listings": stats.get("rent_listings"),
            "deals_closed": stats.get("deals_closed"),
            "team_size": stats.get("team_size"),
            "deals_in": [clean(x) for x in (deals.get("deals in") or "").split(",") if clean(x)],
            "operates_in": [clean(x) for x in (deals.get("operates in") or "").split(",") if clean(x)],
            "about": about,
            "photo": (card.select_one(".prefagent__headersec__img") or {}).get("src"),
            "logo": (card.select_one(".prefagent__headersec__brand__logo") or {}).get("src"),
        })
    return out


# ---- autosuggest -----------------------------------------------------------------------------

# suggestType codes (2026-11-07): lt = locality, lt_al = a locality alias
# with its own id (Bandra Reclamation), lt_pg = a place inside a locality
# whose rfnum is "<locality id>-<place name>", pg = a paying-guest listing.
_SUGGEST_KINDS = {"city_name": "city", "sub": "sub_region", "lt": "locality", "lt_al": "locality",
                  "lt_pg": "landmark", "prj": "project", "pg": "paying_guest", "state_name": "region"}


def _place(id_, name):
    """{id, name} for a city / locality reference, None when both are unknown."""
    return {"id": id_, "name": name} if id_ or name else None


def parse_autosuggest(payload):
    """{locationMap, landmarkMap} -> one flat list of places, every item with
    the same keys. City / locality names come from the site's own display
    string where its format fixes them: '<locality>, <city>' and
    '<project>, <locality>, <city>'."""
    payload = payload or {}
    out = []
    for group in (payload.get("locationMap") or {}).values():
        for item in group or []:
            if not isinstance(item, dict):
                continue
            code = clean(item.get("suggestType")) or ""
            kind = _SUGGEST_KINDS.get(code, code or None)
            place_id = clean(item.get("rfnum"))
            name = clean(item.get("psmName")) or clean(item.get("result"))
            display = clean(item.get("result"))
            locality_id = clean(item.get("localityId"))
            if code == "lt_pg" and place_id:
                # "82390-Worli Sea Face Municipal School Worli": the prefix is
                # the locality's id; the place itself has no id of its own
                prefix = place_id.split("-", 1)[0]
                locality_id = locality_id or (prefix if prefix.isdigit() else None)
                place_id = None
            parts = [p.strip() for p in (display or "").split(",")]
            city_name = locality_name = None
            if kind == "city":
                city_name = name
            elif code == "prj" and len(parts) >= 3:
                locality_name, city_name = parts[-2] or None, parts[-1] or None
            elif code in ("lt", "lt_al", "lt_pg") and len(parts) >= 2:
                city_name = parts[-1] or None
            out.append({
                "id": place_id,
                "name": name,
                "display": display,
                "type": kind,
                "category": None,
                "city": _place(clean(item.get("city")), city_name),
                "locality": _place(locality_id, locality_name),
                "state": clean(item.get("stateName")),
                "developer": clean(item.get("devName")),
                "latitude": to_float(item.get("latitude")), "longitude": to_float(item.get("longitude")),
            })
    for category, items in (payload.get("landmarkMap") or {}).items():
        for item in items or []:
            if not isinstance(item, dict):
                continue
            out.append({
                "id": None,
                "name": clean(item.get("result")),
                "display": clean(item.get("result")),
                "type": "landmark",
                "category": clean(item.get("catgoryName")) or clean(category),
                "city": _place(clean(item.get("city")), clean(item.get("cityName"))),
                "locality": _place(clean(item.get("locality")), clean(item.get("locName"))),
                "state": None, "developer": None,
                "latitude": to_float(item.get("lat")), "longitude": to_float(item.get("lng")),
            })
    return out


# ---- trends ---------------------------------------------------------------------------------

def parse_trends(payload, table_html=None):
    """trendsdata JSON + the tableData.html tables -> {quarters, series,
    quarterly_table, yearly_table}; None when the site returned nothing."""
    payload = payload if isinstance(payload, dict) else {}
    datasets = [d for d in (payload.get("datasets") or []) if isinstance(d, dict)]
    labels = [iso_date(l) or clean(l) for l in (payload.get("labels") or [])]
    series = [{"name": clean(d.get("label")), "values": [to_float(v) for v in (d.get("data") or [])]}
              for d in datasets]
    quarterly, yearly = _trend_tables(table_html)
    if not series and not quarterly and not yearly:
        return None
    return {"unit": "INR per sqft", "quarters": labels, "series": series,
            "quarterly_table": quarterly, "yearly_table": yearly}


def _trend_tables(html):
    if not html or "<table" not in html:
        return [], []
    soup = BeautifulSoup(html, "lxml")
    tables = {}
    for table in soup.select("table"):
        classes = " ".join(table.get("class") or [])
        kind = "quarterly" if "table_oneY" in classes else "yearly" if "table_threeY" in classes else None
        if not kind:
            continue
        rows = []
        for row in table.select("tr")[1:]:
            cells = row.select("td")
            if len(cells) < 2:
                continue
            value_cell = cells[1]
            change = value_cell.select_one("[class*=tdredtxt], [class*=tdgreentxt]")
            change_text = _text(change) if change is not None else None
            if change is not None:
                change.extract()
            rows.append({"period": _text(cells[0]),
                         "price_per_sqft": to_float(_text(value_cell)),
                         "change_percent": (-abs(to_float(change_text)) if "red" in " ".join(change.get("class") or [])
                                            else to_float(change_text)) if change_text and to_float(change_text) is not None else None})
        tables[kind] = rows
    return tables.get("quarterly", []), tables.get("yearly", [])
