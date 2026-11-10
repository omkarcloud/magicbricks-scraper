"""Offline tests for the /magicbricks/* request schemas.

    python -m pytest magicbricks/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from magicbricks import refs, schemas  # noqa: E402


def _error(schema, data):
    with pytest.raises(ValidationError) as info:
        schema().load(data)
    return info.value.normalized_messages()


# ---- one param per input -------------------------------------------------------------------

def test_property_schema_accepts_id_hex_and_link():
    assert schemas.PropertySchema().load({"property": "87092175"}) == {"property": "87092175"}
    assert schemas.PropertySchema().load({"property": "4d423837303932313735"}) == {"property": "87092175"}
    link = "https://www.magicbricks.com/propertyDetails/3-BHK-Flat-FOR-Sale-Juhu-in-Mumbai&id=4d423837303932313735"
    assert schemas.PropertySchema().load({"property": link}) == {"property": "87092175"}


@pytest.mark.parametrize("value", ["", "juhu", "https://example.com/propertyDetails/x&id=4d423837303932313735"])
def test_property_schema_rejects(value):
    errors = _error(schemas.PropertySchema, {"property": value})
    assert "property" in errors
    if value:
        assert "magicbricks.com" in errors["property"][0]


def test_property_schema_rejects_sibling_params():
    errors = _error(schemas.PropertySchema, {"property": "87092175", "id": "87092175"})
    assert "id" in errors


def test_project_schema():
    assert schemas.ProjectSchema().load({"project": "5336113"}) == {"project": "5336113"}
    assert schemas.ProjectSchema().load(
        {"project": "https://www.magicbricks.com/shelton-elite-juhu-mumbai-pdpid-4d4235333336313133"}) == {"project": "5336113"}
    assert "project" in _error(schemas.ProjectSchema, {"project": "shelton elite"})


def test_agent_schema():
    loaded = schemas.AgentListingsSchema().load({"agent": "4d423631393739353331"})
    assert loaded == {"agent": "61979531", "city": None, "listing_type": "S", "page": 1}
    loaded = schemas.AgentListingsSchema().load({"agent": "61979531", "listing_type": "Rent", "city": "Mumbai", "page": "2"})
    assert loaded["listing_type"] == "R" and loaded["city"] == "Mumbai" and loaded["page"] == 2
    assert "agent" in _error(schemas.AgentListingsSchema, {"agent": "viraj"})


# ---- properties/search --------------------------------------------------------------------

def test_search_schema_defaults():
    loaded = schemas.PropertiesSearchSchema().load({"city": " Mumbai "})
    assert loaded["city"] == "Mumbai" and loaded["listing_type"] == "S" and loaded["sort"] == "premiumRecent"
    assert loaded["page"] == 1 and loaded["property_type"] is None and loaded["bedrooms"] is None
    assert loaded["min_price"] is None and loaded["furnishing"] is None


def test_search_schema_maps_choices_to_site_tokens():
    loaded = schemas.PropertiesSearchSchema().load({
        "city": "4320", "listing_type": "rent", "locality": "Juhu, Bandra West",
        "property_type": "Apartment,villa", "bedrooms": "2,3", "min_price": "50000", "max_price": "200000",
        "min_area": "1000", "max_area": "2000", "furnishing": "Semi-Furnished",
        "possession": "ready-to-move", "keyword": "sea view", "sort": "price_low_to_high", "page": "3"})
    assert loaded["listing_type"] == "R"
    assert loaded["property_type"] == ["Multistorey-Apartment", "Villa"]
    assert loaded["bedrooms"] == ["2", "3"]
    assert loaded["furnishing"] == "11902" and loaded["possession"] == "10081"
    assert loaded["sort"] == "Lowest_Price" and loaded["page"] == 3
    assert loaded["min_price"] == 50000 and loaded["max_area"] == 2000
    assert loaded["locality"] == "Juhu, Bandra West" and loaded["keyword"] == "sea view"


@pytest.mark.parametrize("data,field", [
    ({}, "city"),
    ({"city": "Mumbai", "listing_type": "lease"}, "listing_type"),
    ({"city": "Mumbai", "property_type": "castle"}, "property_type"),
    ({"city": "Mumbai", "bedrooms": "0"}, "bedrooms"),
    ({"city": "Mumbai", "bedrooms": "12"}, "bedrooms"),
    ({"city": "Mumbai", "min_price": "-5"}, "min_price"),
    ({"city": "Mumbai", "min_price": "100", "max_price": "50"}, "min_price"),
    ({"city": "Mumbai", "min_area": "900", "max_area": "100"}, "min_area"),
    ({"city": "Mumbai", "furnishing": "bare"}, "furnishing"),
    ({"city": "Mumbai", "sort": "cheapest"}, "sort"),
    ({"city": "Mumbai", "page": "101"}, "page"),
    ({"city": "Mumbai", "page": "0"}, "page"),
    ({"city": "Mumbai", "url": "https://www.magicbricks.com/x"}, "url"),
])
def test_search_schema_rejects(data, field):
    errors = _error(schemas.PropertiesSearchSchema, data)
    assert field in errors, errors


def test_search_schema_property_type_message_lists_choices():
    errors = _error(schemas.PropertiesSearchSchema, {"city": "Mumbai", "property_type": "castle"})
    assert "apartment" in errors["property_type"][0] and "warehouse" in errors["property_type"][0]


# ---- the rest ------------------------------------------------------------------------------

def test_locations_schema():
    assert schemas.LocationsSearchSchema().load({"query": "juhu"}) == {"query": "juhu", "city": None}
    assert schemas.LocationsSearchSchema().load({"query": "juhu", "city": "4320"})["city"] == "4320"
    assert "query" in _error(schemas.LocationsSearchSchema, {})
    assert "query" in _error(schemas.LocationsSearchSchema, {"query": "x" * 81})


def test_projects_search_schema():
    assert schemas.ProjectsSearchSchema().load({"city": "Mumbai"}) == {"city": "Mumbai", "locality": None, "page": 1}
    loaded = schemas.ProjectsSearchSchema().load({"city": "Mumbai", "locality": "Andheri  West", "page": "4"})
    assert loaded["locality"] == "Andheri West" and loaded["page"] == 4
    assert "city" in _error(schemas.ProjectsSearchSchema, {"page": "2"})


def test_project_listings_schema():
    loaded = schemas.ProjectListingsSchema().load({"project": "5336113", "listing_type": "RENT"})
    assert loaded == {"project": "5336113", "listing_type": "R", "page": 1}


def test_agents_schema_needs_a_place():
    assert schemas.AgentsSearchSchema().load({"city": "Mumbai"}) == {"city": "Mumbai", "locality": None, "listing_type": "S"}
    assert schemas.AgentsSearchSchema().load({"locality": "60166"})["locality"] == "60166"
    assert "city" in _error(schemas.AgentsSearchSchema, {})
    assert "city" in _error(schemas.AgentsSearchSchema, {"listing_type": "rent"})


def test_trends_schema():
    loaded = schemas.LocalityTrendsSchema().load({"locality": "Juhu"})
    assert loaded == {"locality": "Juhu", "city": None, "listing_type": "S", "property_type": "10002"}
    loaded = schemas.LocalityTrendsSchema().load({"locality": "60166", "city": "Mumbai", "listing_type": "rent",
                                                  "property_type": "house"})
    assert loaded["property_type"] == "10001" and loaded["listing_type"] == "R"
    assert "property_type" in _error(schemas.LocalityTrendsSchema, {"locality": "Juhu", "property_type": "castle"})
    assert "locality" in _error(schemas.LocalityTrendsSchema, {})


def test_every_property_type_has_a_site_slug():
    assert len(refs.PROPERTY_TYPES) == 22
    assert all("-" in slug or slug.isalpha() for slug in refs.PROPERTY_TYPES.values())
