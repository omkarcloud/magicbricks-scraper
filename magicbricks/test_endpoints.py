"""Live endpoint smoke tests: one call per /magicbricks/* route against a
running service, with example values proven to return data (2026-11-07).
The listing tooling (derive_facts.py) reads the FIRST call per path as that
route's working example, so the first call of each test is the public
example: Lodha World One (Worli, Mumbai) and a 5 BHK flat on its upper
floors, the agency that lists it, Bandra.

Listings expire about 60 days after their last renewal, so the example
listing is an old id its agent keeps renewing (63567183 against ~87M for
listings posted in Nov 2026); swap it here when it 404s.

Skipped unless MAGICBRICKS_BASE points at a running service:

    ONLY_SCRAPER=magicbricks python run.py --dev
    MAGICBRICKS_BASE=http://127.0.0.1:6002 python -m pytest magicbricks/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("MAGICBRICKS_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set MAGICBRICKS_BASE to run live endpoint tests")


def call(path, status=200, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == status, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


# ---- properties ---------------------------------------------------------------------

def test_property_details():
    flat = call("/magicbricks/properties/details", property="63567183")
    assert flat["id"] == "63567183" and "Lodha World One" in flat["title"]
    assert flat["price"]["amount"] and flat["price"]["currency"] == "INR" and flat["bedrooms"] == 5
    assert flat["area"]["carpet"]["value"] and flat["amenities"] and flat["images"]["all"]
    assert flat["project"]["id"] == "5070869" and flat["lister"]["company"]
    assert flat["lister"]["phone"] is None and flat["nearby_places"] and flat["price_trend"]
    link = "https://www.magicbricks.com/propertyDetails/x&id=4d423633353637313833"
    assert call("/magicbricks/properties/details", property=link)["id"] == "63567183"
    call("/magicbricks/properties/details", status=404, property="19999999")
    call("/magicbricks/properties/details", status=400, property="lodha")


def test_property_similar():
    body = call("/magicbricks/properties/similar", property="63567183")
    assert body["similar_count"] > 10 and body["similar"][0]["id"] and body["similar"][0]["price"]["amount"]


def test_locations_search():
    body = call("/magicbricks/locations/search", query="bandra")
    names = {(r["type"], r["name"]) for r in body["results"]}
    assert ("locality", "Bandra West") in names
    world_one = call("/magicbricks/locations/search", query="world one", city="Mumbai")["results"]
    assert any(r["type"] == "project" and r["id"] == "5070869" for r in world_one)


def test_properties_search():
    body = call("/magicbricks/properties/search", city="Mumbai")
    assert body["count"] > 10000 and len(body["results"]) == 30 and body["next"]
    row = body["results"][0]
    assert row["id"] and row["link"] and row["price"]["amount"] and row["location"]["city"]["name"] == "Mumbai"
    juhu = call("/magicbricks/properties/search", city="Mumbai", locality="Juhu", property_type="apartment",
                bedrooms="3", sort="price_low_to_high")
    prices = [r["price"]["amount"] for r in juhu["results"] if r["price"]["amount"]]
    assert juhu["localities"][0]["name"] == "Juhu" and prices == sorted(prices)
    rent = call("/magicbricks/properties/search", city="Bangalore", listing_type="rent", furnishing="furnished",
                min_price="30000", max_price="80000")
    assert rent["listing_type"] == "rent" and all(30000 <= r["price"]["amount"] <= 80000 for r in rent["results"])
    call("/magicbricks/properties/search", status=404, city="Atlantis")
    call("/magicbricks/properties/search", status=404, city="Mumbai", locality="Nowhereville")
    call("/magicbricks/properties/search", status=400, city="Mumbai", property_type="castle")


# ---- projects -----------------------------------------------------------------------

def test_projects_search():
    body = call("/magicbricks/projects/search", city="Mumbai")
    assert body["count"] > 1000 and len(body["results"]) == 20 and body["next"]
    assert body["results"][0]["id"] and body["results"][0]["developer"]["name"]
    andheri = call("/magicbricks/projects/search", city="Mumbai", locality="Andheri West", page="2")
    assert andheri["results"] and andheri["current_page"] == 2
    call("/magicbricks/projects/search", status=404, city="Atlantis")


def test_project_details():
    body = call("/magicbricks/projects/details", project="5070869")
    assert body["name"] == "Lodha World One" and body["developer"]["name"].startswith("Lodha")
    assert body["total_units"] and body["amenities"] and body["rera"]["ids"] and body["faqs"]
    call("/magicbricks/projects/details", status=404, project="1234567")


def test_project_listings():
    body = call("/magicbricks/projects/listings", project="5070869")
    assert body["count"] and body["results"][0]["project"]["id"] == "5070869"
    rent = call("/magicbricks/projects/listings", project="5070869", listing_type="rent")
    assert rent["listing_type"] == "rent" and rent["results"]
    call("/magicbricks/projects/listings", status=404, project="1234567")


def test_project_reviews():
    body = call("/magicbricks/projects/reviews", project="5070869")
    assert body["reviews"]["count"] and body["reviews"]["results"][0]["text"]
    assert body["locality_reviews"]["count"]


def test_project_rera():
    body = call("/magicbricks/projects/rera", project="5070869")
    assert body["registrations"] and body["document_groups"]
    assert body["document_groups"][0]["documents"][0]["link"].endswith(".pdf")


# ---- agents -------------------------------------------------------------------------

def test_agents_search():
    body = call("/magicbricks/agents/search", city="Mumbai")
    assert body["count"] > 50 and body["results"][0]["name"] and body["results"][0]["link"]
    juhu = call("/magicbricks/agents/search", city="Mumbai", locality="Juhu", listing_type="rent")
    assert juhu["locality"]["id"] == "60166"
    call("/magicbricks/agents/search", status=400)


def test_agent_listings():
    body = call("/magicbricks/agents/listings", agent="27202575")
    assert body["count"] > 10 and body["results"][0]["lister"]["id"] == "27202575"
    mumbai = call("/magicbricks/agents/listings", agent="27202575", city="Mumbai", listing_type="rent")
    assert mumbai["listing_type"] == "rent"
    call("/magicbricks/agents/listings", status=400, agent="x")


# ---- localities ---------------------------------------------------------------------

def test_locality_trends():
    body = call("/magicbricks/localities/trends", locality="Bandra West")
    assert body["locality"]["id"] == "78839" and len(body["quarters"]) >= 12
    assert body["series"][0]["values"][-1]
    rent = call("/magicbricks/localities/trends", locality="60166", listing_type="rent")
    assert rent["listing_type"] == "rent" and rent["series"]
    call("/magicbricks/localities/trends", status=404, locality="Nowhereville")
