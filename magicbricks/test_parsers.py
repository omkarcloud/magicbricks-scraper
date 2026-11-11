"""Offline tests for the Magicbricks parsers, reference resolvers and
value helpers.

    python -m pytest magicbricks/test_parsers.py -q

Fixtures are real www.magicbricks.com responses captured 2026-11-07
(magicbricks/fixtures/, HTML pages trimmed to their <title>, ld+json and
state <script> blocks): search JSON (sale / rent / commercial / empty), a
sale listing in a project, a rent listing, a commercial listing, the
search-page fallback an unknown id serves, a project page, two
new-projects pages, a RERA page, the Mumbai top-agents fragment, two
autosuggest payloads, a trends series + table. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from magicbricks import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


@pytest.fixture(scope="module")
def sale():
    return P.parse_property(fixture("property_sale_juhu.html"), "87092175")


@pytest.fixture(scope="module")
def rent():
    return P.parse_property(fixture("property_rent_bangalore.html"), "79239359")


@pytest.fixture(scope="module")
def commercial():
    return P.parse_property(fixture("property_commercial_mumbai.html"), "87109047")


@pytest.fixture(scope="module")
def project():
    return P.parse_project(fixture("project_shelton_elite.html"), "5336113")


# ---- refs ----------------------------------------------------------------------------------

def test_hex_ids_round_trip():
    assert refs.encode_id("87092175") == "4d423837303932313735"
    assert refs.decode_id("4d423837303932313735") == "87092175"
    assert refs.decode_id("4d42") is None
    assert refs.decode_id("zz") is None


@pytest.mark.parametrize("value,expected", [
    ("87092175", "87092175"),
    ("4d423837303932313735", "87092175"),
    ("4D423837303932313735", "87092175"),
    ("https://www.magicbricks.com/propertyDetails/3-BHK-Flat-FOR-Sale-Juhu-in-Mumbai&id=4d423837303932313735", "87092175"),
    ("https://magicbricks.com/propertyDetails/x&id=4d423837303932313735&category=Sale", "87092175"),
])
def test_resolve_property(value, expected):
    assert refs.resolve_property(value) == expected


@pytest.mark.parametrize("value", [
    "", "juhu flat", "https://example.com/propertyDetails/x&id=4d423837303932313735",
    "https://www.magicbricks.com/shelton-elite-juhu-mumbai-pdpid-4d4235333336313133",
    "4d4258",   # hex that is not an MB id
])
def test_resolve_property_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_property(value)


@pytest.mark.parametrize("value,expected", [
    ("5336113", "5336113"),
    ("4d4235333336313133", "5336113"),
    ("https://www.magicbricks.com/shelton-elite-juhu-mumbai-pdpid-4d4235333336313133", "5336113"),
    ("https://www.magicbricks.com/shelton-elite-rera-details-nprid-4d4235333336313133", "5336113"),
])
def test_resolve_project(value, expected):
    assert refs.resolve_project(value) == expected


def test_resolve_agent():
    assert refs.resolve_agent("61979531") == "61979531"
    assert refs.resolve_agent(
        "http://www.magicbricks.com/top-agent-details/company-majestic-properties-in-mumbai-agentid-4d423631393739353331") == "61979531"
    with pytest.raises(ValueError):
        refs.resolve_agent("https://www.magicbricks.com/propertyDetails/x&id=4d423837303932313735")


def test_resolve_place():
    assert refs.resolve_place("  Andheri   West ") == "Andheri West"
    assert refs.resolve_place("60166") == "60166"
    with pytest.raises(ValueError):
        refs.resolve_place("  ")


def test_projects_list_path():
    assert refs.projects_list_path("Mumbai") == "/new-projects-Mumbai"
    assert refs.projects_list_path("Navi Mumbai", page=3) == "/new-projects-Navi-Mumbai/page-3"
    assert refs.projects_list_path("Mumbai", "Andheri West", 2) == "/new-projects-Andheri-West-in-Mumbai/page-2"


def test_links():
    assert refs.property_link("87092175") == "https://www.magicbricks.com/propertyDetails/property&id=4d423837303932313735"
    assert refs.project_link("5336113") == "https://www.magicbricks.com/project-pdpid-4d4235333336313133"
    assert refs.project_link("5336113", "shelton-elite-juhu-mumbai-pdpid-4d4235333336313133").endswith("juhu-mumbai-pdpid-4d4235333336313133")
    assert refs.agent_link("61979531").endswith("-agentid-4d423631393739353331")


# ---- value helpers ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2026-11-06T17:38:09.000Z", "2026-11-06T17:38:09Z"),
    ("2026-10-31T08:01:58.000+00:00", "2026-10-31T08:01:58Z"),
    ("2027-03-01 00:00:00", "2027-03-01"),
    ("20270301", "2027-03-01"),
    ("27/10/2026", "2026-10-27"),
    ("Nov 06, '2026", "2026-11-06"),
    ("Aug 01, '24", "2024-08-01"),
    ("05 Nov 26", "2026-11-05"),
    ("07 November 2026", "2026-11-07"),
    ("Mar '27", "2027-03"),
    ("Mar, 2027", "2027-03"),
    ("Sep 2022", "2022-09"),
    ("Oct-26", "2026-10"),
    ("Oct'26", "2026-10"),
    ("NA", None), ("", None), (None, None), ("Immediately", None),
    (1793986689000, "2026-11-06T17:38:09Z"),
])
def test_iso_date(value, expected):
    assert P.iso_date(value) == expected


def test_number_helpers():
    assert P.to_int("1,128") == 1128
    assert P.to_int("6.76 Cr") == 6
    assert P.to_float("51.0") == 51.0
    assert P.positive("0") is None
    assert P.positive(0.0) is None
    assert P.yn("Y") is True and P.yn("N") is False and P.yn("Z") is None and P.yn(None) is None
    assert P.clean("  a   b ") == "a b"
    assert P.clean("null") is None


def test_extract_state_handles_missing_and_garbage():
    assert P.extract_state("<html></html>", "SERVER_PRELOADED_STATE_") is None
    assert P.extract_state("window.SERVER_PRELOADED_STATE_ = {broken", "SERVER_PRELOADED_STATE_") is None
    assert P.extract_state('x window.K = {"a": [1, {"b": "}"}]}; y', "K") == {"a": [1, {"b": "}"}]}


# ---- search -----------------------------------------------------------------------------------

def test_parse_search_sale():
    out = P.parse_search(fixture("search_sale_juhu_3bhk.json"))
    assert out["total_count"] == 259 and out["total_pages"] == 9 and out["items_per_page"] == 30
    assert out["city"] == {"id": "4320", "name": "Mumbai"}
    assert out["localities"] == [{"id": "60166", "name": "Juhu"}]
    assert out["summary"] == "3 BHK - 3 BHK Apartments for Sale in Juhu"
    assert len(out["results"]) == 30
    row = out["results"][0]
    assert row["id"] == "86927567"
    assert row["link"] == ("https://www.magicbricks.com/propertyDetails/"
                           "3-BHK-1600-Sq-ft-Multistorey-Apartment-FOR-Sale-Juhu-in-Mumbai&id=4d423836393237353637")
    assert row["listing_type"] == "sale" and row["property_type"] == "Apartment"
    assert row["transaction_type"] == "New Property"
    assert row["price"]["amount"] == 83200000 and row["price"]["currency"] == "INR"
    assert row["price"]["display"] == "8.32 Cr" and row["price"]["per_sqft"] == 52000.0
    assert row["price"]["maintenance"] == {"amount": 22500, "currency": "INR", "period": "monthly",
                                           "is_per_sqft": False}
    assert row["price"]["booking_amount"] == 500000
    assert row["bedrooms"] == 3 and row["bathrooms"] == 3 and row["balconies"] == 1
    assert row["area"]["carpet"] == {"value": 1500.0, "unit": "sqft"}
    assert row["area"]["covered"] == {"value": 1600.0, "unit": "sqft"}
    assert row["furnishing"] == "unfurnished"
    assert row["floor"] == {"number": 11, "total": 11, "display": "11 of 11 Floor"}
    assert row["facing"] == "West" and row["overlooking"] == "Main Road"
    assert row["possession"]["status"] == "Ready to Move"
    assert row["ownership"] == "Co-operative Society" and row["parking"] == "2 Covered"
    assert row["location"]["locality"] == {"id": "60166", "name": "Juhu"}
    assert row["location"]["city"] == {"id": "4320", "name": "Mumbai"}
    assert row["location"]["latitude"] == pytest.approx(19.0982677) and row["location"]["landmark"] == "JUHU GULMOHAR ROAD"
    assert {"id": "12201", "name": "Power Back Up"} in row["amenities"]
    assert {"id": "12224", "name": "Banquet Hall"} in row["amenities"]
    assert row["landmarks"][0] == {"id": "160529", "name": "Juhu Beach Bus Stop", "category": "Transportation Hub",
                                   "distance_km": None}
    assert row["lister"]["name"] == "Jigar" and row["lister"]["company"] == "Dedhia Realtors"
    assert row["lister"]["type"] == "Agent" and row["lister"]["operating_since"] == 1993
    assert row["lister"]["is_rera_agent"] is True and row["lister"]["rera_id"] == "A5100000376"
    assert row["lister"]["link"].endswith("-agentid-" + refs.encode_id("4668587"))
    assert row["images"]["count"] == 12 and len(row["images"]["all"]) == 7
    assert row["images"]["cover"].startswith("https://img.staticmb.com/")
    assert row["is_verified"] is False
    assert row["posted_on"] == "2026-11-06T23:45:16Z" and row["expires_on"] == "2027-01-05T23:45:16Z"
    assert row["posted_label"] == "Posted Today"


def test_parse_search_rent_row_has_rent_fields_and_project():
    out = P.parse_search(fixture("search_rent_bangalore.json"))
    row = out["results"][0]
    assert row["listing_type"] == "rent"
    assert row["price"]["amount"] == 210000 and row["price"]["display"] == "2.1 Lac"
    assert row["tenant_preference"] == "Bachelors/Family"
    assert row["project"]["id"] == "5038429" and row["project"]["name"] == "Century Ethos"
    assert row["project"]["link"] == "https://www.magicbricks.com/century-ethos-hebbal-bangalore-pdpid-4d4235303338343239"
    assert row["project"]["developer"] == "Century Real Estate"
    assert row["project"]["rera_ids"] == ["PRM/KA/RERA/1251/309/PR/171014/000283"]
    assert row["possession"]["status"] == "Immediately"
    assert row["location"]["address"] == "Bellary Road, NH44, Opposite Sahakaranagar, Bengaluru, Karnataka"
    assert out["city"]["name"] == "Bangalore"


def test_parse_search_commercial():
    out = P.parse_search(fixture("search_commercial_mumbai.json"))
    assert out["total_count"] > 1000
    row = out["results"][0]
    assert row["property_type"] == "Commercial Office Space"
    assert row["bedrooms"] is None
    assert row["price"]["amount"]


def test_parse_search_empty_page():
    out = P.parse_search(fixture("search_empty.json"))
    assert out["results"] == [] and out["total_count"] == 0 and out["total_pages"] == 0
    assert out["city"]["name"] == "Mumbai"


def test_parse_search_never_crashes_on_sparse_rows():
    out = P.parse_search({"resultList": [{}, {"id": "1", "price": "x", "ltcoordGeo": "a,b"}, "junk"],
                          "editAdditionalDataBean": {"cityName": None}})
    assert len(out["results"]) == 2
    assert out["results"][1]["id"] == "1" and out["results"][1]["price"]["amount"] is None
    assert out["results"][1]["location"]["latitude"] is None
    assert out["city"] == {"id": None, "name": None}
    assert P.parse_search(None)["results"] == []


# ---- property page -------------------------------------------------------------------------

def test_parse_property_sale(sale):
    assert sale["id"] == "87092175"
    assert sale["link"].startswith("https://www.magicbricks.com/propertyDetails/3-BHK-1128-Sq-ft")
    assert sale["title"] == "3 BHK 1128 Sqft Flat for Sale in Shelton Elite Juhu Mumbai"
    assert sale["listing_type"] == "sale" and sale["property_type"] == "Multistorey Apartment"
    assert sale["transaction_type"] == "New Property"
    assert sale["price"]["amount"] == 67672000 and sale["price"]["display"] == "6.76 Cr"
    assert sale["price"]["per_sqft"] == 59993     # price / carpet area, the site's own carpetAreaSqft figure
    assert sale["price"]["market_estimate"] == 67600000 and sale["price"]["emi_per_month"] == 234274
    assert sale["price"]["includes_other_charges"] is False
    assert sale["bedrooms"] == 3 and sale["bathrooms"] == 3
    assert sale["area"]["carpet"] == {"value": 1128.0, "unit": "sqft"} and sale["area"]["covered"] is None
    assert sale["furnishing"] == "unfurnished"
    assert sale["possession"] == {"status": "Under Construction", "available_from": "2027-03"}
    assert sale["age"] == "Under Construction"
    assert sale["location"]["locality"] == {"id": "60166", "name": "Juhu"}
    assert sale["location"]["city"] == {"id": "4320", "name": "Mumbai"}
    assert sale["location"]["address"] == "Juhu, Mumbai - Western Mumbai, Maharashtra"
    assert sale["location"]["latitude"] == pytest.approx(19.1136376)
    assert sale["location"]["locality_video"] == "https://www.youtube.com/watch?v=ZgbJ_R_8PEk"
    assert sale["project"]["id"] == "5336113" and sale["project"]["name"] == "Shelton Elite"
    assert sale["project"]["link"] == "https://www.magicbricks.com/shelton-elite-juhu-mumbai-pdpid-4d4235333336313133"
    assert sale["project"]["developer"] == "Shelton Groups" and sale["project"]["total_units"] == 31
    assert sale["project"]["possession_by"] == "2027-03" and sale["project"]["launched"] == "2022-09"
    assert sale["project"]["brochure"].endswith("Shelton-Elite-Brochure.pdf")
    assert sale["project"]["rating"] == 4.7 and sale["project"]["ratings"]["water"] == 4.0
    assert sale["rera_ids"] == ["P51800046724"]
    assert {"id": "12202", "name": "Lift"} in sale["amenities"] and len(sale["amenities"]) == 6
    assert sale["images"]["count"] == 30 and len(sale["images"]["all"]) == 5
    lister = sale["lister"]
    assert lister["name"] == "Desai Rakesh" and lister["company"] == "Tejasvi Realty Pvt. Ltd."
    assert lister["type"] == "Agent" and lister["operating_since"] == 1969
    assert lister["phone"] is None and lister["email"] is None     # OTP-gated upstream
    assert lister["rera_ids"] == ["A51800008122"] and lister["rating"] == 4.0
    assert lister["sale_listings"] == 192 and lister["rent_listings"] == 77
    assert lister["buyers_served"] == 12204 and lister["verified_properties"] == 31
    assert "Juhu" in [x for x in lister["operating_in"]]
    assert lister["link"].startswith("https://www.magicbricks.com/property-agent-details/")
    assert sale["nearby_places"][0]["category"] == "Educational Institute"
    assert isinstance(sale["nearby_places"][0]["distance_km"], float)
    assert sale["nearby_places"][0]["latitude"] and sale["nearby_places"][0]["longitude"]
    trend = sale["price_trend"]
    assert trend["unit"] == "INR per sqft" and len(trend["months"]) == 12 and trend["months"][0] == "2025-11"
    assert {s["name"] for s in trend["series"]} == {"Juhu", "Shelton Elite"}
    assert all(len(s["values"]) == 12 for s in trend["series"])
    assert sale["posted_on"] == "2026-11-06"
    assert len(sale["similar"]) == 60 and len(sale["also_viewed"]) == 5
    assert sale["similar"][0]["id"] and sale["similar"][0]["link"].startswith("https://www.magicbricks.com/propertyDetails/")
    assert sale["similar"][0]["price"]["amount"]


def test_parse_property_rent(rent):
    assert rent["id"] == "79239359" and rent["listing_type"] == "rent"
    assert rent["price"]["amount"] == 210000 and rent["price"]["display"] == "2.1 Lac"
    assert rent["price"]["per_sqft"] == 51.0
    assert rent["area"]["carpet"]["value"] == 3900.0 and rent["area"]["covered"]["value"] == 4100.0
    assert rent["furnishing"] == "semi-furnished"
    assert rent["floor"] == {"number": 20, "total": 21, "units_on_floor": None}
    assert rent["facing"] == "East" and rent["balconies"] == 2
    assert rent["additional_rooms"] == ["Puja Room", "Study", "Store", "Servant Room"]
    assert rent["overlooking"] == ["Garden/Park", "Pool", "Main Road"]
    assert rent["possession"]["status"] == "Immediately"
    assert rent["description"] == "Nice flat with a good ventilation."
    assert rent["amenities"] and all(a["name"] for a in rent["amenities"])
    assert rent["location"]["city"]["name"] == "Bangalore"


def test_parse_property_commercial(commercial):
    assert commercial["id"] == "87109047"
    assert commercial["property_type"] and "Office" in commercial["property_type"]
    assert commercial["bedrooms"] is None
    assert commercial["price"]["amount"]
    assert commercial["lister"]["name"]


def test_parse_property_world_one_charges_and_facilities():
    """The public example listing (captured 2026-11-10): charges the other
    fixtures lack, and facilitiesDesc names beyond amenityMap."""
    flat = P.parse_property(fixture("property_sale_world_one.html"), "63567183")
    assert flat["title"] == "5 BHK 5400 Sqft Flat for Sale in Lodha World One Worli Mumbai"
    price = flat["price"]
    assert price["amount"] == 420000000 and price["per_sqft"] == 77763.0 and "label" not in price
    assert price["maintenance"] == {"amount": 26, "currency": "INR", "period": "monthly", "is_per_sqft": False}
    assert price["booking_amount"] == 2500000 and price["brokerage"] == "1%"
    assert flat["floor"] == {"number": None, "total": 78, "units_on_floor": 2}
    assert flat["rera_authority_link"] == "https://maharera.mahaonline.gov.in/" and "rera_link" not in flat
    # 58 amenityMap ids + 32 luxAmenities ids named by luxuryAmenitiesMap + 12 facilitiesDesc
    # names matched to the one id the site's table gives them; every entry has an id and a name
    ids = [a["id"] for a in flat["amenities"]]
    assert len(ids) == len(set(ids)) == 102 and None not in ids
    assert all(a["name"] for a in flat["amenities"])
    assert {"id": "12205", "name": "Swimming Pool"} in flat["amenities"]       # amenityMap
    assert {"id": "12520", "name": "Helipad"} in flat["amenities"]             # luxuryAmenitiesMap
    assert {"id": "12544", "name": "Horticulture"} in flat["amenities"]        # facilitiesDesc + table
    # two site ids share these names; both are kept
    assert sorted(a["id"] for a in flat["amenities"] if a["name"] == "Concierge Services") == ["12239", "1404111"]
    assert flat["highlights"] == []
    assert flat["project"]["ratings"]["construction_quality"] == 4.5
    assert all(k == k.lower() for k in flat["project"]["ratings"])


def test_reviews_featured_copy_merged():
    """The site repeats a featured review at the top of the list without its ratings
    (Lodha World One, 2026-11-10): one entry per id, at the first position, ratings kept."""
    featured = {"reviewId": "1664677", "reviewTitle": "Iconic Sea View Apartments", "reviewDescription": "Lodha",
                "userType": "Owner", "userRelation": "Lives in Project", "postedOn": "03/02/2026",
                "reviewedOn": "27/10/2026", "isSponsered": "false"}
    other = {"reviewId": "1261879", "reviewTitle": "Nice project.", "userName": "Edal Jhaveri", "userType": "Agent",
             "postedOn": "19/03/2024", "reviewedOn": "19/03/2024"}
    original = dict(featured, overAllRating=5, reviewedOn="03/02/2026",
                    categoryRatingMap={"Project Infrastructure": {"Water Supply": 4}})
    out = P._reviews({"count": 3, "pageCount": 1, "resultList": [featured, other, original]})
    assert [r["id"] for r in out["results"]] == ["1664677", "1261879"]
    first = out["results"][0]
    assert first["rating"] == 5.0 and first["reviewed_on"] == "2026-02-03"
    assert first["category_ratings"] == {"project_infrastructure": {"water_supply": 4.0}}
    assert first["reviewer"]["relation"] == "Lives in Project"
    assert out["count"] == 3                     # the site's own count
    shelton = P.parse_project(fixture("project_shelton_elite.html"))
    for key in ("reviews", "locality_reviews"):
        ids = [r["id"] for r in shelton[key]["results"]]
        assert len(ids) == len(set(ids)), key


def test_rent_booking_field_is_the_deposit():
    """A rental's 'booking amount' is its security deposit (the rent page labels the same
    figure 'Security Deposit'): rent rows carry it as security_deposit, sale rows as booking_amount."""
    rent = P.parse_search(fixture("search_rent_bangalore.json"))["results"]
    with_deposit = [r for r in rent if r["price"]["security_deposit"]]
    assert with_deposit and all(r["price"]["booking_amount"] is None for r in rent)
    assert with_deposit[0]["price"]["security_deposit"] == 2000000 and with_deposit[0]["price"]["amount"] == 250000
    sale = P.parse_search(fixture("search_sale_juhu_3bhk.json"))["results"]
    assert any(r["price"]["booking_amount"] for r in sale)
    assert all(r["price"]["security_deposit"] is None for r in sale)
    assert P._booking_or_deposit("rent", None, "0", "24,00,000") == {"booking_amount": None, "security_deposit": 2400000}
    assert P._booking_or_deposit("sale", "2500000") == {"booking_amount": 2500000, "security_deposit": None}


def test_month_dates_and_placeholder_rank():
    """Launch / possession dates are months on the site; the day is a filler 01."""
    assert P._month("Jun, 2021") == "2021-06" and P._month("20180601") == "2018-06"
    assert P._month("2022-12-01 00:00:00") == "2022-12" and P._month(None, "Jun 2018") == "2018-06"
    assert P._month("soon") is None
    assert P.to_int("Not Found") is None          # projectRank.data.rank when unranked


def test_project_card_price_range():
    assert P._range_display("60.6 Lac,1.20 Cr") == "60.6 Lac - 1.20 Cr"
    assert P._range_display("10.51 Cr,18.57 Cr") == "10.51 Cr - 18.57 Cr"
    assert P._range_display("Call For Price") == "Call For Price" and P._range_display(None) is None
    cards = P.parse_projects_list(fixture("projects_mumbai_page1.html"))["results"]
    assert all("," not in c["price"]["display"] for c in cards if c["price"]["display"])


def test_rera_units_and_repeated_documents():
    out = P.parse_rera(fixture("rera_shelton_elite.html"), "5336113")
    assert out["unit_configurations"][0] == {"bedrooms": 1, "property_type": "apartment",
                                             "carpet_area": {"value": 733.0, "unit": "sqft"}}
    assert len(out["unit_configurations"]) == 7
    # Lodha World One lists one PDF as Occupancy Certificate1/2/3 -> once
    groups = P._doc_groups([{"dataKey": "Legal Certificates", "dataValue": {
        "Occupancy Certificate1": "2025/07/05/oc.pdf", "Occupancy Certificate2": "2025/07/05/oc.pdf",
        "Commencement Certificate1": "2025/07/05/cc.pdf"}}])
    assert [d["name"] for d in groups[0]["documents"]] == ["Occupancy Certificate1", "Commencement Certificate1"]


def test_unit_plan_rents_are_numbers():
    plans = P._unit_plans({"All": [{"bhkType": "3 BHK", "carpetAr": "1590", "coverAreaUnitD": "Sq-ft",
                                    "minRentPriceD": "420000", "maxRentPriceD": "615000"},
                                   {"bhkType": "4 BHK", "carpetAr": "1965", "minRentPriceD": None}]})
    assert plans[0]["rent_price"] == {"min": 420000, "max": 615000}
    assert plans[1]["rent_price"] is None


def test_agent_lone_place_is_the_city():
    """'Tejasvi Realty Pvt. Ltd., Mumbai' (no base locality) -> city Mumbai, locality None."""
    agents = [{"locality": "Andheri West", "city": "Mumbai"}, {"locality": "Chembur", "city": "Mumbai"},
              {"locality": "Mumbai", "city": None}, {"locality": "Thane West", "city": None}]
    P.settle_agent_cities(agents, "4320")                    # a code: the cards' own city decides
    assert agents[2] == {"locality": None, "city": "Mumbai"}
    assert agents[3] == {"locality": "Thane West", "city": None}
    lone = [{"locality": "Bangalore", "city": None}]
    assert P.settle_agent_cities(lone, "bangalore") == [{"locality": None, "city": "Bangalore"}]
    cards = P.settle_agent_cities(P.parse_agents(fixture("agents_mumbai_sale.html")), "Mumbai")
    assert not [c for c in cards if c["locality"] == "Mumbai"]


def test_facing_spacing():
    assert P._facing("North - East") == "North-East"
    assert P._facing("South -West") == "South-West"
    assert P._facing("East") == "East" and P._facing(None) is None


def test_strip_html_decodes_entities():
    """Project descriptions carry &nbsp; / &amp; inside their HTML (Lodha World One, 2026-11-10)."""
    text = P._strip_html("<p>Near the Sea Link.&nbsp;</p><h2>Key Facts &amp; USPs</h2>"
                         "<table><tr><td>Feature</td><td>Details</td></tr></table>")
    assert text == "Near the Sea Link. | Key Facts & USPs | Feature: Details"
    assert P._strip_html("Pei Cobb Freed &amp; Partners") == "Pei Cobb Freed & Partners"


def test_search_amenities_all_named():
    """Search rows carry bare amenity ids (luxAmenMap / nonluxAmenMap name a few);
    the site's id table names the rest, so no row ships a null name."""
    for name in ("search_sale_juhu_3bhk.json", "search_rent_bangalore.json", "search_commercial_mumbai.json"):
        rows = P.parse_search(fixture(name))["results"]
        amenities = [a for row in rows for a in row["amenities"]]
        assert amenities and all(a["id"] and a["name"] for a in amenities), name
    assert refs.AMENITIES["12226"] == "Cafeteria/Food Court"
    assert refs.AMENITIES["1404161"] == "Kids Splash Pool"


def test_maintenance_frequency():
    assert P._maintenance("26", "Monthly") == {"amount": 26, "currency": "INR", "period": "monthly",
                                               "is_per_sqft": False}
    assert P._maintenance("4.5", "Per sq. Unit Monthly") == {"amount": 4.5, "currency": "INR", "period": "monthly",
                                                             "is_per_sqft": True}
    assert P._maintenance("12000", "Quarterly")["period"] == "quarterly"
    assert P._maintenance("1", "One Time")["period"] == "one-time"
    assert P._maintenance("0", "Monthly") is None and P._maintenance(None, None) is None


def test_reviews_are_plain_text_with_snake_case_ratings():
    project = P.parse_project(fixture("project_shelton_elite.html"), "5336113")
    reviews = project["locality_reviews"]["results"] + project["reviews"]["results"]
    assert not any("<" in (r["text"] or "") for r in reviews)
    assert any("\n" in (r["text"] or "") for r in reviews)        # <br> kept as a line break
    rated = next(r for r in reviews if r["category_ratings"])
    assert set(rated["category_ratings"]) == {"environment", "commuting", "places_of_interest"}
    assert set(rated["category_ratings"]["commuting"]) == {"public_transport", "parking", "connectivity", "traffic"}
    ratings = project["locality"]["ratings"]
    assert ratings["places_of_interest"] == 4.3 and ratings["restaurants"] == 4.3 and ratings["roads"] == 4.2
    assert all(k == P.snake(k) for k in ratings)


def test_snake_and_rich_text():
    assert P.snake("constQuality") == "const_quality"
    assert P.snake("Public Transport") == "public_transport"
    assert P.snake("Places of Interest") == "places_of_interest"
    assert P._rich_text("Sea View<br>From my flat &amp; more<br/> <b>bold</b>") == "Sea View\nFrom my flat & more\nbold"
    assert P._rich_text("  ") is None and P._rich_text(None) is None


def test_parse_property_unknown_page_has_no_record():
    html = fixture("property_unknown.html")
    assert "SERVER_PRELOADED_STATE_DETAILS" not in html      # fetch.py maps this to NotFound
    record = P.parse_property(html, "19999999")
    assert record["id"] == "19999999" and record["title"] is None and record["price"]["amount"] is None
    assert record["similar"] == []


# ---- projects -----------------------------------------------------------------------------

def test_parse_project(project):
    assert project["id"] == "5336113" and project["name"] == "Shelton Elite"
    assert project["link"] == "https://www.magicbricks.com/shelton-elite-juhu-mumbai-pdpid-4d4235333336313133"
    assert project["status"] == "Under Construction" and project["property_type"] == "Multistorey Apartment"
    assert project["description"].startswith("Shelton Elite is a Under Construction project")
    assert "<" not in project["description"] and "Shelton Elite Price: Rs. 5.41 Cr - 10.63 Cr" in project["description"]
    assert "<" not in project["developer"]["about"]
    assert project["bedrooms"] == [3, 4]
    assert project["price"] == {"min": 54148000, "max": 106368000, "currency": "INR",
                                "display": "5.41 Cr - 10.63 Cr", "per_sqft_min": 40000.0, "per_sqft_max": 60284.0}
    assert project["launched"] == "2022-09" and project["possession_by"] == "2027-03"   # months, like the site
    assert project["total_units"] == 31 and project["towers"] == 1
    assert project["area"] == {"value": 1.0, "unit": "acre"}
    assert project["location"]["address"].startswith("Gulmohar Cross Road No. 12")
    assert project["location"]["pincode"] == "400049" and project["location"]["state"] == "Maharashtra"
    assert project["location"]["latitude"] == pytest.approx(19.1136376)
    dev = project["developer"]
    assert dev["name"] == "Shelton Groups" and dev["id"] == "73541"
    assert dev["link"] == "https://www.magicbricks.com/shelton-groups-buid-4d423733353431"
    assert dev["experience_years"] == 17 and dev["total_projects"] == 3 and dev["completed_projects"] == 2
    assert project["rera"]["ids"] == ["P51800046724"]
    assert project["rera"]["link"] == "https://www.magicbricks.com/shelton-elite-rera-details-nprid-4d4235333336313133"
    assert project["rera"]["updated_on"] == "2024-08-01"
    assert project["approved_by_banks"] == ["Canara Bank"]
    assert project["certificates"] == {"commencement": True, "occupancy": None}
    assert {"id": "12202", "name": "Lift", "icon": "https://cdn.staticmb.com/mobileImages/amenities/lift.jpg"} in project["amenities"]
    assert len(project["amenities"]) == 18
    assert project["unit_plans"][0]["configuration"] == "3 BHK"
    assert project["unit_plans"][0]["carpet_area"] == {"value": 1088.0, "unit": "sqft"}
    assert project["unit_plans"][0]["floor_plan"].endswith(".JPG")
    assert project["gallery"]["photo_count"] == 30 and len(project["gallery"]["photos"]) == 25
    assert project["gallery"]["photos"][0]["caption"] == "Project Entrance in Shelton Elite"
    assert project["gallery"]["videos"] == ["https://www.youtube.com/embed/ZgbJ_R_8PEk"]
    assert project["gallery"]["brochure"].endswith("Shelton-Elite-Brochure.pdf")
    assert project["rating"] == 4.7 and project["review_count"] == 3
    assert project["ratings"]["construction_quality"] == 4.0
    assert project["ratings"]["project_infrastructure"] == 4.8 and "psm_avg" not in project["ratings"]
    assert project["rank"] == {"in_locality": 12, "of": 13}
    assert project["listings_for_sale"] == 30
    assert project["price_trend"]["months"][0] == "2025-11" and len(project["price_trend"]["series"]) == 2
    assert project["price_trend"]["project_change_percent"] == 27.97
    assert project["locality_price_trend"]["series"][0]["name"] == "Juhu"
    loc = project["locality"]
    assert loc["id"] == "60166" and loc["name"] == "Juhu" and loc["rank"] == 11
    assert loc["rating"] == 4.5 and loc["review_count"] == 116
    assert loc["ratings"]["safety"] == 4.4
    assert loc["price_per_sqft"]["quarter_change_percent"] == -2.3
    assert loc["pros"][0].startswith("Presence of Bollywood")
    pincode_faq = next(f for f in project["faqs"] if f["question"] == "What is the area pin code of Shelton Elite?")
    assert "400049" in pincode_faq["answer"]
    assert all(f["question"] and f["answer"] and "<" not in f["answer"] for f in project["faqs"])
    # the site's count includes the featured copy of 1675659; the list keeps it once, with its ratings
    assert project["reviews"]["count"] == 3 and len(project["reviews"]["results"]) == 2
    review = project["reviews"]["results"][0]
    assert review["id"] == "1675659" and review["title"] == "Prime Juhu Living with Exclusive Comforts"
    assert review["reviewer"] == {"name": None, "type": "Owner", "relation": "Lives in Project", "photo": None}
    assert review["posted_on"] == "2026-02-09" and review["is_sponsored"] is False
    assert review["rating"] is not None and review["reviewed_on"] == "2026-02-09"
    assert project["locality_reviews"]["count"] == 116
    assert project["similar_projects"][0]["id"] == "5441461"
    assert project["similar_projects"][0]["price"]["min"] == 90000000
    assert project["similar_projects"][0]["link"].startswith("https://www.magicbricks.com/lotus-arcadian")
    assert project["updated_on"] == "2026-11-07"


def test_parse_project_sparse():
    record = P.parse_project("<html></html>", "1")
    assert record["id"] == "1" and record["name"] is None and record["amenities"] == []
    assert record["reviews"]["count"] == 0


def test_parse_projects_list():
    out = P.parse_projects_list(fixture("projects_mumbai_page1.html"))
    assert out["total_count"] == 3734 and out["total_pages"] == 187 and out["items_per_page"] == 20
    assert out["page"] == 1 and out["city"] == {"id": "4320", "name": "Mumbai"}
    assert out["locality"] == {"id": None, "name": None}
    assert len(out["results"]) == 20
    card = out["results"][0]
    assert card["id"] == "5332329" and card["name"] == "Liberty Bay Vue"
    assert card["link"] == "https://www.magicbricks.com/liberty-bay-vue-malad-west-mumbai-pdpid-4d4235333332333239"
    assert card["developer"]["name"] == "Liberty Group" and card["developer"]["id"] == "55322"
    assert card["bedrooms"] == [1, 2, 3]
    assert card["price"]["min"] == 11500000 and card["price"]["max"] == 34000000
    assert card["price"]["display"] == "1.15 Cr - 3.40 Cr"
    assert card["price"]["per_sqft_min"] == 15885.0 and card["price"]["per_sqft_max"] == 27200.0
    assert card["status"] == "Ready To Move"
    assert card["launched"] == "2017-08" and card["possession_by"] == "2025-12"
    assert card["total_units"] == 138 and card["towers"] == 1
    assert card["area"] == {"value": 1.0, "unit": "acre"}
    assert card["location"]["locality"] == {"id": "80084", "name": "Malad West"}
    assert card["location"]["pincode"] == "400095"
    assert card["has_rera"] is True and card["rera_updated_on"] == "2025-09-09"
    assert card["image"].startswith("https://img.staticmb.com/mbimages/project/")
    assert card["image_count"] == 71
    assert card["brochure"].endswith(".pdf")
    assert card["video"] == "https://www.youtube.com/watch?v=o5AbL94RXN4"
    assert card["amenities"][0]["id"] == "12539"
    page2 = P.parse_projects_list(fixture("projects_mumbai_page2.html"))
    assert len(page2["results"]) == 20
    assert {c["id"] for c in page2["results"]}.isdisjoint({c["id"] for c in out["results"]})


def test_parse_projects_list_fallback_and_sparse():
    fallback = ('<script>window.SERVER_PRELOADED_STATE_ = {"searchResult": [], '
                '"searchAdditionalDataBean": {"reqUrl": "/magichomes"}};</script>')
    assert P.parse_projects_list(fallback) is None
    assert P.parse_projects_list("<html></html>")["results"] == []


def test_parse_rera():
    out = P.parse_rera(fixture("rera_shelton_elite.html"), "5336113")
    assert out["id"] == "5336113" and out["name"] == "Shelton Elite" and out["developer"] == "Shelton Groups"
    assert out["link"] == "https://www.magicbricks.com/shelton-elite-juhu-mumbai-pdpid-4d4235333336313133"
    assert out["registrations"] == [{"id": "P51800046724", "valid_until": "2027-03", "phase": "26303"}]
    assert out["has_legal_certificates"] is True and out["has_quarterly_reports"] is True
    assert out["updated_on"] == "2024-08-01"
    groups = {g["group"]: g["documents"] for g in out["document_groups"]}
    assert "Legal Certificates" in groups and "Quarterly Progress Reports" in groups
    legal = groups["Legal Certificates"]
    assert legal[0]["name"] == "Legal Title Report"
    assert legal[0]["link"] == "https://img.staticmb.com/mbimages/reradoc/2024/08/01/53361131Copyofthelegaltitlereport_2_1.pdf"
    assert len(legal) == 12
    assert out["total_units"] == 31 and out["possession_by"] == "2027-03"
    assert P.parse_rera("<html></html>", "1")["document_groups"] == []


# ---- agents -----------------------------------------------------------------------------------

def test_parse_agents():
    out = P.parse_agents(fixture("agents_mumbai_sale.html"))
    assert len(out) == 104
    first = out[0]
    assert first["name"] == "Viraj Patil" and first["company"] == "Majestic Properties"
    assert first["id"] == "61979531"
    assert first["link"] == ("https://www.magicbricks.com/top-agent-details/"
                             "company-majestic-properties-in-mumbai-agentid-4d423631393739353331")
    assert first["locality"] == "Andheri West" and first["city"] == "Mumbai"
    assert first["operating_since"] == 2014 and first["badge"] == "Trusted by Many Users"
    assert first["sale_listings"] == 29 and first["rent_listings"] == 67
    assert first["deals_closed"] == 14 and first["team_size"] == 1
    assert first["deals_in"] == ["Rent/Lease", "Pre-launch", "Original Booking", "Resale"]
    assert "Goregaon West" in first["operates_in"] and len(first["operates_in"]) > 10
    assert first["about"].startswith("Coming into Real estate") and "..." not in first["about"]
    assert first["about"].endswith("Clients.")
    assert first["photo"].startswith("https://img.staticmb.com/")
    second = out[1]
    assert second["name"] == "Anisha Sidhwani" and second["company"] == "Easy To Move In"
    assert second["locality"] == "Chembur" and second["deals_closed"] == 1000
    assert second["logo"].startswith("https://img.staticmb.com/mbimages/user/")
    assert all(a["id"] and a["name"] for a in out)


def test_parse_agents_empty():
    assert P.parse_agents("") == []
    assert P.parse_agents('<div class="agent-srp" id="topAgentCard"></div>') == []


# ---- autosuggest ------------------------------------------------------------------------------

def test_parse_autosuggest():
    out = P.parse_autosuggest(fixture("autosuggest_juhu.json"))
    assert out[0] == {"id": "60166", "name": "Juhu", "display": "Juhu, Mumbai", "type": "locality",
                      "category": None, "city": {"id": "4320", "name": "Mumbai"}, "locality": None,
                      "state": None, "developer": None,
                      "latitude": pytest.approx(19.0982677), "longitude": pytest.approx(72.833514)}
    kinds = {r["type"] for r in out}
    assert {"locality", "project", "landmark"} <= kinds
    assert all(set(r) == set(out[0]) for r in out)     # one key set for every suggestion
    project = next(r for r in out if r["type"] == "project" and r["developer"])
    assert project["locality"] == {"id": "60166", "name": "Juhu"}
    assert project["city"] == {"id": "4320", "name": "Mumbai"}
    landmark = next(r for r in out if r["type"] == "landmark" and r["category"])
    assert landmark["locality"]["name"] and landmark["city"]["name"] and landmark["latitude"]


def test_parse_autosuggest_maps_every_type_code():
    payload = {"locationMap": {
        "LOCATION": [
            {"result": "Bandra Reclamation, Mumbai", "city": "4320", "rfnum": "94250", "suggestType": "lt_al",
             "psmName": "Bandra Reclamation", "localityId": "", "latitude": "19.05", "longitude": "72.82"},
            {"result": "Worli Sea Face Municipal School Worli, Mumbai", "city": "4320",
             "rfnum": "82390-Worli Sea Face Municipal School Worli", "suggestType": "lt_pg",
             "psmName": "Worli Sea Face Municipal School Worli, Mumbai", "localityId": "", "latitude": "19.0097"},
            {"result": "Mumbai-South Mumbai", "city": "4320", "rfnum": "1001042", "suggestType": "sub",
             "psmName": "South Mumbai"},
        ],
        "PG": [{"result": "worli, Worli Sea Face", "city": "4320", "rfnum": "515101", "suggestType": "pg",
                "psmName": "worli", "localityId": ""}],
        "OTHER": [{"result": "x", "rfnum": "1", "suggestType": "brand_new"}, "junk"],
    }}
    out = P.parse_autosuggest(payload)
    assert [r["type"] for r in out] == ["locality", "landmark", "sub_region", "paying_guest", "brand_new"]
    assert out[0]["id"] == "94250" and out[0]["latitude"] == 19.05
    assert out[0]["city"] == {"id": "4320", "name": "Mumbai"}
    assert out[1]["id"] is None and out[1]["locality"] == {"id": "82390", "name": None}
    assert out[1]["city"] == {"id": "4320", "name": "Mumbai"}
    assert out[2]["city"] == {"id": "4320", "name": None}          # sub-region: no city in its display
    assert out[3]["id"] == "515101" and out[3]["locality"] is None
    assert out[4]["city"] is None and out[4]["category"] is None


def test_parse_autosuggest_empty():
    assert P.parse_autosuggest(fixture("autosuggest_empty.json")) == []
    assert P.parse_autosuggest(None) == []


# ---- trends ---------------------------------------------------------------------------------

def test_parse_trends():
    out = P.parse_trends(fixture("trends_juhu_sale.json"), fixture("trends_table_juhu_sale.html"))
    assert out["unit"] == "INR per sqft"
    assert out["quarters"][0] == "2021-10" and out["quarters"][-1] == "2026-10" and len(out["quarters"]) == 21
    assert out["series"] == [{"name": "Juhu", "values": [36753.0, 37421.0, 39272.0, 38819.0, 38676.0, 39628.0, 39466.0,
                                                        39237.0, 40580.0, 41227.0, 41789.0, 43138.0, 42773.0, 43673.0,
                                                        51548.0, 52257.0, 48122.0, 46893.0, 45542.0, 45736.0, 44697.0]}]
    assert out["quarterly_table"][0] == {"period": "Oct-Dec'25", "price_per_sqft": 46893.0, "change_percent": -3.0}
    assert out["yearly_table"][0] == {"period": "2025", "price_per_sqft": 48091.0, "change_percent": 11.0}
    assert len(out["yearly_table"]) >= 3


def test_parse_trends_nothing():
    assert P.parse_trends(None, None) is None
    assert P.parse_trends({"labels": [], "datasets": []}, "") is None
