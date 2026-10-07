"""BODY/content checks: headings, images, links, content diversity, text volume, TOC, freshness."""

from __future__ import annotations

from shared.html_parser import (
    ParsedPage,
    attr,
    first_tag,
    get_body_text,
    get_content_diversity,
    get_headings,
    get_images,
    get_json_ld,
    get_links,
    tags,
)
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "BODY"
GENERIC_ANCHORS = {"click here", "read more", "here", "more", "learn more", "link"}
DATE_KEYS = ("dateModified", "datePublished", "dateCreated")
NO_IMAGES = "No images"

H1 = Check("BODY-001", "H1 Present", C)
H1_TEXT = Check("BODY-002", "H1 Not Empty", C)
IMG_DIMENSIONS = Check("BODY-003", "Images Have Dimensions", C)
IMG_LAZY = Check("BODY-004", "Images Lazy Loading", C)
INTERNAL = Check("BODY-005", "Internal Links", C)
NOFOLLOW = Check("BODY-006", "No Nofollow Links", C)
DIVERSITY = Check("BODY-007", "Content Diversity", C)
TEXT = Check("BODY-008", "Text Content", C)
PARAM_LINKS = Check("BODY-009", "Parameterized Links", C)
SUBHEADS = Check("BODY-010", "Subheadlines", C)
TABLES = Check("BODY-011", "Tables Present", C)
LISTS = Check("BODY-012", "Lists Present", C)
ANCHORS = Check("BODY-013", "Anchor Text Quality", C)
TOC = Check("BODY-014", "Table of Contents", C)
FRESHNESS = Check("BODY-015", "Content Freshness", C)
TEXT_IMAGE = Check("BODY-016", "Text-Image Ratio", C)
IN_CONTENT = Check("BODY-017", "In-Content Links", C)


def word_count(page: ParsedPage) -> int:
    return len(get_body_text(page).split())


def check_h1_present(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    h = get_headings(page)
    if h["h1_count"] == 1 and h["h1_texts"][0]:
        return H1.result(Severity.PASS, f"One H1: '{h['h1_texts'][0][:80]}'")
    if h["h1_count"] == 0:
        return H1.result(Severity.FAIL, "No H1 found")
    return H1.result(Severity.WARN, f"{h['h1_count']} H1 tags", {"texts": h["h1_texts"]})


def check_h1_not_empty(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    h = get_headings(page)
    if h["h1_count"] == 0:
        return H1_TEXT.result(Severity.FAIL, "No H1")
    if any(not t.strip() for t in h["h1_texts"]):
        return H1_TEXT.result(Severity.FAIL, "Empty H1 found")
    return H1_TEXT.result(Severity.PASS, "H1 has content")


def check_images_dimensions(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    imgs = get_images(page)
    if not imgs:
        return IMG_DIMENSIONS.result(Severity.INFO, NO_IMAGES)
    missing = [i["src"] for i in imgs if not i["has_dimensions"]]
    if not missing:
        return IMG_DIMENSIONS.result(Severity.PASS, f"All {len(imgs)} images have width+height")
    msg = f"{len(missing)}/{len(imgs)} images missing dimensions"
    return IMG_DIMENSIONS.result(Severity.WARN, msg, {"missing": missing[:10]})


def check_images_lazy(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    imgs = get_images(page)
    if not imgs:
        return IMG_LAZY.result(Severity.INFO, NO_IMAGES)
    eager = [i["src"] for i in imgs[3:] if i["loading"] != "lazy"]
    if not eager:
        return IMG_LAZY.result(Severity.PASS, "Below-fold images use lazy loading")
    msg = f"{len(eager)} below-fold images without loading=lazy"
    return IMG_LAZY.result(Severity.INFO, msg, {"missing": eager[:10]})


def check_internal_links(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    count = get_links(page)["internal_count"]
    if count:
        return INTERNAL.result(Severity.PASS, f"{count} internal links found")
    return INTERNAL.result(Severity.WARN, "No internal links")


def check_nofollow_links(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    count = get_links(page)["nofollow_count"]
    if count == 0:
        return NOFOLLOW.result(Severity.PASS, "No nofollow links")
    return NOFOLLOW.result(
        Severity.WARN, f"{count} nofollow links - reserve nofollow/sponsored for paid links"
    )


def check_content_diversity(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    diversity = get_content_diversity(page)
    kinds = sum(1 for v in diversity.values() if v > 0)
    if kinds >= 4:
        return DIVERSITY.result(Severity.PASS, f"{kinds} content types present", dict(diversity))
    if kinds >= 2:
        return DIVERSITY.result(Severity.WARN, f"Only {kinds} content types - aim for 4+", dict(diversity))
    return DIVERSITY.result(Severity.FAIL, f"Poor content diversity: {kinds} types", dict(diversity))


def check_text_content(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    words = word_count(page)
    if words >= 300:
        return TEXT.result(Severity.PASS, f"{words} words of text content")
    if words >= 100:
        return TEXT.result(Severity.WARN, f"Only {words} words - consider adding more content")
    return TEXT.result(Severity.FAIL, f"Very thin content: {words} words")


def check_parameterized_links(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    count = get_links(page)["parameterized_count"]
    if count == 0:
        return PARAM_LINKS.result(Severity.PASS, "No parameterized internal links in HTML")
    tip = {"tip": "Use buttons or data attributes plus JS for filter/sort URLs"}
    return PARAM_LINKS.result(Severity.WARN, f"{count} parameterized internal links", tip)


def check_subheadlines(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    h = get_headings(page)
    count = sum(h[f"h{i}_count"] for i in range(2, 7))
    if count >= 2:
        return SUBHEADS.result(Severity.PASS, f"{count} subheadlines (H2-H6) found")
    if count == 1:
        return SUBHEADS.result(Severity.WARN, "Only 1 subheadline - add more for structure")
    return SUBHEADS.result(Severity.FAIL, "No subheadlines (H2-H6) - page lacks structure")


def check_tables_present(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    count = get_content_diversity(page)["tables"]
    return TABLES.result(Severity.INFO, f"{count} table(s) found" if count else "No tables found")


def check_lists_present(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    diversity = get_content_diversity(page)
    lists = diversity["lists_ul"] + diversity["lists_ol"]
    if lists:
        return LISTS.result(
            Severity.PASS, f"{lists} list(s) found (ul={diversity['lists_ul']}, ol={diversity['lists_ol']})"
        )
    words = word_count(page)
    if words > 200:
        return LISTS.result(Severity.WARN, f"No lists on a page with {words} words - consider adding lists")
    return LISTS.result(Severity.INFO, "No lists found")


def check_anchor_text_quality(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    generic = [
        lnk["text"]
        for lnk in links["internal"] + links["external"]
        if lnk["text"].lower().strip() in GENERIC_ANCHORS
    ]
    if len(generic) > 2:
        return ANCHORS.result(
            Severity.WARN, f"{len(generic)} generic anchor texts found", {"samples": generic[:5]}
        )
    return ANCHORS.result(Severity.PASS, "Anchor texts are descriptive")


def check_toc_present(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """BODY-014: A table of contents helps navigation on long-form content."""
    toc = (
        first_tag(page.soup, id="toc")
        or first_tag(page.soup, class_="toc")
        or first_tag(page.soup, id="table-of-contents")
        or next((n for n in tags(page.soup, "nav") if "content" in attr(n, "aria-label").lower()), None)
    )
    if toc is not None:
        return TOC.result(Severity.PASS, "TOC found")
    anchors = [a for a in tags(page.soup, "a", href=True) if attr(a, "href").startswith("#")]
    if len(anchors) >= 3:
        return TOC.result(Severity.PASS, f"{len(anchors)} in-page anchor links (likely TOC)")
    words = word_count(page)
    if words > 800:
        return TOC.result(Severity.WARN, f"Long page ({words} words) without TOC - consider adding one")
    return TOC.result(Severity.INFO, "No TOC (short page)")


def check_content_freshness(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """BODY-015: Published/updated date signals (<time datetime> or JSON-LD dates)."""
    dates = [attr(t, "datetime") for t in tags(page.soup, "time", attrs={"datetime": True})]
    dates += [f"{key}={block[key]}" for block in get_json_ld(page) for key in DATE_KEYS if key in block]
    if dates:
        return FRESHNESS.result(
            Severity.PASS, f"Date signals found: {', '.join(dates[:3])}", {"dates": dates[:5]}
        )
    return FRESHNESS.result(Severity.WARN, "No date/time signals - freshness cannot be determined")


def check_text_image_ratio(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """BODY-016: Balance of text and images."""
    words, images = word_count(page), len(get_images(page))
    if images == 0:
        if words > 300:
            return TEXT_IMAGE.result(Severity.WARN, f"{words} words but 0 images - add visuals")
        return TEXT_IMAGE.result(Severity.INFO, NO_IMAGES)
    ratio = words / images
    if 50 <= ratio <= 500:
        return TEXT_IMAGE.result(
            Severity.PASS, f"~{int(ratio)} words per image ({words} words / {images} images)"
        )
    if ratio < 50:
        return TEXT_IMAGE.result(Severity.INFO, f"Image-heavy: {int(ratio)} words per image")
    return TEXT_IMAGE.result(Severity.WARN, f"Text-heavy: {int(ratio)} words per image - add more images")


def check_read_more_links(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """BODY-017: At least 3 internal links per page."""
    internal = get_links(page)["internal_count"]
    if internal >= 3:
        return IN_CONTENT.result(Severity.PASS, f"{internal} internal links")
    if internal:
        return IN_CONTENT.result(Severity.WARN, f"Only {internal} internal links - aim for 3+ per page")
    return IN_CONTENT.result(Severity.FAIL, "No internal links - critical for interlinking")


checks = {
    "BODY-001": check_h1_present,
    "BODY-002": check_h1_not_empty,
    "BODY-003": check_images_dimensions,
    "BODY-004": check_images_lazy,
    "BODY-005": check_internal_links,
    "BODY-006": check_nofollow_links,
    "BODY-007": check_content_diversity,
    "BODY-008": check_text_content,
    "BODY-009": check_parameterized_links,
    "BODY-010": check_subheadlines,
    "BODY-011": check_tables_present,
    "BODY-012": check_lists_present,
    "BODY-013": check_anchor_text_quality,
    "BODY-014": check_toc_present,
    "BODY-015": check_content_freshness,
    "BODY-016": check_text_image_ratio,
    "BODY-017": check_read_more_links,
}

if __name__ == "__main__":
    run_tool(C, checks, "BODY/content SEO checks")
