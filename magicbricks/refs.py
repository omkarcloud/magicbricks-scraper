"""Reference resolvers, link builders and the slug / code tables the
/magicbricks/* schemas and parsers share.

ONE param per input (tripadvisor QueryOrIdField convention, never a
sibling `url` / `id` pair). Every magicbricks.com entity link carries the
entity's id hex-encoded with an "MB" prefix (research 2026-11-07):

    property  87092175  ->  /propertyDetails/<slug>&id=4d423837303932313735
                            (hex of "MB87092175"; the slug is ignored)
    project   5336113   ->  /<slug>-pdpid-4d4235333336313133   (hex of "MB5336113")
              RERA page    /<slug>-rera-details-nprid-<same hex>
    agent     61979531  ->  /top-agent-details/<slug>-agentid-4d423631393739353331

so a resolver accepts the bare decimal id, the hex form, or any
magicbricks.com link carrying it, and returns the decimal id. Resolvers
raise ValueError with a user-facing message (RefField -> 400).

The property-type slugs, sort tokens, furnishing / possession codes and the
trends property-type codes are the site's own (verified against
/mbsrp/propertySearch.html result counts on 2026-11-07); the amenity and
landmark-category tables are the id -> name pairs the site embeds in its
pages (union over the captured fixtures).
"""
import re
from urllib.parse import urlparse

SITE = "https://www.magicbricks.com"

_DIGITS_RE = re.compile(r"^[0-9]{3,12}$")
_HEX_RE = re.compile(r"^(?:4d42|4D42)(?:[0-9a-fA-F]{2})+$")
_LINK_PROPERTY_RE = re.compile(r"[?&]id=(4d42[0-9a-fA-F]+)", re.I)
_LINK_PROJECT_RE = re.compile(r"-(?:pdpid|nprid)-(4d42[0-9a-fA-F]+)", re.I)
_LINK_AGENT_RE = re.compile(r"-agentid-(4d42[0-9a-fA-F]+)", re.I)


def encode_id(decimal_id):
    """87092175 -> '4d423837303932313735' (hex of 'MB' + id)."""
    return ("MB" + str(decimal_id)).encode("ascii").hex()


def decode_id(hex_id):
    """'4d423837303932313735' -> '87092175'; None when it is not an MB id."""
    try:
        raw = bytes.fromhex(hex_id).decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return None
    if raw.startswith("MB") and raw[2:].isdigit():
        return raw[2:]
    return None


def _host_is_magicbricks(url):
    host = (urlparse(url).hostname or "").lower()
    return host == "magicbricks.com" or host.endswith(".magicbricks.com")


def _as_link(value):
    if value.startswith("//"):
        return "https:" + value
    if value.startswith(("http://", "https://")):
        return value
    return None


def _resolve(value, link_re, what, example):
    value = (value or "").strip()
    if _DIGITS_RE.match(value):
        return value
    if _HEX_RE.match(value):
        decoded = decode_id(value)
        if decoded:
            return decoded
    url = _as_link(value)
    if url:
        if not _host_is_magicbricks(url):
            raise ValueError("Must be a magicbricks.com link.")
        match = link_re.search(url)
        if match:
            decoded = decode_id(match.group(1))
            if decoded:
                return decoded
        raise ValueError(f"Must be a magicbricks.com {what} link ({example}).")
    raise ValueError(f"Must be a numeric {what} id, its hex id or a magicbricks.com {what} link ({example}).")


def resolve_property(value):
    """Bare id (87092175), hex id (4d4238...) or a /propertyDetails/ link -> the id."""
    return _resolve(value, _LINK_PROPERTY_RE, "property",
                    f"{SITE}/propertyDetails/<slug>&id=4d423837303932313735")


def resolve_project(value):
    """Bare psmid (5336113), hex id or a -pdpid- / -nprid- link -> the psmid."""
    return _resolve(value, _LINK_PROJECT_RE, "project",
                    f"{SITE}/<slug>-pdpid-4d4235333336313133")


def resolve_agent(value):
    """Bare agent id (61979531), hex id or an -agentid- link -> the id."""
    return _resolve(value, _LINK_AGENT_RE, "agent",
                    f"{SITE}/top-agent-details/<slug>-agentid-4d423631393739353331")


def resolve_place(value):
    """A locality / city given by name or by the site's numeric id. Returns
    the stripped value; api.py sends an id as `locality=`/`city=` and a
    name as `Locality=`/`cityName=` (both accepted upstream)."""
    value = " ".join((value or "").split())
    if not value:
        raise ValueError("Must be a name or a numeric magicbricks.com id.")
    if len(value) > 80:
        raise ValueError("Too long (max 80 characters).")
    return value


def is_numeric_id(value):
    return bool(_DIGITS_RE.match(str(value or "")))


# ---- links -------------------------------------------------------------------------

def property_link(property_id, slug=None):
    """The canonical listing link; the slug is cosmetic (the site serves the
    page for any slug), so a search row's own slug is used when known."""
    return f"{SITE}/propertyDetails/{slug or 'property'}&id={encode_id(property_id)}"


def project_link(psmid, slug=None):
    if slug and "-pdpid-" in slug:
        return f"{SITE}/{slug.lstrip('/')}"
    return f"{SITE}/{slug or 'project'}-pdpid-{encode_id(psmid)}"


def rera_link(rera_slug):
    return f"{SITE}/{rera_slug.lstrip('/')}" if rera_slug else None


def agent_link(agent_id, slug=None):
    return f"{SITE}/top-agent-details/{slug or 'agent'}-agentid-{encode_id(agent_id)}"


def site_link(path):
    """A site-relative path or a bare slug -> absolute link (None stays None)."""
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    return f"{SITE}/{path.lstrip('/')}"


def place_slug(name):
    """'Andheri West' -> 'Andheri-West' for the /new-projects-* paths
    (case-insensitive upstream: /new-projects-mumbai == /new-projects-Mumbai)."""
    return "-".join(" ".join((name or "").split()).split(" "))


def projects_list_path(city, locality=None, page=1):
    """/new-projects-<City> or /new-projects-<Locality>-in-<City>, paged as
    /page-N (the '-page-N' suffix form answers 500 to non-Indian exits)."""
    if locality:
        path = f"/new-projects-{place_slug(locality)}-in-{place_slug(city)}"
    else:
        path = f"/new-projects-{place_slug(city)}"
    if page and page > 1:
        path += f"/page-{page}"
    return path


# ---- search vocab -------------------------------------------------------------------

LISTING_TYPES = {"sale": "S", "rent": "R"}

# public value -> the site's own `proptype=` slug (residential first).
PROPERTY_TYPES = {
    "apartment": "Multistorey-Apartment",
    "builder-floor": "Builder-Floor-Apartment",
    "penthouse": "Penthouse",
    "studio-apartment": "Studio-Apartment",
    "house": "Residential-House",
    "villa": "Villa",
    "plot": "Residential-Plot",
    "farm-house": "Farm-House",
    "service-apartment": "Service-Apartment",
    "office-space": "Commercial-Office-Space",
    "office-it-park": "Office-ITPark-SEZ",
    "shop": "Commercial-Shop",
    "showroom": "Commercial-Showroom",
    "commercial-land": "Commercial-Land",
    "industrial-land": "Industrial-Land",
    "warehouse": "Warehouse-Godown",
    "industrial-building": "Industrial-Building",
    "industrial-shed": "Industrial-Shed",
    "agricultural-land": "Agricultural-Land",
    "co-working": "Co-working-Space",
    "hotel": "Hotel",
    "guest-house": "Guest-House",
}

SORTS = {
    "relevance": "premiumRecent",
    "price_low_to_high": "Lowest_Price",
    "price_high_to_low": "Highest_Price",
    "newest": "postRecency",
    "rate_low_to_high": "Lowest_Sqft_Price",
    "rate_high_to_low": "Highest_Sqft_Price",
}

FURNISHING = {"furnished": "11900", "semi-furnished": "11902", "unfurnished": "11901"}
POSSESSION = {"ready-to-move": "10081", "under-construction": "10080"}

# /mbutility/trends/* propType codes (the locality page's radio values).
TRENDS_PROPERTY_TYPES = {
    "apartment": "10002", "builder-floor": "10003", "house": "10001",
    "plot": "10000", "office-space": "10007", "shop": "10008",
}

MAX_SEARCH_PAGE = 100   # page 101+ repeats page 1 upstream (2026-11-07)

# ---- id tables -----------------------------------------------------------------------

AMENITIES = {
    "12201": "Power Back Up", "12202": "Lift", "12203": "Rain Water Harvesting",
    "12204": "Club House", "12205": "Swimming Pool", "12206": "Gymnasium", "12207": "Park",
    "12208": "Reserved Parking", "12209": "Security", "12211": "Water Storage",
    "12214": "Service/Goods Lift", "12215": "Air Conditioned", "12216": "Visitor Parking",
    "12217": "Intercom Facility", "12218": "Maintenance Staff", "12219": "Waste Disposal",
    "12220": "Laundry Service", "12221": "Internet/Wi-Fi Connectivity",
    "12222": "DTH Television Facility", "12223": "RO Water System", "12224": "Banquet Hall",
    "12225": "Bar/Lounge", "12227": "Conference Room", "12228": "Piped Gas",
    "12229": "Jogging and Strolling Track", "12230": "Outdoor Tennis Courts",
    "12234": "Skyline View", "12513": "Marble flooring", "12521": "Private pool",
    "12522": "Private jaccuzi", "12523": "Mini Cinema Theatre",
    "12526": "Pool with temperature control", "12527": "Sea facing", "12528": "Skydeck",
    "12529": "High Ceiling", "12532": "Theme based Architectures", "12535": "Large Clubhouse",
    "12537": "Large Open space", "12539": "Grand Entrance lobby",
    "12540": "Premium branded fittings", "12541": "AC in each room", "12543": "Multipurpose Hall",
    "12547": "CCTV Camera", "12548": "Fire Sprinklers", "12556": "Fireplace", "12558": "Sky Villa",
    "12560": "Water Front", "12561": "Hilltop", "12562": "Smart Home", "12581": "Kids play area",
    "1404110": "Bank & ATM", "1404117": "Indoor Games Room", "1404120": "Kids Club",
    "1404146": "Sewage treatment plant",
}

LANDMARK_CATEGORIES = {
    "19201": "Commercial Hub", "19202": "Educational Institute", "19203": "Hospital",
    "19206": "Shopping Centre", "19207": "Tourist Spot", "19210": "Transportation Hub",
}
