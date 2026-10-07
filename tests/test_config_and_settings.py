from __future__ import annotations

from pathlib import Path

import pytest

from shared.config import ConfigError, load_config
from shared.settings import PROJECT_ROOT

EXAMPLE_CONFIG = PROJECT_ROOT / "configs" / "example.config.json"


def test_example_config_loads() -> None:
    config = load_config(EXAMPLE_CONFIG)
    assert config.domain == "loremipsum.franzai.com"
    assert len(config.important_pages) == 3
    assert config.important_pages[0].page_type == "homepage"
    assert config.robots_url.endswith("/robots.txt")


def test_phrase_lookup_ignores_trailing_slash() -> None:
    config = load_config(EXAMPLE_CONFIG)
    assert config.phrase_for("https://loremipsum.franzai.com/lorem-ipsum-history") == "lorem ipsum history"
    assert config.phrase_for("https://loremipsum.franzai.com/unknown/") == ""


def test_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")


def test_config_without_required_fields_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"domain": "example.com"}', encoding="utf-8")
    with pytest.raises(ConfigError, match="start_url"):
        load_config(bad)
