"""Unit tests for plugin trust persistence helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.trust_store import is_runtime_plugin_trusted, load_plugin_trust, set_runtime_plugin_trust

pytestmark = pytest.mark.unit


def test_load_plugin_trust_defaults_to_empty_mapping(tmp_path: Path) -> None:
    payload = load_plugin_trust(state_root=str(tmp_path.resolve()))

    assert payload["schema_version"] == 1
    assert payload["trusted_runtime_plugins"] == {}


def test_set_runtime_plugin_trust_persists_true_and_false(tmp_path: Path) -> None:
    state_root = str(tmp_path.resolve())

    assert is_runtime_plugin_trusted("acme.demo", "1.0.0", state_root=state_root) is False

    set_runtime_plugin_trust("acme.demo", "1.0.0", trusted=True, state_root=state_root)
    assert is_runtime_plugin_trusted("acme.demo", "1.0.0", state_root=state_root) is True

    set_runtime_plugin_trust("acme.demo", "1.0.0", trusted=False, state_root=state_root)
    assert is_runtime_plugin_trusted("acme.demo", "1.0.0", state_root=state_root) is False
