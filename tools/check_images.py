"""Image optimization checks: alt text, dimensions, lazy loading, formats, filenames, primary image."""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from shared.html_parser import ParsedPage, attr, first_tag, get_images, tags
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "IMAGES"
ABOVE_FOLD = 3
MODERN_FORMATS = {"webp", "avif"}
GENERIC_FILENAME = re.compile(r"^(img|image|photo|pic|DSC|IMG_)\d+", re.I)
LARGE_IMAGE_PX = 1200
ALT_WORDS_MIN, ALT_WORDS_MAX = 3, 10
NO_IMAGES = "No images"
NO_PHRASE = "No targeted phrase configured for this URL"

ALT = Check("IMG-001", "Images Have Alt Text", C)
DIMENSIONS = Check("IMG-002", "Images Have Dimensions", C)
ABOVE_FOLD_LAZY = Check("IMG-003", "Above Fold Not Lazy", C)
FILENAMES = Check("IMG-004", "Image Filenames", C)
FORMAT = Check("IMG-005", "Modern Image Format", C)
RESPONSIVE = Check("IMG-006", "Responsive Images", C)
FILENAME_KEYWORDS = Check("IMG-007", "Filename Has Keywords", C)
ALT_LENGTH = Check("IMG-008", "Alt Text Length", C)
PRIMARY = Check("IMG-009", "Primary Image Quality", C)
FIRST_ALT_PHRASE = Check("IMG-010", "First Image Alt Has Phrase", C)


def filename(src: str) -> str:
    return urlparse(src).path.rsplit("/", 1)[-1] if src else ""


def phrase_keywords(phrase: str) -> list[str]:
    return [w.lower() for w in phrase.split() if len(w) > 3]


def check_images_have_alt(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    imgs = get_images(page)
    if not imgs:
        return ALT.result(Severity.INFO, NO_IMAGES)
    missing = [i["src"][:80] for i in imgs if not i["alt"]]
    if not missing:
        return ALT.result(Severity.PASS, f"All {len(imgs)} images have alt text")
    return ALT.result(
        Severity.WARN, f"{len(missing)}/{len(imgs)} images missing alt text", {"missing": missing[:5]}
    )


def check_images_have_dimensions(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    imgs = get_images(page)
    if not imgs:
        return DIMENSIONS.result(Severity.INFO, NO_IMAGES)
    missing = [i["src"][:80] for i in imgs if not i["has_dimensions"]]
    if not missing:
        return DIMENSIONS.result(Severity.PASS, f"All {len(imgs)} images have width+height (CLS safe)")
    msg = f"{len(missing)}/{len(imgs)} images missing width/height"
    return DIMENSIONS.result(Severity.WARN, msg, {"missing": missing[:5]})


def check_above_fold_not_lazy(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    first = get_images(page)[:ABOVE_FOLD]
    if not first:
        return ABOVE_FOLD_LAZY.result(Severity.INFO, NO_IMAGES)
    lazy = [i["src"][:80] for i in first if i["loading"] == "lazy"]
    if not lazy:
        return ABOVE_FOLD_LAZY.result(Severity.PASS, f"First {len(first)} images are not lazy-loaded")
    msg = f"{len(lazy)} above-fold images have loading=lazy (slows LCP)"
    return ABOVE_FOLD_LAZY.result(Severity.WARN, msg, {"lazy_above_fold": lazy})


def check_image_filenames(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    imgs = get_images(page)[:10]
    if not imgs:
        return FILENAMES.result(Severity.INFO, NO_IMAGES)
    bad = [n for n in (filename(i["src"]) for i in imgs) if GENERIC_FILENAME.match(n) or len(n) < 4]
    if not bad:
        return FILENAMES.result(Severity.PASS, "Image filenames are descriptive")
    return FILENAMES.result(Severity.WARN, f"{len(bad)} images have generic filenames", {"generic": bad})


def check_image_format(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    imgs = get_images(page)
    if not imgs:
        return FORMAT.result(Severity.INFO, NO_IMAGES)
    formats = Counter(filename(i["src"]).rsplit(".", 1)[-1].lower() for i in imgs)
    modern = sum(formats[f] for f in MODERN_FORMATS)
    if modern == len(imgs):
        return FORMAT.result(Severity.PASS, "All images use modern formats (WebP/AVIF)")
    if modern:
        return FORMAT.result(Severity.INFO, f"Formats: {dict(formats)} - consider WebP/AVIF for all")
    return FORMAT.result(Severity.WARN, f"No modern image formats found: {dict(formats)}")


def check_images_responsive(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    imgs = tags(page.soup, "img")
    if not imgs:
        return RESPONSIVE.result(Severity.INFO, NO_IMAGES)
    with_srcset = sum(1 for i in imgs if attr(i, "srcset"))
    if with_srcset == len(imgs):
        return RESPONSIVE.result(Severity.PASS, f"All {len(imgs)} images have srcset")
    if with_srcset:
        return RESPONSIVE.result(Severity.INFO, f"{with_srcset}/{len(imgs)} images have srcset")
    return RESPONSIVE.result(Severity.WARN, "No images use srcset for responsive delivery")


def check_filename_has_keywords(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    keywords = phrase_keywords(config.phrase_for(response.final_url) if config else "")
    if not keywords:
        return FILENAME_KEYWORDS.result(Severity.INFO, NO_PHRASE)
    imgs = get_images(page)
    if not imgs:
        return FILENAME_KEYWORDS.result(Severity.INFO, NO_IMAGES)
    if any(kw in filename(i["src"]).lower() for i in imgs for kw in keywords):
        return FILENAME_KEYWORDS.result(Severity.PASS, "An image filename contains a targeted keyword")
    return FILENAME_KEYWORDS.result(
        Severity.WARN, f"No image filename contains a targeted keyword: {keywords}"
    )


def check_alt_text_length(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    with_alt = [i["alt"] for i in get_images(page) if i["alt"]]
    if not with_alt:
        return ALT_LENGTH.result(Severity.INFO, "No alt texts to evaluate")
    bad = [a for a in with_alt if not ALT_WORDS_MIN <= len(a.split()) <= ALT_WORDS_MAX]
    if len(bad) / len(with_alt) > 0.5:
        msg = f"{len(bad)}/{len(with_alt)} alt texts outside {ALT_WORDS_MIN}-{ALT_WORDS_MAX} words"
        return ALT_LENGTH.result(Severity.WARN, msg, {"examples": [a[:80] for a in bad[:5]]})
    return ALT_LENGTH.result(Severity.PASS, f"Most alt texts have {ALT_WORDS_MIN}-{ALT_WORDS_MAX} words")


def check_primary_image_quality(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """IMG-009: The primary image should be at least 1200px wide (Discover / social previews)."""
    imgs = get_images(page)
    if not imgs:
        return PRIMARY.result(Severity.INFO, NO_IMAGES)
    digits = re.sub(r"\D", "", str(imgs[0]["width"]))
    if digits:
        width = int(digits)
        if width >= LARGE_IMAGE_PX:
            return PRIMARY.result(Severity.PASS, f"Primary image width: {width}px")
        msg = f"Primary image width: {width}px - needs >= {LARGE_IMAGE_PX}px for Discover/social"
        return PRIMARY.result(Severity.WARN, msg, {"src": imgs[0]["src"][:80]})
    if attr(first_tag(page.soup, "meta", property="og:image"), "content"):
        return PRIMARY.result(
            Severity.INFO, f"Primary image width unknown - check og:image is >= {LARGE_IMAGE_PX}px"
        )
    return PRIMARY.result(Severity.WARN, "Cannot determine primary image size - set width or og:image")


def check_first_image_alt_has_phrase(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """IMG-010: The first image's alt text should mention the targeted phrase."""
    phrase = config.phrase_for(response.final_url) if config else ""
    if not phrase:
        return FIRST_ALT_PHRASE.result(Severity.INFO, NO_PHRASE)
    imgs = get_images(page)
    if not imgs:
        return FIRST_ALT_PHRASE.result(Severity.INFO, NO_IMAGES)
    alt = imgs[0]["alt"].lower()
    keywords = phrase_keywords(phrase)
    if sum(1 for kw in keywords if kw in alt) >= len(keywords) * 0.5:
        return FIRST_ALT_PHRASE.result(
            Severity.PASS, f"First image alt contains phrase keywords: '{alt[:60]}'"
        )
    return FIRST_ALT_PHRASE.result(Severity.WARN, f"First image alt '{alt[:60]}' misses phrase '{phrase}'")


checks = {
    "IMG-001": check_images_have_alt,
    "IMG-002": check_images_have_dimensions,
    "IMG-003": check_above_fold_not_lazy,
    "IMG-004": check_image_filenames,
    "IMG-005": check_image_format,
    "IMG-006": check_images_responsive,
    "IMG-007": check_filename_has_keywords,
    "IMG-008": check_alt_text_length,
    "IMG-009": check_primary_image_quality,
    "IMG-010": check_first_image_alt_has_phrase,
}

if __name__ == "__main__":
    run_tool(C, checks, "Image optimization checks")
