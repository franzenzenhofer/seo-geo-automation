"""Schema.org structured data checks (JSON-LD, including @graph).

Required properties follow Google's structured data docs:
https://developers.google.com/search/docs/appearance/structured-data/search-gallery
"""

from __future__ import annotations

from typing import Any

from shared.html_parser import ParsedPage, get_json_ld
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "SCHEMA"
JsonObj = dict[str, Any]

JSON_LD = Check("SCHEMA-001", "json_ld_present", C)
ARTICLE = Check("SCHEMA-002", "article_fields", C)
BREADCRUMB = Check("SCHEMA-003", "breadcrumb", C)
BREADCRUMB_ITEMS = Check("SCHEMA-004", "breadcrumb_positions", C)
ORGANIZATION = Check("SCHEMA-005", "organization", C)
PRODUCT = Check("SCHEMA-006", "product", C)
VIDEO = Check("SCHEMA-007", "video_object", C)
FAQ = Check("SCHEMA-008", "faq_page", C)
SEARCH_ACTION = Check("SCHEMA-009", "website_searchaction", C)
EVENT = Check("SCHEMA-010", "event", C)
RECIPE = Check("SCHEMA-011", "recipe", C)
RATING = Check("SCHEMA-012", "aggregate_rating", C)


def all_objects(blocks: list[JsonObj]) -> list[JsonObj]:
    """Top-level JSON-LD blocks plus every dict inside their @graph."""
    objects: list[JsonObj] = []
    for block in blocks:
        objects.append(block)
        graph = block.get("@graph", [])
        if isinstance(graph, list):
            objects.extend(item for item in graph if isinstance(item, dict))
    return objects


def find_types(page: ParsedPage, names: set[str]) -> list[JsonObj]:
    found = []
    for obj in all_objects(get_json_ld(page)):
        types = obj.get("@type")
        type_set = set(types) if isinstance(types, list) else {types}
        if type_set & names:
            found.append(obj)
    return found


def first_dict(value: Any) -> JsonObj:
    """A dict value, or the first dict of a list, else {}."""
    if isinstance(value, list):
        value = value[0] if value else {}
    return value if isinstance(value, dict) else {}


def missing_keys(obj: JsonObj, keys: list[str]) -> list[str]:
    return [k for k in keys if not obj.get(k)]


def required_fields(check: Check, page: ParsedPage, types: set[str], keys: list[str]) -> CheckResult:
    label = "/".join(sorted(types))
    items = find_types(page, types)
    if not items:
        return check.result(Severity.INFO, f"No {label} found")
    missing = missing_keys(items[0], keys)
    if missing:
        return check.result(Severity.FAIL, f"{label} missing: {', '.join(missing)}", {"missing": missing})
    return check.result(Severity.PASS, f"{label} has all required fields")


def check_json_ld_present(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    blocks = get_json_ld(page)
    if blocks:
        types = [str(b.get("@type", "?")) for b in blocks]
        return JSON_LD.result(Severity.PASS, f"Found {len(blocks)} JSON-LD block(s)", {"types": types})
    return JSON_LD.result(Severity.WARN, "No JSON-LD structured data found")


def article_missing(article: JsonObj) -> list[str]:
    missing = missing_keys(article, ["headline", "image"])
    if not (article.get("datePublished") or article.get("dateModified")):
        missing.append("datePublished|dateModified")
    if not first_dict(article.get("author")).get("name"):
        missing.append("author.name")
    return missing


def check_article_fields(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    articles = find_types(page, {"Article", "NewsArticle", "BlogPosting"})
    if not articles:
        return ARTICLE.result(Severity.INFO, "No Article type found")
    for article in articles:
        missing = article_missing(article)
        if missing:
            return ARTICLE.result(
                Severity.FAIL, f"Article missing: {', '.join(missing)}", {"missing": missing}
            )
    return ARTICLE.result(Severity.PASS, "Article schema has all recommended fields")


def breadcrumb_items(page: ParsedPage) -> list[Any] | None:
    crumbs = find_types(page, {"BreadcrumbList"})
    if not crumbs:
        return None
    items = crumbs[0].get("itemListElement", [])
    return items if isinstance(items, list) else []


def check_breadcrumb(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    items = breadcrumb_items(page)
    if items is None:
        return BREADCRUMB.result(Severity.INFO, "No BreadcrumbList found")
    if len(items) < 2:
        return BREADCRUMB.result(Severity.WARN, f"BreadcrumbList has {len(items)} item(s), need >= 2")
    return BREADCRUMB.result(Severity.PASS, f"BreadcrumbList with {len(items)} items")


def breadcrumb_item_issues(index: int, element: Any) -> list[str]:
    el = element if isinstance(element, dict) else {}
    issues = [] if isinstance(el.get("position"), (int, float)) else [f"Item {index}: no position"]
    item = el.get("item", {})
    if not isinstance(item, str) and not (
        el.get("name") or first_dict(item).get("@id") or first_dict(item).get("name")
    ):
        issues.append(f"Item {index}: no item URL or name")
    return issues


def check_breadcrumb_positions(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    items = breadcrumb_items(page)
    if items is None:
        return BREADCRUMB_ITEMS.result(Severity.INFO, "No BreadcrumbList found")
    issues = [issue for i, el in enumerate(items) for issue in breadcrumb_item_issues(i, el)]
    if issues:
        return BREADCRUMB_ITEMS.result(Severity.FAIL, "; ".join(issues), {"issues": issues})
    return BREADCRUMB_ITEMS.result(Severity.PASS, "All breadcrumb items valid")


def check_organization(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    orgs = find_types(page, {"Organization", "LocalBusiness"})
    if not orgs:
        return ORGANIZATION.result(Severity.INFO, "No Organization/LocalBusiness found")
    missing = missing_keys(orgs[0], ["name", "url"])
    if not (orgs[0].get("logo") or orgs[0].get("image")):
        missing.append("logo|image")
    if missing:
        return ORGANIZATION.result(
            Severity.FAIL, f"Organization missing: {', '.join(missing)}", {"missing": missing}
        )
    return ORGANIZATION.result(Severity.PASS, "Organization schema is complete")


def check_product(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    products = find_types(page, {"Product"})
    if not products:
        return PRODUCT.result(Severity.INFO, "No Product found")
    offers = first_dict(products[0].get("offers"))
    missing = missing_keys(products[0], ["name"]) + [
        f"offers.{k}" for k in missing_keys(offers, ["price", "priceCurrency"])
    ]
    if missing:
        return PRODUCT.result(Severity.FAIL, f"Product missing: {', '.join(missing)}", {"missing": missing})
    return PRODUCT.result(Severity.PASS, "Product schema is complete")


def check_video_object(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    return required_fields(
        VIDEO, page, {"VideoObject"}, ["name", "description", "thumbnailUrl", "uploadDate"]
    )


def check_faq_page(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    faqs = find_types(page, {"FAQPage"})
    if not faqs:
        return FAQ.result(Severity.INFO, "No FAQPage found")
    entities = faqs[0].get("mainEntity", [])
    if not isinstance(entities, list) or not entities:
        return FAQ.result(Severity.FAIL, "FAQPage missing mainEntity array")
    for i, question in enumerate(entities):
        q = question if isinstance(question, dict) else {}
        if q.get("@type") != "Question" or not q.get("acceptedAnswer"):
            return FAQ.result(Severity.FAIL, f"mainEntity[{i}]: invalid Question or no acceptedAnswer")
    return FAQ.result(Severity.PASS, f"FAQPage with {len(entities)} valid Q&A pairs")


def search_action(site: JsonObj) -> JsonObj:
    action = site.get("potentialAction", {})
    if isinstance(action, list):
        return next((a for a in action if isinstance(a, dict) and a.get("@type") == "SearchAction"), {})
    return action if isinstance(action, dict) else {}


def check_website_searchaction(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    sites = find_types(page, {"WebSite"})
    if not sites:
        return SEARCH_ACTION.result(Severity.INFO, "No WebSite found")
    action = search_action(sites[0])
    if action.get("@type") != "SearchAction":
        return SEARCH_ACTION.result(Severity.WARN, "WebSite has no SearchAction")
    target = action.get("target", "")
    template = first_dict(target).get("urlTemplate", "") if not isinstance(target, str) else target
    if "{search_term_string}" not in str(template):
        return SEARCH_ACTION.result(Severity.FAIL, "SearchAction target missing {search_term_string}")
    return SEARCH_ACTION.result(Severity.PASS, "WebSite SearchAction configured correctly")


def check_event(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    return required_fields(EVENT, page, {"Event"}, ["name", "startDate", "location"])


def check_recipe(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    recipes = find_types(page, {"Recipe"})
    if not recipes:
        return RECIPE.result(Severity.INFO, "No Recipe found")
    missing = missing_keys(recipes[0], ["name", "image"])
    if not (recipes[0].get("recipeIngredient") or recipes[0].get("recipeInstructions")):
        missing.append("recipeIngredient|recipeInstructions")
    if missing:
        return RECIPE.result(Severity.FAIL, f"Recipe missing: {', '.join(missing)}", {"missing": missing})
    return RECIPE.result(Severity.PASS, "Recipe schema is complete")


def aggregate_ratings(page: ParsedPage) -> list[JsonObj]:
    ratings = find_types(page, {"AggregateRating"})
    nested = [first_dict(obj.get("aggregateRating")) for obj in all_objects(get_json_ld(page))]
    return ratings + [r for r in nested if r.get("@type") == "AggregateRating"]


def check_aggregate_rating(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    ratings = aggregate_ratings(page)
    if not ratings:
        return RATING.result(Severity.INFO, "No AggregateRating found")
    missing = missing_keys(ratings[0], ["ratingValue"])
    if not (ratings[0].get("reviewCount") or ratings[0].get("ratingCount")):
        missing.append("reviewCount|ratingCount")
    if missing:
        return RATING.result(
            Severity.FAIL, f"AggregateRating missing: {', '.join(missing)}", {"missing": missing}
        )
    return RATING.result(Severity.PASS, "AggregateRating is complete")


checks = {
    "SCHEMA-001": check_json_ld_present,
    "SCHEMA-002": check_article_fields,
    "SCHEMA-003": check_breadcrumb,
    "SCHEMA-004": check_breadcrumb_positions,
    "SCHEMA-005": check_organization,
    "SCHEMA-006": check_product,
    "SCHEMA-007": check_video_object,
    "SCHEMA-008": check_faq_page,
    "SCHEMA-009": check_website_searchaction,
    "SCHEMA-010": check_event,
    "SCHEMA-011": check_recipe,
    "SCHEMA-012": check_aggregate_rating,
}

if __name__ == "__main__":
    run_tool(C, checks, "Schema.org structured data checks")
