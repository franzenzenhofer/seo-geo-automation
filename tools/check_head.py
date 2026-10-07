"""HEAD tag SEO checks - title, meta, canonical, viewport, charset, etc."""

from __future__ import annotations

from shared.html_parser import ParsedPage as Pg
from shared.html_parser import (
    get_canonical,
    get_charset,
    get_favicon,
    get_lang,
    get_meta_description,
    get_meta_robots,
    get_scripts_in_head,
    get_title,
    get_viewport,
    meta_by_name,
)
from shared.http_client import HttpResponse as Rsp
from shared.tool_base import run_tool
from shared.types import CheckResult as R
from shared.types import Severity, SiteConfig

C, P, W, F, INF = "HEAD", Severity.PASS, Severity.WARN, Severity.FAIL, Severity.INFO


def _canon(cid: str, name: str, page: Pg) -> dict | R:
    c = get_canonical(page)
    return R(cid, name, C, INF, "No canonical to check") if not c["href"] else c


def check_title_present(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    t = get_title(page)
    if t["count"] == 1 and t["text"]:
        return R("HEAD-001", "title_present", C, P, f"Title found: '{t['text']}'")
    if t["count"] == 0 or not t["text"]:
        return R("HEAD-001", "title_present", C, F, "No title tag or title is empty")
    return R("HEAD-001", "title_present", C, F, f"Found {t['count']} title tags, expected 1")


def check_title_length(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    n = get_title(page)["length"]
    return R(
        "HEAD-002", "title_length", C, P if 40 <= n <= 120 else W, f"Title length {n} chars (optimal: 40-120)"
    )


def check_title_has_brand(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    brand = cfg.brand_name if cfg else ""
    if not brand:
        return R("HEAD-003", "title_has_brand", C, INF, "No brand_name in config, skipping")
    hit = brand.lower() in get_title(page)["text"].lower()
    return R(
        "HEAD-003",
        "title_has_brand",
        C,
        P if hit else W,
        f"Brand '{brand}' {'found' if hit else 'missing'} in title",
    )


def check_meta_description_present(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    m = get_meta_description(page)
    if m["count"] == 1 and m["content"]:
        return R("HEAD-004", "meta_description_present", C, P, "Meta description found")
    if m["count"] == 0 or not m["content"]:
        return R("HEAD-004", "meta_description_present", C, F, "No meta description found")
    return R("HEAD-004", "meta_description_present", C, F, f"Found {m['count']} meta descriptions")


def check_meta_description_length(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    n = get_meta_description(page)["length"]
    return R(
        "HEAD-005",
        "meta_description_length",
        C,
        P if 70 <= n <= 160 else W,
        f"Length {n} chars (optimal: 70-160)",
    )


def check_canonical_present(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    c = get_canonical(page)
    return R(
        "HEAD-006",
        "canonical_present",
        C,
        P if c["href"] else F,
        f"Canonical: {c['href']}" if c["href"] else "No canonical link found",
    )


def check_canonical_self_referencing(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    c = _canon("HEAD-007", "canonical_self_referencing", page)
    if isinstance(c, R):
        return c
    ok = c["is_self_referencing"]
    return R(
        "HEAD-007",
        "canonical_self_referencing",
        C,
        P if ok else W,
        "Self-referencing" if ok else f"Points elsewhere: {c['href']}",
    )


def check_canonical_absolute(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    c = _canon("HEAD-008", "canonical_absolute", page)
    if isinstance(c, R):
        return c
    return R(
        "HEAD-008",
        "canonical_absolute",
        C,
        P if c["is_absolute"] else F,
        "Absolute URL" if c["is_absolute"] else "Not an absolute URL",
    )


def check_canonical_https(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    c = _canon("HEAD-009", "canonical_https", page)
    if isinstance(c, R):
        return c
    if not rsp.final_url.startswith("https"):
        return R("HEAD-009", "canonical_https", C, INF, "Page is not HTTPS, skipping")
    return R(
        "HEAD-009",
        "canonical_https",
        C,
        P if c["is_https"] else F,
        "Uses HTTPS" if c["is_https"] else "Does not use HTTPS on HTTPS page",
    )


def check_canonical_no_tracking(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    c = _canon("HEAD-010", "canonical_no_tracking", page)
    if isinstance(c, R):
        return c
    ok = not c["has_tracking_params"]
    return R(
        "HEAD-010",
        "canonical_no_tracking",
        C,
        P if ok else F,
        "No tracking params" if ok else f"Tracking params in canonical: {c['href']}",
    )


def check_meta_robots(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    r = get_meta_robots(page)
    if r["has_noindex"]:
        return R("HEAD-011", "meta_robots", C, W, "Page has noindex directive")
    return R(
        "HEAD-011",
        "meta_robots",
        C,
        W if r["has_nofollow"] else P,
        "Page has nofollow directive" if r["has_nofollow"] else "No restrictive robots directives",
    )


def check_viewport_present(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    v = get_viewport(page)
    return R(
        "HEAD-012",
        "viewport_present",
        C,
        P if v["present"] else F,
        f"Viewport: {v['content']}" if v["present"] else "No viewport meta tag found",
    )


def check_charset_utf8(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    cs = get_charset(page)
    if not cs["present"]:
        return R("HEAD-013", "charset_utf8", C, F, "No charset declared")
    return R(
        "HEAD-013",
        "charset_utf8",
        C,
        P if cs["is_utf8"] else W,
        "UTF-8" if cs["is_utf8"] else f"Charset '{cs['value']}', expected UTF-8",
    )


def check_lang_attribute(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    la = get_lang(page)
    return R(
        "HEAD-014",
        "lang_attribute",
        C,
        P if la["present"] else F,
        f"Lang: '{la['value']}'" if la["present"] else "No lang attribute on <html>",
    )


def check_no_meta_keywords(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    kw = meta_by_name(page, "keywords")
    return R(
        "HEAD-015",
        "no_meta_keywords",
        C,
        P if not kw else W,
        "No meta keywords (deprecated)" if not kw else "Meta keywords present (deprecated since 2009)",
    )


def check_no_duplicate_meta(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    dupes = [
        n
        for n, ct in [
            ("title", get_title(page)["count"]),
            ("description", get_meta_description(page)["count"]),
            ("canonical", get_canonical(page)["count"]),
        ]
        if ct > 1
    ]
    return R(
        "HEAD-016",
        "no_duplicate_meta",
        C,
        F if dupes else P,
        f"Duplicates: {', '.join(dupes)}" if dupes else "No duplicates",
    )


def check_favicon_link(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    f = get_favicon(page)
    return R(
        "HEAD-017",
        "favicon_link",
        C,
        P if f["present"] else W,
        f"Favicon: {f['href']}" if f["present"] else "No favicon link tag found",
    )


def check_no_blocking_scripts(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    bl = [s for s in get_scripts_in_head(page) if s["blocking"]]
    return R(
        "HEAD-018",
        "no_blocking_scripts",
        C,
        P if not bl else W,
        "No render-blocking scripts in head"
        if not bl
        else f"{len(bl)} blocking: {[s['src'] for s in bl[:3]]}",
    )


def check_canonical_in_head(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    c = _canon("HEAD-019", "canonical_in_head", page)
    if isinstance(c, R):
        return c
    return R(
        "HEAD-019",
        "canonical_in_head",
        C,
        P if c["in_head"] else F,
        "Inside <head>" if c["in_head"] else "Outside <head>",
    )


checks = {
    f"HEAD-{i:03d}": fn
    for i, fn in enumerate(
        [
            check_title_present,
            check_title_length,
            check_title_has_brand,
            check_meta_description_present,
            check_meta_description_length,
            check_canonical_present,
            check_canonical_self_referencing,
            check_canonical_absolute,
            check_canonical_https,
            check_canonical_no_tracking,
            check_meta_robots,
            check_viewport_present,
            check_charset_utf8,
            check_lang_attribute,
            check_no_meta_keywords,
            check_no_duplicate_meta,
            check_favicon_link,
            check_no_blocking_scripts,
            check_canonical_in_head,
        ],
        start=1,
    )
}

if __name__ == "__main__":
    run_tool("HEAD", checks, description="SEO HEAD tag audit checks")
