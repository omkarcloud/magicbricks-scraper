"""The /magicbricks/* endpoint functions (route_glue's route_table calls
them with the schema's loaded kwargs).

properties/details and properties/similar slice ONE cached page parse
(cache.cached_call stores parse_property under magicbricks.property keyed
on the id); projects/details, projects/reviews and projects/rera share
the cached project parse the same way (the RERA page needs the slug the
project page publishes). Everything else caches its own response.

Place inputs: a numeric value is the site's own id and goes out as
`city=` / `locality=`; a name goes out as `cityName=` / `Locality=` (both
accepted by /mbsrp/propertySearch.html). An unknown city answers with a
null city name and is a 404; a locality name the city does not have comes
back with a null id and is a 404 too (the site would silently drop the
filter and return the whole city).
"""
from cache import cached_call
from magicbricks import cache_config as ttl
from magicbricks import parsers
from magicbricks.fetch import (
    MagicbricksNotFound, fetch_agents, fetch_autosuggest, fetch_project, fetch_projects_list, fetch_property,
    fetch_rera, fetch_search, fetch_trends, fetch_trends_table,
)
from magicbricks.refs import LISTING_TYPES, TRENDS_PROPERTY_TYPES, is_numeric_id

SEARCH_PAGE_SIZE = 30     # /mbsrp/propertySearch.html's own page size
PROJECTS_PAGE_SIZE = 20   # /new-projects-* pages


def _pagination(page, per_page, total_count, total_pages):
    if total_pages and total_count and total_pages * per_page < total_count:
        # the site's pageCount is a UI cap (50); the real reach is 100 pages
        total_pages = min(-(-total_count // per_page), 100)
    return {"page": page, "items_per_page": per_page, "total_pages": total_pages or 0,
            "total_count": total_count or 0}


# ---- locations/search ------------------------------------------------------------------

def _locations_search(query, city):
    city_code = _city_code(city) if city else None
    results = parsers.parse_autosuggest(fetch_autosuggest(query, city_code))
    return {"query": query, "count": len(results), "results": results}


def locations_search(**data):
    """Autocomplete a place or project name: cities, sub-regions, localities,
    projects, landmarks and paying-guest listings, each with its magicbricks
    id, city id and coordinates. `city` narrows localities and projects to
    one city. The ids feed `city` / `locality` / `project` on every other
    endpoint."""
    return cached_call("magicbricks.locations", data, _locations_search, ttl.SUGGEST_CACHE)


def _suggest_places(text, city=None, kinds=("locality",)):
    results = parsers.parse_autosuggest(fetch_autosuggest(text, city))
    return [r for r in results if r.get("type") in kinds]


def _city_code(city):
    """A city name or code -> the site's city code (via autosuggest)."""
    if is_numeric_id(city):
        return str(city)
    for place in _suggest_places(city, kinds=("city",)):
        if place.get("id"):
            return place["id"]
    raise MagicbricksNotFound(f"city {city!r} not found on magicbricks.com")


def _locality_id(locality, city=None):
    """A locality name or id -> the site's locality id (via autosuggest,
    narrowed to the city when one is given)."""
    if is_numeric_id(locality):
        return str(locality)
    city_code = _city_code(city) if city else None
    places = _suggest_places(locality, city_code)
    wanted = " ".join(locality.lower().split())
    for place in places:
        if (place.get("name") or "").lower() == wanted and place.get("id"):
            return place["id"]
    for place in places:
        if place.get("id"):
            return place["id"]
    raise MagicbricksNotFound(f"locality {locality!r} not found on magicbricks.com")


# ---- properties/search ---------------------------------------------------------------------

def _place_params(params, city=None, locality=None):
    if city is not None:
        params["city" if is_numeric_id(city) else "cityName"] = city
    if locality:
        names = [x.strip() for x in str(locality).split(",") if x.strip()]
        ids = [x for x in names if is_numeric_id(x)]
        words = [x for x in names if not is_numeric_id(x)]
        if ids:
            params["locality"] = ",".join(ids)
        if words:
            params["Locality"] = ",".join(words)
    return params


def _search_page(params, page, label):
    payload = fetch_search({**params, "page": page})
    if payload is None:   # past the last page
        return {"summary": None, "city": {"id": None, "name": None}, "localities": [], "results": [],
                "pagination": _pagination(page, SEARCH_PAGE_SIZE, 0, 0)}
    parsed = parsers.parse_search(payload)
    if parsed["city"]["name"] is None and ("cityName" in params or "city" in params):
        raise MagicbricksNotFound(f"city {params.get('cityName') or params.get('city')!r} not found on magicbricks.com")
    missing = [l["name"] for l in parsed["localities"] if l["id"] is None and l["name"]]
    if missing:
        raise MagicbricksNotFound(f"locality {missing[0]!r} not found in {parsed['city']['name']}")
    return {
        "summary": parsed["summary"],
        "city": parsed["city"],
        "localities": parsed["localities"],
        "results": parsed["results"],
        "pagination": _pagination(page, parsed["items_per_page"], parsed["total_count"], parsed["total_pages"]),
    }


def _properties_search(city, listing_type, locality, property_type, bedrooms, min_price, max_price,
                       min_area, max_area, furnishing, possession, keyword, sort, page):
    params = _place_params({"category": listing_type, "sortBy": sort}, city, locality)
    if property_type:
        params["proptype"] = ",".join(property_type)
    if bedrooms:
        params["bedroom"] = ",".join(bedrooms)
    if min_price:
        params["budgetMin"] = min_price
    if max_price:
        params["budgetMax"] = max_price
    if min_area:
        params["areaFrom"] = min_area
    if max_area:
        params["areaTo"] = max_area
    if furnishing:
        params["furnished"] = furnishing
    if possession:
        params["possessionStatus"] = possession
    if keyword:
        params["keyword"] = keyword
    out = _search_page(params, page, "search")
    out = {"listing_type": _public_listing_type(listing_type), **out}
    return out


def _public_listing_type(code):
    return next((k for k, v in LISTING_TYPES.items() if v == code), code)


def properties_search(**data):
    """Search sale or rent listings in a city (30 per page, up to 100 pages):
    price with ₹ per sq ft, BHK, bathrooms, carpet and covered area,
    furnishing, floor, facing, possession, locality with coordinates,
    project, amenities, nearby landmarks, lister and photos. Filter by
    locality, property type, bedrooms, budget, area, furnishing, possession
    and keyword; sort by relevance, price, rate per sq ft or newest. An
    unknown city or locality is a 404."""
    return cached_call("magicbricks.search", data, _properties_search, ttl.SEARCH_CACHE)


# ---- the shared property record -------------------------------------------------------------

def _property_record(property):
    return parsers.parse_property(fetch_property(property), property)


def _record(property):
    return cached_call("magicbricks.property", {"property": property}, _property_record, ttl.PROPERTY_CACHE)


def property_details(property):
    """Get one listing in full: price with ₹ per sq ft, market estimate and
    EMI, rooms, carpet / covered / super / plot area, floor, facing,
    possession, amenities, address and coordinates, the project (units,
    towers, ratings, brochure), the lister (company, RERA ids, rating,
    listing counts), nearby places and the 12-month ₹ per sq ft trend of the
    locality and the project. The lister's phone and email are null: the
    site shows them only after an OTP login. An unknown or expired listing
    is a 404."""
    record = dict(_record(property))
    record["similar_count"] = len(record.pop("similar", []) or [])
    record["also_viewed_count"] = len(record.pop("also_viewed", []) or [])
    return record


def property_similar(property):
    """Get the listings the site recommends next to one listing: up to 60
    similar properties plus the "also viewed" ones, each with id, link,
    title, price, possession, floor, developer, project link, photo and
    coordinates."""
    record = _record(property)
    return {
        "id": record["id"], "link": record["link"], "title": record["title"],
        "similar": record["similar"], "similar_count": len(record["similar"]),
        "also_viewed": record["also_viewed"], "also_viewed_count": len(record["also_viewed"]),
    }


# ---- projects ---------------------------------------------------------------------------------

def _projects_search(city, locality, page):
    html = fetch_projects_list(city, locality, page)
    parsed = parsers.parse_projects_list(html)
    if parsed is None:
        raise MagicbricksNotFound(f"no new-projects directory for {locality + ', ' if locality else ''}{city!r}")
    if locality and parsed["locality"]["name"] is None and parsed["results"]:
        # the site serves the city directory when the locality is unknown
        raise MagicbricksNotFound(f"locality {locality!r} not found in {parsed['city']['name'] or city}")
    return {
        "city": parsed["city"],
        "locality": parsed["locality"] if locality else None,
        "results": parsed["results"],
        "pagination": _pagination(page, parsed["items_per_page"], parsed["total_count"], parsed["total_pages"]),
    }


def projects_search(**data):
    """Browse new and upcoming residential projects in a city or one of its
    localities (20 per page): name, developer, BHK mix, price range, ₹ per
    sq ft range, status, launch and possession dates, units, towers, RERA
    flag, rating, photos, brochure and amenities."""
    return cached_call("magicbricks.projects", data, _projects_search, ttl.PROJECTS_LIST_CACHE)


def _project_record(project):
    return parsers.parse_project(fetch_project(project), project)


def _project(project):
    return cached_call("magicbricks.project", {"project": project}, _project_record, ttl.PROJECT_CACHE)


def project_details(project):
    """Get one project in full: status, configurations, price range, launch
    and possession dates, units, towers, floors, address with pincode and
    coordinates, developer profile, RERA ids, approving banks, amenities,
    unit floor plans, photo gallery, ratings, 12-month price trends, the
    locality profile, FAQs and similar projects."""
    record = dict(_project(project))
    reviews = record.pop("reviews", None) or {}
    locality_reviews = record.pop("locality_reviews", None) or {}
    record["review_count"] = record.get("review_count") or reviews.get("count")
    record["locality_review_count"] = locality_reviews.get("count")
    return record


def project_reviews(project):
    """Get a project's resident reviews (title, text, reviewer type and
    relation, dates) with its category ratings, plus the reviews and
    ratings of the project's locality."""
    record = _project(project)
    return {
        "id": record["id"], "name": record["name"], "link": record["link"],
        "rating": record["rating"], "ratings": record["ratings"],
        "reviews": record["reviews"],
        "locality": {"name": (record.get("locality") or {}).get("name"),
                     "rating": (record.get("locality") or {}).get("rating"),
                     "ratings": (record.get("locality") or {}).get("ratings")} if record.get("locality") else None,
        "locality_reviews": record["locality_reviews"],
    }


def _project_rera(project):
    record = _project(project)
    slug = (record.get("rera") or {}).get("slug")
    if not slug:
        raise MagicbricksNotFound(f"project {project} publishes no RERA page")
    return parsers.parse_rera(fetch_rera(slug, project), project)


def project_rera(**data):
    """Get a project's RERA registrations (id, validity, phase) and the
    documents its developer filed: legal certificates, quarterly progress
    reports and others, each a direct PDF link. A project without a RERA
    page is a 404."""
    return cached_call("magicbricks.rera", data, _project_rera, ttl.RERA_CACHE)


def _project_listings(project, listing_type, page):
    params = {"category": listing_type, "psmid": project, "sortBy": "premiumRecent"}
    out = _search_page(params, page, "project listings")
    out.pop("localities", None)
    out.pop("city", None)
    if not out["results"] and page == 1:
        # an unknown psmid and a project with no listings of this type both
        # answer an empty page upstream; the (cached) project page tells
        # them apart — it 404s for an unknown id
        _project(project)
    return {"project": {"id": project}, "listing_type": _public_listing_type(listing_type), **out}


def project_listings(**data):
    """List the live sale or rent listings inside one project (30 per page),
    in the same shape as properties/search. An unknown project is a 404."""
    return cached_call("magicbricks.project_listings", data, _project_listings, ttl.SEARCH_CACHE)


# ---- agents -----------------------------------------------------------------------------------

def _agents_search(city, locality, listing_type):
    locality_id = _locality_id(locality, city) if locality else None
    city_code = _city_code(city) if city and not locality_id else None
    html = fetch_agents(listing_type, city=city_code, locality=locality_id)
    results = parsers.parse_agents(html)
    return {
        "city": city,
        "locality": {"id": locality_id, "name": None if is_numeric_id(locality) else locality} if locality else None,
        "listing_type": _public_listing_type(listing_type),
        "count": len(results), "results": results,
    }


def agents_search(**data):
    """Get the top-ranked real-estate agents of a city or a locality (about
    100 per city, one page): name, company, profile link, base locality,
    operating since, sale and rent listing counts, deals closed, team size,
    deal types, operating localities, about text, photo and logo. Phone
    numbers are not on the public cards."""
    return cached_call("magicbricks.agents", data, _agents_search, ttl.AGENTS_CACHE)


def _agent_listings(agent, city, listing_type, page):
    params = _place_params({"category": listing_type, "oid": agent, "sortBy": "premiumRecent"}, city)
    out = _search_page(params, page, "agent listings")
    out.pop("localities", None)
    if not city:
        out.pop("city", None)
    return {"agent": {"id": agent}, "listing_type": _public_listing_type(listing_type), **out}


def agent_listings(**data):
    """List one agent's live sale or rent listings (30 per page), optionally
    inside one city, in the same shape as properties/search. An agent with
    no live listings returns an empty page."""
    return cached_call("magicbricks.agent_listings", data, _agent_listings, ttl.SEARCH_CACHE)


# ---- localities/trends --------------------------------------------------------------------

def _locality_trends(locality, city, listing_type, property_type):
    locality_id = _locality_id(locality, city)
    payload = fetch_trends(locality_id, listing_type, property_type)
    table = fetch_trends_table(locality_id, listing_type, property_type) if payload else None
    trends = parsers.parse_trends(payload, table)
    if trends is None:
        raise MagicbricksNotFound(f"no price trend for locality {locality!r}")
    public_type = next((k for k, v in TRENDS_PROPERTY_TYPES.items() if v == property_type), None)
    return {
        "locality": {"id": locality_id, "name": None if is_numeric_id(locality) else locality},
        "listing_type": _public_listing_type(listing_type),
        "property_type": public_type or property_type,
        **trends,
    }


def locality_trends(**data):
    """Get a locality's price trend: average ₹ per sq ft for every quarter of
    the last five years, plus the site's quarter-on-quarter and yearly
    change tables when it publishes them, for sale or rent and per property
    type. An unknown locality is a 404."""
    return cached_call("magicbricks.trends", data, _locality_trends, ttl.TRENDS_CACHE)
