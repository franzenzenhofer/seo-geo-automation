"""Video checks: embedded videos, VideoObject structured data, lazy-loaded video iframes."""

from __future__ import annotations

from bs4 import Tag

from shared.html_parser import ParsedPage, attr, get_json_ld, tags
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "VIDEO"
VIDEO_HOSTS = ("youtube", "youtu.be", "vimeo")
VIDEO_OBJECT_FIELDS = ("name", "description", "thumbnailUrl", "uploadDate")

VIDEO_001 = Check("VIDEO-001", "Video Present", C)
VIDEO_002 = Check("VIDEO-002", "VideoObject Schema", C)
VIDEO_003 = Check("VIDEO-003", "Video Iframe Lazy", C)


def is_video_iframe(iframe: Tag) -> bool:
    src = (attr(iframe, "src") + " " + attr(iframe, "data-src")).lower()
    return any(host in src for host in VIDEO_HOSTS)


def video_iframes(page: ParsedPage) -> list[Tag]:
    return [i for i in tags(page.soup, "iframe") if is_video_iframe(i)]


def check_video_present(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    videos, iframes = len(tags(page.soup, "video")), len(video_iframes(page))
    if videos + iframes:
        msg = f"{videos + iframes} videos found ({videos} <video>, {iframes} iframe)"
        return VIDEO_001.result(Severity.INFO, msg)
    return VIDEO_001.result(Severity.INFO, "No videos found")


def check_video_schema(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    for block in get_json_ld(page):
        types = block.get("@type", "")
        if "VideoObject" not in (types if isinstance(types, list) else [types]):
            continue
        missing = [f for f in VIDEO_OBJECT_FIELDS if not block.get(f)]
        if missing:
            return VIDEO_002.result(Severity.WARN, f"VideoObject missing: {missing}")
        msg = "VideoObject with all required fields"
        return VIDEO_002.result(Severity.PASS, msg)
    return VIDEO_002.result(Severity.INFO, "No VideoObject structured data")


def check_video_lazy_loading(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    iframes = video_iframes(page)
    if not iframes:
        return VIDEO_003.result(Severity.INFO, "No video iframes")
    lazy = sum(1 for i in iframes if attr(i, "loading") == "lazy" or attr(i, "data-src"))
    sev = Severity.PASS if lazy == len(iframes) else Severity.WARN
    return VIDEO_003.result(sev, f"{lazy}/{len(iframes)} video iframes lazy-load")


checks = {
    "VIDEO-001": check_video_present,
    "VIDEO-002": check_video_schema,
    "VIDEO-003": check_video_lazy_loading,
}

if __name__ == "__main__":
    run_tool(C, checks, "Video optimization checks")
