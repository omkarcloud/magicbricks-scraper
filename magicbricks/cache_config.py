"""Cache TTL per /magicbricks/* endpoint (cache.py, keyed on the validated
params). Listings churn daily (a seller edits price / status, new postings
land every hour), so the live surfaces cache for hours, not days; the
reference surfaces (projects, RERA, trends, autosuggest) move with the
site's own monthly / quarterly refresh.
"""
from datetime import timedelta

# Search pages: new postings land hourly, prices move daily; 2 h keeps a
# paging client consistent across its pages without serving stale counts.
SEARCH_CACHE = timedelta(hours=2)
# ONE parsed property page serves details + similar (api._property_record).
PROPERTY_CACHE = timedelta(hours=6)
# Project pages carry month-level data (price trend, reviews, floor plans).
PROJECT_CACHE = timedelta(hours=24)
# RERA documents are filed quarterly.
RERA_CACHE = timedelta(hours=24)
# The new-projects directory reorders as projects launch (rank by demand).
PROJECTS_LIST_CACHE = timedelta(hours=12)
# Agent rankings per city / locality change with their listing counts.
AGENTS_CACHE = timedelta(hours=12)
# Autosuggest = the site's place / project index; localities rarely change.
SUGGEST_CACHE = timedelta(hours=24)
# Quarterly ₹/sqft series: a new point lands once a quarter.
TRENDS_CACHE = timedelta(hours=24)
