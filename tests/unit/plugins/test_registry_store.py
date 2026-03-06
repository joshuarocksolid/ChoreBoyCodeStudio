"""Unit tests for plugin registry persistence helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.models import PluginRegistryEntry
from app.plugins.registry_store import (
    clear_registry_entry_failures,
    load_plugin_registry,
    parse_plugin_registry,
    record_registry_entry_failure,
    remove_registry_entry,
    set_registry_entry_enabled,
    upsert_registry_entry,
)

pytestmark = pytest.mark.unit


def test_parse_plugin_registry_filters_invalid_entries() -> None:
    registry = parse_plugin_registry(
        {
            "schema_version": 1,
            "entries": [
                {"id": "ok.plugin", "version": "1.0.0", "install_path": "/tmp/plugin"},
                {"id": "", "version": "1.0.0", "install_path": "/tmp/invalid"},
                {"id": "missing.path", "version": "1.0.0"},
            ],
        }
    )

    assert len(registry.entries) == 1
    assert registry.entries[0].plugin_id == "ok.plugin"


def test_upsert_and_remove_registry_entry_round_trip(tmp_path: Path) -> None:
    state_root = str(tmp_path.resolve())
    entry = PluginRegistryEntry(
        plugin_id="acme.demo",
        version="1.0.0",
        install_path=str((tmp_path / "plugin").resolve()),
        enabled=True,
        installed_at="2026-03-06T00:00:00",
    )

    upsert_registry_entry(entry, state_root=state_root)
    loaded = load_plugin_registry(state_root)
    assert [(item.plugin_id, item.version) for item in loaded.entries] == [("acme.demo", "1.0.0")]

    remove_registry_entry("acme.demo", state_root=state_root)
    assert load_plugin_registry(state_root).entries == []


def test_set_registry_entry_enabled_clears_failure_data_when_reenabled(tmp_path: Path) -> None:
    state_root = str(tmp_path.resolve())
    entry = PluginRegistryEntry(
        plugin_id="acme.demo",
        version="1.0.0",
        install_path=str((tmp_path / "plugin").resolve()),
        enabled=True,
        installed_at="2026-03-06T00:00:00",
        last_error="boom",
        failure_count=3,
    )
    upsert_registry_entry(entry, state_root=state_root)

    set_registry_entry_enabled("acme.demo", "1.0.0", enabled=True, state_root=state_root)
    updated = load_plugin_registry(state_root).entries[0]

    assert updated.enabled is True
    assert updated.last_error is None
    assert updated.failure_count == 0


def test_record_and_clear_registry_failures(tmp_path: Path) -> None:
    state_root = str(tmp_path.resolve())
    entry = PluginRegistryEntry(
        plugin_id="acme.demo",
        version="1.0.0",
        install_path=str((tmp_path / "plugin").resolve()),
        enabled=True,
        installed_at="2026-03-06T00:00:00",
    )
    upsert_registry_entry(entry, state_root=state_root)

    record_registry_entry_failure(
        "acme.demo",
        "1.0.0",
        error_message="runtime failed",
        disable_after_failures=1,
        state_root=state_root,
    )
    failed = load_plugin_registry(state_root).entries[0]
    assert failed.enabled is False
    assert failed.failure_count == 1
    assert failed.last_error == "runtime failed"

    clear_registry_entry_failures("acme.demo", "1.0.0", state_root=state_root)
    recovered = load_plugin_registry(state_root).entries[0]
    assert recovered.failure_count == 0
    assert recovered.last_error is None
