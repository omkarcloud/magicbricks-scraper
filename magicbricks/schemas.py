"""Marshmallow request schemas for every /magicbricks/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    property   a listing id (87092175), its hex id (4d4238...) OR any
               magicbricks.com /propertyDetails/ link
    project    a project id (5336113), its hex id OR a -pdpid- / -nprid- link
    agent      an agent id (61979531), its hex id OR an -agentid- link
    city       a city name ("Mumbai", "Navi Mumbai") or the site's city code (4320)
    locality   a locality name ("Juhu", "Andheri West") or the site's id (60166)

Choice vocab (magicbricks/refs.py): listing_type sale|rent; property_type
the 22 public names mapped to the site's own slugs; sort relevance |
price_low_to_high | price_high_to_low | newest | rate_low_to_high |
rate_high_to_low; furnishing furnished | semi-furnished | unfurnished;
possession ready-to-move | under-construction.
"""
from marshmallow import ValidationError, validates_schema

from schema_fields import (
    BaseSchema, ChoiceField, CommaListField, PageField, PositiveInt, QueryField, RefField, StrippedString,
)
from magicbricks import refs


class PropertyRefField(RefField):
    resolver = staticmethod(refs.resolve_property)


class ProjectRefField(RefField):
    resolver = staticmethod(refs.resolve_project)


class AgentRefField(RefField):
    resolver = staticmethod(refs.resolve_agent)


class PlaceField(RefField):
    """A locality / city by name or by the site's numeric id."""
    resolver = staticmethod(refs.resolve_place)


def _listing_type():
    # a zero-arg field factory, so the listing tooling (derive_facts) reads
    # its choices as the param's enum
    return ChoiceField(refs.LISTING_TYPES, load_default=refs.LISTING_TYPES["sale"], metadata={
        "description": "sale (buy) or rent listings (default sale)"})


class LocationsSearchSchema(BaseSchema):
    query = QueryField(max_length=80, metadata={
        "description": "text to autocomplete: a city, locality, project or landmark name"})
    city = PlaceField(required=False, load_default=None, metadata={
        "description": "optional city name or code to narrow locality / project suggestions to"})


class PropertiesSearchSchema(BaseSchema):
    city = PlaceField(metadata={"description": "city name (Mumbai, Bangalore, Navi Mumbai) or magicbricks city code"})
    listing_type = _listing_type()
    locality = StrippedString(load_default=None, metadata={
        "description": "comma list of locality names or ids inside the city (Juhu,Bandra West)"})
    property_type = CommaListField(value_map=refs.PROPERTY_TYPES, max_items=22, metadata={
        "description": "comma list of: " + ", ".join(refs.PROPERTY_TYPES)})
    bedrooms = CommaListField(allowed=[str(n) for n in range(1, 12)], max_items=11, metadata={
        "description": "comma list of BHK counts (1..11), e.g. 2,3"})
    min_price = PositiveInt(metadata={"description": "minimum price in INR (monthly rent for rent listings)"})
    max_price = PositiveInt(metadata={"description": "maximum price in INR"})
    min_area = PositiveInt(metadata={"description": "minimum area in sq ft"})
    max_area = PositiveInt(metadata={"description": "maximum area in sq ft"})
    furnishing = ChoiceField(refs.FURNISHING, metadata={
        "description": "furnished | semi-furnished | unfurnished"})
    possession = ChoiceField(refs.POSSESSION, metadata={
        "description": "ready-to-move | under-construction (sale listings)"})
    keyword = StrippedString(load_default=None, metadata={
        "description": "free-text filter on the listing text (project name, 'sea view', a landmark)"})
    sort = ChoiceField(refs.SORTS, load_default=refs.SORTS["relevance"], metadata={
        "description": "relevance (default) | price_low_to_high | price_high_to_low | newest | "
                       "rate_low_to_high | rate_high_to_low (₹ per sq ft)"})
    page = PageField(max_page=refs.MAX_SEARCH_PAGE, metadata={
        "description": "1-based page of 30 listings (the site serves at most 100 pages per search)"})

    @validates_schema
    def _ranges(self, data, **kwargs):
        if data.get("min_price") and data.get("max_price") and data["min_price"] > data["max_price"]:
            raise ValidationError("min_price must not exceed max_price.", "min_price")
        if data.get("min_area") and data.get("max_area") and data["min_area"] > data["max_area"]:
            raise ValidationError("min_area must not exceed max_area.", "min_area")
        locality = data.get("locality")
        if locality is not None and len(locality) > 200:
            raise ValidationError("Too long (max 200 characters).", "locality")


class PropertySchema(BaseSchema):
    property = PropertyRefField(metadata={
        "description": "listing id (87092175), its hex id, or a magicbricks.com property link"})


class ProjectsSearchSchema(BaseSchema):
    city = PlaceField(metadata={"description": "city name (Mumbai, Pune, New Delhi) or magicbricks city code"})
    locality = PlaceField(required=False, load_default=None, metadata={
        "description": "optional locality name inside the city (Andheri West)"})
    page = PageField(max_page=500, metadata={"description": "1-based page of 20 projects"})


class ProjectSchema(BaseSchema):
    project = ProjectRefField(metadata={
        "description": "project id (5336113), its hex id, or a magicbricks.com project link"})


class ProjectListingsSchema(BaseSchema):
    project = ProjectRefField(metadata={
        "description": "project id (5336113), its hex id, or a magicbricks.com project link"})
    listing_type = _listing_type()
    page = PageField(max_page=refs.MAX_SEARCH_PAGE, metadata={"description": "1-based page of 30 listings"})


class AgentsSearchSchema(BaseSchema):
    city = PlaceField(required=False, load_default=None, metadata={
        "description": "city name or code (required unless locality is given)"})
    locality = PlaceField(required=False, load_default=None, metadata={
        "description": "locality name or id; narrows the ranking to agents operating there"})
    listing_type = _listing_type()

    @validates_schema
    def _place_required(self, data, **kwargs):
        if not data.get("city") and not data.get("locality"):
            raise ValidationError("Give a city or a locality.", "city")


class AgentListingsSchema(BaseSchema):
    agent = AgentRefField(metadata={
        "description": "agent id (61979531), its hex id, or a magicbricks.com agent link"})
    city = PlaceField(required=False, load_default=None, metadata={
        "description": "optional city name or code to limit the agent's listings to"})
    listing_type = _listing_type()
    page = PageField(max_page=refs.MAX_SEARCH_PAGE, metadata={"description": "1-based page of 30 listings"})


class LocalityTrendsSchema(BaseSchema):
    locality = PlaceField(metadata={
        "description": "locality name (Juhu) or magicbricks locality id (60166)"})
    city = PlaceField(required=False, load_default=None, metadata={
        "description": "city name or code, to pick the right locality when the name exists in several cities"})
    listing_type = _listing_type()
    property_type = ChoiceField(refs.TRENDS_PROPERTY_TYPES, load_default=refs.TRENDS_PROPERTY_TYPES["apartment"],
                                metadata={"description": "apartment (default) | builder-floor | house | plot | "
                                                         "office-space | shop"})
