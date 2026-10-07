"""Shared type definitions for SEO audit system."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    INFO = "INFO"
    ERROR = "ERROR"


@dataclass
class CheckResult:
    check_id: str
    name: str
    category: str
    severity: Severity
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    source_doc: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckResult:
        return cls(
            check_id=data["check_id"],
            name=data["name"],
            category=data["category"],
            severity=Severity(data["severity"]),
            message=data["message"],
            details=data.get("details", {}),
            source_doc=data.get("source_doc", ""),
        )


@dataclass(frozen=True)
class Check:
    """Identity of one check; builds its CheckResult so call sites stay one line."""

    check_id: str
    name: str
    category: str

    def result(self, severity: Severity, message: str, details: dict[str, Any] | None = None) -> CheckResult:
        return CheckResult(self.check_id, self.name, self.category, severity, message, details or {})


@dataclass
class CategoryResult:
    category: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.severity in (Severity.FAIL, Severity.ERROR))

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.WARN)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "checks": [c.to_dict() for c in self.checks],
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "warn_count": self.warn_count,
            "total": len(self.checks),
        }


@dataclass
class PageConfig:
    url: str
    page_type: str = "page"

    @classmethod
    def from_raw(cls, raw: str | dict[str, Any]) -> PageConfig:
        if isinstance(raw, str):
            return cls(url=raw, page_type="page")
        return cls(url=raw["url"], page_type=raw.get("type", "page"))


@dataclass
class SiteConfig:
    domain: str
    start_url: str
    brand_name: str = ""
    language: str = "en"
    targeted_phrases: dict[str, str] = field(default_factory=dict)
    important_pages: list[PageConfig] = field(default_factory=list)
    sitemap_url: str = ""
    robots_url: str = ""
    gsc_property: str = ""

    def phrase_for(self, url: str) -> str:
        """Targeted phrase configured for this URL (trailing-slash insensitive), or ''."""
        phrases = {u.rstrip("/"): p for u, p in self.targeted_phrases.items()}
        return phrases.get(url.rstrip("/"), "")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteConfig:
        data = dict(data)
        raw_pages = data.pop("important_pages", [])
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        config = cls(**filtered)
        config.important_pages = [PageConfig.from_raw(p) for p in raw_pages]
        return config


@dataclass
class FullReport:
    domain: str
    url: str
    timestamp: str
    categories: list[CategoryResult] = field(default_factory=list)

    @property
    def total_checks(self) -> int:
        return sum(len(c.checks) for c in self.categories)

    @property
    def total_pass(self) -> int:
        return sum(c.pass_count for c in self.categories)

    @property
    def total_fail(self) -> int:
        return sum(c.fail_count for c in self.categories)

    @property
    def total_warn(self) -> int:
        return sum(c.warn_count for c in self.categories)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "url": self.url,
            "timestamp": self.timestamp,
            "categories": [c.to_dict() for c in self.categories],
            "summary": {
                "total": self.total_checks,
                "pass": self.total_pass,
                "fail": self.total_fail,
                "warn": self.total_warn,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass
class PageResult:
    url: str
    slug: str
    page_type: str
    report: FullReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "slug": self.slug,
            "page_type": self.page_type,
            "report": self.report.to_dict(),
        }


@dataclass
class MultiPageReport:
    domain: str
    timestamp: str
    pages: list[PageResult] = field(default_factory=list)

    @property
    def total_checks(self) -> int:
        return sum(p.report.total_checks for p in self.pages)

    @property
    def total_pass(self) -> int:
        return sum(p.report.total_pass for p in self.pages)

    @property
    def total_fail(self) -> int:
        return sum(p.report.total_fail for p in self.pages)

    @property
    def total_warn(self) -> int:
        return sum(p.report.total_warn for p in self.pages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "timestamp": self.timestamp,
            "pages": [p.to_dict() for p in self.pages],
            "summary": {
                "total_pages": len(self.pages),
                "total_checks": self.total_checks,
                "pass": self.total_pass,
                "fail": self.total_fail,
                "warn": self.total_warn,
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
