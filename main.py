"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does (paged endpoints carry a
`pagination` block instead of next / previous links); results are written
to output/*.json. The schemas fill in every default, exactly as the API does.
"""
import json
import os

from magicbricks import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def params(schema_cls, **query):
    """Validate a query exactly like the API: defaults filled, links resolved."""
    return schema_cls().load(query)


if __name__ == "__main__":
    # a listing id, its hex id or any magicbricks.com property link
    save("property_63567183.json", api.property_details(
        **params(schemas.PropertySchema, property="63567183")))

    # 30 listings per page; a city name or code, plus any of the filters
    save("search_mumbai_worli.json", api.properties_search(
        **params(schemas.PropertiesSearchSchema, city="Mumbai", locality="Worli", bedrooms="3,4",
                 sort="price_high_to_low")))

    # a project id, its hex id or any -pdpid- project link
    save("project_5070869.json", api.project_details(
        **params(schemas.ProjectSchema, project="5070869")))
