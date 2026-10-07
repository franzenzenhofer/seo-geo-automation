"""Optional Google Search Console client.

Enabled only when GSC_CREDENTIALS points to a JSON file that is either
- a service-account key (the service account must be added as a user of the GSC property), or
- an OAuth "authorized_user" file (fields: client_id, client_secret, refresh_token).
API reference: https://developers.google.com/webmaster-tools/v1/api_reference_index
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from shared.settings import ENV_GSC_CREDENTIALS, optional_path
from shared.types import Severity, SiteConfig

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
GSC_NOT_CONFIGURED = f"GSC skipped: set {ENV_GSC_CREDENTIALS} to a credentials JSON (see README)"
NO_PROPERTY = "GSC skipped: add gsc_property to the config (e.g. sc-domain:example.com)"


@dataclass(frozen=True)
class GscContext:
    service: Any
    site_url: str


@dataclass(frozen=True)
class GscUnavailable:
    reason: str
    severity: Severity


def gsc_configured() -> bool:
    return optional_path(ENV_GSC_CREDENTIALS) is not None


def load_credentials(path: Path) -> Any:
    """Build google-auth credentials from a service-account or authorized-user JSON file."""
    from google.oauth2 import credentials as user_credentials
    from google.oauth2 import service_account

    info = json.loads(path.read_text(encoding="utf-8"))
    if info.get("type") == "service_account":
        return service_account.Credentials.from_service_account_info(info, scopes=GSC_SCOPES)
    return user_credentials.Credentials.from_authorized_user_info(info, scopes=GSC_SCOPES)


def access_token() -> str:
    """Fresh OAuth access token for tools that call Google APIs themselves; empty if unset."""
    path = optional_path(ENV_GSC_CREDENTIALS)
    if path is None:
        return ""
    from google.auth.transport.requests import Request

    creds = load_credentials(path)
    creds.refresh(Request())
    return str(creds.token or "")


def gsc_context(config: SiteConfig | None) -> GscContext | GscUnavailable:
    """Authenticated service plus property, or why GSC checks cannot run."""
    path = optional_path(ENV_GSC_CREDENTIALS)
    if path is None:
        return GscUnavailable(GSC_NOT_CONFIGURED, Severity.INFO)
    if not config or not config.gsc_property:
        return GscUnavailable(NO_PROPERTY, Severity.INFO)
    if not path.exists():
        return GscUnavailable(f"{ENV_GSC_CREDENTIALS} file not found: {path}", Severity.ERROR)
    try:
        from googleapiclient.discovery import build

        service = build("searchconsole", "v1", credentials=load_credentials(path))
    except Exception as exc:  # google-auth raises many unrelated exception types
        return GscUnavailable(f"GSC auth error: {exc}", Severity.ERROR)
    return GscContext(service=service, site_url=config.gsc_property)


def _execute(request: Any) -> dict[str, Any]:
    try:
        result: dict[str, Any] = request.execute()
    except Exception as exc:  # googleapiclient HttpError and transport errors
        return {"error": str(exc)}
    return result


def url_inspection(ctx: GscContext, url: str) -> dict[str, Any]:
    body = {"inspectionUrl": url, "siteUrl": ctx.site_url}
    result = _execute(ctx.service.urlInspection().index().inspect(body=body))
    if "error" in result:
        return result
    inspection: dict[str, Any] = result.get("inspectionResult", {})
    return inspection


def page_top_queries(ctx: GscContext, url: str, days: int = 90) -> dict[str, Any]:
    end = datetime.now()
    body = {
        "startDate": (end - timedelta(days=days)).strftime("%Y-%m-%d"),
        "endDate": end.strftime("%Y-%m-%d"),
        "dimensions": ["query"],
        "dimensionFilterGroups": [{"filters": [{"dimension": "page", "expression": url}]}],
        "rowLimit": 10,
    }
    return _execute(ctx.service.searchanalytics().query(siteUrl=ctx.site_url, body=body))


def list_sitemaps(ctx: GscContext) -> dict[str, Any]:
    return _execute(ctx.service.sitemaps().list(siteUrl=ctx.site_url))


def sitemap_summary(ctx: GscContext) -> dict[str, Any]:
    """Sitemaps registered in GSC with submitted URLs, errors and warnings.

    GSC no longer reports indexed counts per sitemap (contents[].indexed is deprecated:
    https://developers.google.com/webmaster-tools/v1/sitemaps), so none are returned here.
    """
    result = list_sitemaps(ctx)
    if "error" in result:
        return result
    rows = [
        {
            "path": sm.get("path", ""),
            "submitted": sum(int(c.get("submitted", "0")) for c in sm.get("contents", [])),
            "errors": int(sm.get("errors", "0")),
            "warnings": int(sm.get("warnings", "0")),
            "lastDownloaded": sm.get("lastDownloaded", ""),
        }
        for sm in result.get("sitemap", [])
    ]
    return {
        "sitemaps": rows,
        "submitted": sum(r["submitted"] for r in rows),
        "errors": sum(r["errors"] for r in rows),
        "warnings": sum(r["warnings"] for r in rows),
    }
