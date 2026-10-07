"""Internal interlinking checks."""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from urllib.parse import urljoin, urlparse

from bs4 import Tag

from shared.html_parser import ParsedPage, attr, first_tag, get_links, tags
from shared.http_client import HttpResponse, fetch, fetch_head
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "INTERLINKING"

LINK_001 = Check("LINK-001", "Has Internal Links", C)
LINK_002 = Check("LINK-002", "Internal Links Status", C)
LINK_003 = Check("LINK-003", "No Internal Nofollow", C)
LINK_004 = Check("LINK-004", "Link to Startpage", C)
LINK_005 = Check("LINK-005", "No Parameterized Links", C)
LINK_006 = Check("LINK-006", "Links to Canonical URLs", C)
LINK_007 = Check("LINK-007", "No Links to Dead Weight", C)
LINK_008 = Check("LINK-008", "Section Link Sampling", C)


def check_has_internal_links(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    count = links["internal_count"]
    if count >= 5:
        return LINK_001.result(Severity.PASS, f"{count} internal links")
    if count > 0:
        return LINK_001.result(Severity.WARN, f"Only {count} internal links - should have more")
    return LINK_001.result(
        Severity.FAIL, "No internal links - every page needs links to other targeted pages"
    )


def check_internal_links_status(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    internal = links["internal"]
    if not internal:
        return LINK_002.result(Severity.INFO, "No internal links")
    sample = random.sample(internal, min(5, len(internal)))
    broken = []
    for link in sample:
        resp = fetch(link["href"])
        if resp.status_code >= 400:
            broken.append({"href": link["href"][:80], "status": resp.status_code})
    if not broken:
        return LINK_002.result(Severity.PASS, f"Sampled {len(sample)} internal links - all OK")
    return LINK_002.result(
        Severity.FAIL, f"{len(broken)}/{len(sample)} sampled links broken", {"broken": broken}
    )


def check_no_nofollow_internal(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    nf_internal = [lnk for lnk in links["internal"] if lnk["nofollow"]]
    if not nf_internal:
        return LINK_003.result(Severity.PASS, "No internal nofollow links (correct)")
    return LINK_003.result(
        Severity.WARN, f"{len(nf_internal)} internal links with nofollow - should not nofollow internal links"
    )


def check_link_to_startpage(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    domain = urlparse(response.final_url).netloc
    start = f"https://{domain}/"
    has_start = any(
        lnk["href"].rstrip("/") + "/" == start or lnk["href"] == start for lnk in links["internal"]
    )
    if has_start:
        return LINK_004.result(Severity.PASS, "Page links to startpage")
    return LINK_004.result(Severity.INFO, "No link to startpage found")


def check_no_parameterized_links(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    param_links = [lnk for lnk in links["internal"] if lnk["has_params"]]
    if not param_links:
        return LINK_005.result(Severity.PASS, "No parameterized internal links (correct - hide from Google)")
    return LINK_005.result(
        Severity.WARN,
        f"{len(param_links)} parameterized links - use data-attributes + JS instead",
        {"examples": [lnk["href"][:80] for lnk in param_links[:5]]},
    )


def canonical_issue(href: str) -> dict[str, object] | None:
    """Why an internal link is not canonical (query string or redirect), or None."""
    if urlparse(href).query:
        return {"href": href[:100], "issue": "has query parameters"}
    resp = fetch_head(href)
    if resp.redirect_chain:
        status = resp.redirect_chain[0].status_code
        return {"href": href[:100], "issue": f"redirects to {resp.final_url[:100]}", "status": status}
    return None


def check_links_to_canonical(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """LINK-006: Internal links point to canonical URLs, not redirecting or parameterised ones."""
    internal = get_links(page)["internal"]
    if not internal:
        return LINK_006.result(Severity.INFO, "No internal links")
    sample = random.sample(internal, min(10, len(internal)))
    issues = [i for i in (canonical_issue(link["href"]) for link in sample) if i]
    if issues:
        msg = f"{len(issues)}/{len(sample)} sampled links are NOT canonical"
        return LINK_006.result(Severity.WARN, msg, {"non_canonical": issues})
    return LINK_006.result(Severity.PASS, f"All {len(sample)} sampled internal links point to canonical URLs")


def check_no_links_to_deadweight(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """LINK-007: Don't link to dead weight pages (noindex, thin, soft-404, error pages)."""
    links = get_links(page)
    internal = links["internal"]
    if not internal:
        return LINK_007.result(Severity.INFO, "No internal links")
    sample = random.sample(internal, min(8, len(internal)))
    deadweight: list[dict] = []
    for link in sample:
        resp = fetch(link["href"])
        if resp.status_code >= 400:
            deadweight.append({"href": link["href"][:100], "issue": f"HTTP {resp.status_code}"})
            continue
        if resp.status_code == 200 and resp.body:
            body_lower = resp.body[:5000].lower()
            if 'name="robots"' in body_lower and "noindex" in body_lower:
                deadweight.append({"href": link["href"][:100], "issue": "noindex page"})
            elif len(resp.body.strip()) < 1000:
                deadweight.append({"href": link["href"][:100], "issue": "very thin content (<1KB)"})
    if deadweight:
        return LINK_007.result(
            Severity.WARN, f"{len(deadweight)} links to dead weight pages", {"deadweight": deadweight}
        )
    return LINK_007.result(Severity.PASS, f"No dead weight pages found in {len(sample)} sampled links")


SECTIONS = ("header", "nav", "main", "footer", "aside")
SECTION_SAMPLE = 5


def section_internal_links(section: Tag, page_url: str) -> list[str]:
    """Unique absolute same-host links inside one page section."""
    domain = urlparse(page_url).netloc
    links = (
        urljoin(page_url, attr(a, "href"))
        for a in tags(section, "a", href=True)
        if not attr(a, "href").startswith(("#", "javascript:", "mailto:", "tel:"))
    )
    return list(dict.fromkeys(link for link in links if urlparse(link).netloc == domain))


@dataclass
class SectionSample:
    links: int
    sampled: int
    broken: list[str]


def sample_section(links: list[str]) -> SectionSample:
    sample = random.sample(links, min(SECTION_SAMPLE, len(links)))
    statuses = {href: fetch_head(href).status_code for href in sample}
    broken = [f"{href[:60]} ({code})" for href, code in statuses.items() if code >= 400 or code == 0]
    return SectionSample(len(links), len(sample), broken)


def check_section_link_sampling(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """LINK-008: Sample links from each page section (header/nav/main/footer/aside) and verify them."""
    results = {
        section: sample_section(section_internal_links(el, response.final_url))
        for section in SECTIONS
        if (el := first_tag(page.soup, section)) is not None
    }
    if not results:
        return LINK_008.result(Severity.INFO, "No header/nav/main/footer/aside sections")
    details: dict[str, object] = {"sections": {k: asdict(v) for k, v in results.items()}}
    broken = sum(len(r.broken) for r in results.values())
    if broken:
        msg = f"{broken} broken link(s) across page sections"
        return LINK_008.result(Severity.FAIL, msg, details)
    summary = ", ".join(f"{k}: {v.sampled}/{v.links} sampled" for k, v in results.items())
    return LINK_008.result(Severity.PASS, f"All sampled links OK - {summary}", details)


checks = {
    "LINK-001": check_has_internal_links,
    "LINK-002": check_internal_links_status,
    "LINK-003": check_no_nofollow_internal,
    "LINK-004": check_link_to_startpage,
    "LINK-005": check_no_parameterized_links,
    "LINK-006": check_links_to_canonical,
    "LINK-007": check_no_links_to_deadweight,
    "LINK-008": check_section_link_sampling,
}

if __name__ == "__main__":
    run_tool("INTERLINKING", checks, "Internal interlinking checks")
