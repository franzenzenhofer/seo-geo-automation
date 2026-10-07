"""HTML parsing helpers for SEO data extraction (BeautifulSoup based, typed)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, Tag

NON_TEXT_TAGS = {"script", "style", "noscript", "template"}
SKIPPED_HREF_PREFIXES = ("#", "javascript:", "mailto:", "tel:")
TRACKING_PARAMS = re.compile(r"[?&](utm_|gclid|fbclid|msclkid)")


@dataclass
class ParsedPage:
    url: str
    html: str
    soup: BeautifulSoup = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.soup = BeautifulSoup(self.html, "html.parser")

    @property
    def head(self) -> Tag | None:
        return first_tag(self.soup, "head")

    @property
    def body(self) -> Tag | None:
        return first_tag(self.soup, "body")


def parse_html(html: str, url: str = "") -> ParsedPage:
    return ParsedPage(url=url, html=html)


def attr(el: Tag | None, name: str) -> str:
    """Attribute value as a plain string (multi-valued attributes are space-joined)."""
    if el is None:
        return ""
    value = el.get(name)
    if value is None:
        return ""
    return value if isinstance(value, str) else " ".join(value)


def tags(root: Tag | None, name: str | list[str] | bool | None = None, **kwargs: Any) -> list[Tag]:
    """find_all() restricted to Tag results."""
    if root is None:
        return []
    return [t for t in root.find_all(name, **kwargs) if isinstance(t, Tag)]


def first_tag(root: Tag | None, name: str | None = None, **kwargs: Any) -> Tag | None:
    found = root.find(name, **kwargs) if root is not None else None
    return found if isinstance(found, Tag) else None


def meta_by_name(page: ParsedPage, name: str) -> list[Tag]:
    return [m for m in tags(page.soup, "meta") if attr(m, "name").lower() == name]


def get_title(page: ParsedPage) -> dict[str, Any]:
    titles = tags(page.soup, "title")
    text = titles[0].get_text(strip=True) if titles else ""
    return {"count": len(titles), "text": text, "length": len(text)}


def get_meta_description(page: ParsedPage) -> dict[str, Any]:
    descs = meta_by_name(page, "description")
    content = attr(descs[0], "content") if descs else ""
    return {"count": len(descs), "content": content, "length": len(content)}


def get_canonical(page: ParsedPage) -> dict[str, Any]:
    canonicals = tags(page.soup, "link", rel="canonical")
    href = attr(canonicals[0], "href") if canonicals else ""
    head = page.head
    in_head = bool(canonicals and head and canonicals[0] in head.descendants)
    return {
        "count": len(canonicals),
        "href": href,
        "in_head": in_head,
        "is_self_referencing": urls_match(href, page.url) if href and page.url else None,
        "is_absolute": href.startswith("http"),
        "is_https": href.startswith("https") if href else None,
        "has_tracking_params": bool(TRACKING_PARAMS.search(href)),
    }


def get_meta_robots(page: ParsedPage) -> dict[str, Any]:
    robots_tags = [
        {"name": attr(m, "name").lower(), "content": attr(m, "content")}
        for m in tags(page.soup, "meta")
        if attr(m, "name").lower() in ("robots", "googlebot")
    ]
    return {
        "tags": robots_tags,
        "count": len(robots_tags),
        "has_noindex": any("noindex" in r["content"].lower() for r in robots_tags),
        "has_nofollow": any("nofollow" in r["content"].lower() for r in robots_tags),
    }


def get_viewport(page: ParsedPage) -> dict[str, Any]:
    vp = first_tag(page.soup, "meta", attrs={"name": "viewport"})
    return {"present": vp is not None, "content": attr(vp, "content")}


def get_charset(page: ParsedPage) -> dict[str, Any]:
    val = attr(first_tag(page.soup, "meta", charset=True), "charset")
    if not val:
        ct = first_tag(page.soup, "meta", attrs={"http-equiv": re.compile("content-type", re.I)})
        match = re.search(r"charset=([^\s;]+)", attr(ct, "content"))
        val = match.group(1) if match else ""
    return {"present": bool(val), "value": val, "is_utf8": val.upper() == "UTF-8"}


def get_lang(page: ParsedPage) -> dict[str, Any]:
    lang = attr(first_tag(page.soup, "html"), "lang")
    return {"present": bool(lang), "value": lang}


def get_hreflang(page: ParsedPage) -> list[dict[str, str]]:
    links = tags(page.soup, "link", rel="alternate", hreflang=True)
    return [{"hreflang": attr(lnk, "hreflang"), "href": attr(lnk, "href")} for lnk in links]


def _meta_with_prefix(page: ParsedPage, key: str, prefix: str) -> dict[str, str]:
    return {
        attr(m, key): attr(m, "content") for m in tags(page.soup, "meta") if attr(m, key).startswith(prefix)
    }


def get_og_tags(page: ParsedPage) -> dict[str, str]:
    return _meta_with_prefix(page, "property", "og:")


def get_twitter_tags(page: ParsedPage) -> dict[str, str]:
    return _meta_with_prefix(page, "name", "twitter:")


def get_headings(page: ParsedPage) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for level in range(1, 7):
        found = tags(page.soup, f"h{level}")
        result[f"h{level}_count"] = len(found)
        result[f"h{level}_texts"] = [h.get_text(strip=True) for h in found][:10]
    return result


def get_images(page: ParsedPage) -> list[dict[str, Any]]:
    images = []
    for img in tags(page.soup, "img"):
        src = attr(img, "src")
        width, height = attr(img, "width"), attr(img, "height")
        images.append(
            {
                "src": urljoin(page.url, src) if page.url and src else src,
                "alt": attr(img, "alt"),
                "width": width,
                "height": height,
                "loading": attr(img, "loading"),
                "has_dimensions": bool(width and height),
            }
        )
    return images


def _link_data(a: Tag, page_url: str) -> dict[str, Any] | None:
    href = attr(a, "href")
    if not href or href.startswith(SKIPPED_HREF_PREFIXES):
        return None
    abs_href = urljoin(page_url, href) if page_url else href
    return {
        "href": abs_href,
        "text": a.get_text(strip=True)[:100],
        "nofollow": "nofollow" in attr(a, "rel").split(),
        "has_params": "?" in abs_href,
    }


def get_links(page: ParsedPage) -> dict[str, Any]:
    domain = urlparse(page.url).netloc if page.url else ""
    internal: list[dict[str, Any]] = []
    external: list[dict[str, Any]] = []
    for a in tags(page.soup, "a", href=True):
        data = _link_data(a, page.url)
        if data is None:
            continue
        netloc = urlparse(data["href"]).netloc
        (internal if netloc in (domain, "") else external).append(data)
    return {
        "internal": internal,
        "external": external,
        "internal_count": len(internal),
        "external_count": len(external),
        "nofollow_count": sum(1 for lnk in internal + external if lnk["nofollow"]),
        "parameterized_count": sum(1 for lnk in internal if lnk["has_params"]),
    }


def get_json_ld(page: ParsedPage) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for script in tags(page.soup, "script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        blocks.extend(item for item in items if isinstance(item, dict))
    return blocks


def get_scripts_in_head(page: ParsedPage) -> list[dict[str, Any]]:
    return [
        {
            "src": attr(s, "src"),
            "async": s.has_attr("async"),
            "defer": s.has_attr("defer"),
            "blocking": not (s.has_attr("async") or s.has_attr("defer") or attr(s, "type") == "module"),
        }
        for s in tags(page.head, "script", src=True)
    ]


def get_body_text(page: ParsedPage) -> str:
    """Visible body text (script/style/noscript/template excluded). Does not mutate the soup."""
    body = page.body
    if body is None:
        return ""
    parts = [
        str(s).strip()
        for s in body.find_all(string=True)
        if not isinstance(s, Comment) and s.parent is not None and s.parent.name not in NON_TEXT_TAGS
    ]
    return " ".join(p for p in parts if p)


def get_content_diversity(page: ParsedPage) -> dict[str, int]:
    root = page.body or page.soup

    def count(*names: str) -> int:
        return sum(len(tags(root, n)) for n in names)

    return {
        "paragraphs": count("p"),
        "tables": count("table"),
        "lists_ul": count("ul"),
        "lists_ol": count("ol"),
        "definition_lists": count("dl"),
        "images": count("img"),
        "videos": count("video", "iframe"),
        "blockquotes": count("blockquote"),
    }


def get_favicon(page: ParsedPage) -> dict[str, Any]:
    icon = first_tag(page.soup, "link", rel=re.compile(r"(icon|shortcut)", re.I))
    href = attr(icon, "href")
    if page.url and href:
        href = urljoin(page.url, href)
    return {"present": icon is not None, "href": href}


def urls_match(url1: str, url2: str) -> bool:
    p1, p2 = urlparse(url1), urlparse(url2)
    return p1.netloc == p2.netloc and (p1.path.rstrip("/") or "/") == (p2.path.rstrip("/") or "/")
