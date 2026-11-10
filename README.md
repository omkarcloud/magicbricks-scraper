# 🏠 Magicbricks Scraper

Magicbricks Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Magicbricks property data for free.

## ✨ What Can I Get?

- 🏠 **Full details on 460K+ live listings** — price, ₹/sq ft, BHK, carpet area, floor, amenities, GPS, photos & the agent
- 🔍 **Search any Indian city your way** — buy or rent, 10 filters, 6 sort orders, 30 listings per page
- 🏗️ **29,000+ new projects** — floor plans, price ranges, RERA documents, resident reviews & ratings
- 📈 **Agents & price trends** — every city's top agents and 5 years of ₹/sq ft for any locality

## 🎥 Example: A Full Magicbricks Listing

```json
{
  "id": "63567183",
  "link": "https://www.magicbricks.com/propertyDetails/5-BHK-5401-Sq-ft-Multistorey-Apartment-FOR-Sale-Worli-in-Mumbai&id=4d423633353637313833",
  "title": "5 BHK 5400 Sqft Flat for Sale in Lodha World One Worli Mumbai",
  "listing_type": "sale",
  "transaction_type": "Resale",
  "description": "This is a large bare shell unit that can be made into 5 or 6 BHK in Lodha World One called CIEL. CIEL has exclusive amenities and stunning sea and Race Course views .",
  "price": { "amount": 420000000, "currency": "INR", "display": "42.0 Cr", "per_sqft": 77763.0, "emi_per_month": 1453996, "booking_amount": 2500000, "brokerage": "1%" },
  "bedrooms": 5,
  "bathrooms": 5,
  "balconies": 3,
  "area": { "carpet": { "value": 5400.0, "unit": "sqft" }, "covered": { "value": 5401.0, "unit": "sqft" } },
  "floor": { "number": null, "total": 78, "units_on_floor": 2 },
  "furnishing": "semi-furnished",
  "possession": { "status": "Ready to Move", "available_from": null },
  "location": { "locality": { "id": "78910", "name": "Worli" }, "city": { "id": "4320", "name": "Mumbai" }, "latitude": 19.00255, "longitude": 72.82653 },
  "project": { "id": "5070869", "name": "Lodha World One", "developer": "Lodha Developers Limited", "total_units": 421, "towers": 4, "rating": 4.4 },
  "rera_ids": ["P51900008345", "P51900008962"],
  "amenities": [
    { "id": "12205", "name": "Swimming Pool" },
    { "id": null, "name": "Helipad" }
  ],
  "lister": { "id": "27202575", "name": "Monica", "company": "M M Realty", "type": "Agent", "is_rera_agent": true, "sale_listings": 126, "rent_listings": 95 },
  "nearby_places": [
    { "name": "Patil International School", "category": "Educational Institute", "distance_km": 2.0 }
  ],
  "price_trend": { "unit": "INR per sqft", "months": ["2025-11", "2025-12", "2026-01"], "series": [{ "name": "Worli", "kind": "Locality Average", "values": [52510.0, 52315.0, 52244.0] }] }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Magicbricks Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/magicbricks-scraper
cd magicbricks-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

Magicbricks' Akamai bot protection refuses many cloud servers. Getting `blocked` errors? Start it on an Indian residential proxy instead:
```bash
MAGICBRICKS_PROXY=http://user:pass@host:port python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/properties/details?property=63567183"
```

```json
{
  "id": "63567183",
  "title": "5 BHK 5400 Sqft Flat for Sale in Lodha World One Worli Mumbai",
  "listing_type": "sale",
  "property_type": "Multistorey Apartment",
  "price": { "amount": 420000000, "currency": "INR", "display": "42.0 Cr", "per_sqft": 77763.0 },
  "bedrooms": 5,
  "bathrooms": 5,
  "area": { "carpet": { "value": 5400.0, "unit": "sqft" } },
  "floor": { "number": null, "total": 78, "units_on_floor": 2 },
  "furnishing": "semi-furnished",
  "age": "5 to 10 years",
  "ownership": "Freehold",
  "location": { "locality": { "id": "78910", "name": "Worli" }, "city": { "id": "4320", "name": "Mumbai" }, "latitude": 19.00255, "longitude": 72.82653 },
  "project": { "id": "5070869", "name": "Lodha World One", "developer": "Lodha Developers Limited" },
  "lister": { "name": "Monica", "company": "M M Realty", "type": "Agent" },
  "similar_count": 60
}
```

All 12 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

12 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Property Details | `/properties/details` | Everything about one listing: price, areas, amenities, project, agent, GPS |
| Search Locations | `/locations/search` | IDs and coordinates for any city, locality, project or landmark |
| Search Properties | `/properties/search` | 30 listings per page with 10 filters and 6 sort orders |
| Similar Properties | `/properties/similar` | Up to 60 look-alike listings plus what buyers also viewed |
| Search Projects | `/projects/search` | New and upcoming projects of any city, 20 per page |
| Project Details | `/projects/details` | Floor plans, prices, amenities, developer, RERA IDs, ratings and FAQs |
| Project Listings | `/projects/listings` | Every home for sale or rent inside one project |
| Project Reviews | `/projects/reviews` | Resident reviews and ratings for the project and its locality |
| Project RERA Documents | `/projects/rera` | RERA registrations plus the filed legal PDFs |
| Search Agents | `/agents/search` | A city's top agents with listings, deals closed and areas served |
| Agent Listings | `/agents/listings` | Every live listing of one agent, 30 per page |
| Locality Price Trends | `/localities/trends` | Five years of quarterly ₹ per sq ft for any locality |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-magicbricks-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-magicbricks-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-magicbricks-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/properties/details",
    params={"property": "63567183"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Magicbricks Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/magicbricks-scraper-github-whatsapp)

[![Ask Us by Email about Magicbricks Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Magicbricks%20Scraper%20API&body=I%20need%20help%20using%20the%20Magicbricks%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/magicbricks-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/magicbricks-scraper)
