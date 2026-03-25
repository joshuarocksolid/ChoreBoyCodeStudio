"""Unit tests for per-project plugin policy persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.plugins.project_config import (
    is_plugin_enabled_in_project,
    is_plugin_version_pinned,
    load_project_plugin_config,
    preferred_provider_for,
    preferred_provider_key,
    set_project_plugin_enabled,
    set_project_plugin_version_pin,
    set_project_preferred_provider,
)

pytestmark = pytest.mark.unit


def test_load_project_plugin_config_defaults_when_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    config = load_project_plugin_config(str(project_root))

    assert config.enabled_plugins == ()
    assert config.disabled_plugins == ()
    assert config.pinned_versions == {}
    assert config.preferred_providers == {}


def test_project_plugin_config_persists_enable_pin_and_provider_preferences(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)

    set_project_plugin_enabled(str(project_root), "cbcs.python_tools", enabled=True)
    set_project_plugin_version_pin(str(project_root), "cbcs.python_tools", "1.0.0")
    set_project_preferred_provider(
        str(project_root),
        preferred_provider_key("formatter", language="python"),
        "cbcs.python_tools:formatter",
    )

    config = load_project_plugin_config(str(project_root))

    assert config.enabled_plugins == ("cbcs.python_tools",)
    assert config.pinned_versions == {"cbcs.python_tools": "1.0.0"}
    assert preferred_provider_for("formatter", config=config, language="python") == "cbcs.python_tools:formatter"

    payload = json.loads((project_root / "cbcs" / "plugins.json").read_text(encoding="utf-8"))
    assert payload["pinned_versions"]["cbcs.python_tools"] == "1.0.0"
    assert payload["preferred_providers"]["formatter:python"] == "cbcs.python_tools:formatter"


def test_project_plugin_config_enable_disable_and_pin_resolution(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)

    set_project_plugin_enabled(str(project_root), "cbcs.pytest", enabled=False)
    set_project_plugin_version_pin(str(project_root), "cbcs.pytest", "1.0.0")
    config = load_project_plugin_config(str(project_root))

    assert is_plugin_enabled_in_project("cbcs.pytest", config=config, default_enabled=True) is False
    assert is_plugin_version_pinned("cbcs.pytest", "1.0.0", config=config) is True
    assert is_plugin_version_pinned("cbcs.pytest", "2.0.0", config=config) is False
