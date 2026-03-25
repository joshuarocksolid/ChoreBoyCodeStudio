"""Unit tests for project dependency manifest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
    DEPENDENCY_MANIFEST_SCHEMA_VERSION,
    DependencyEntry,
    DependencyManifest,
    SOURCE_FOLDER,
    SOURCE_WHEEL,
    STATUS_ACTIVE,
    STATUS_REMOVED,
    dependency_manifest_path,
    load_dependency_manifest,
    save_dependency_manifest,
)

pytestmark = pytest.mark.unit


def _make_entry(name: str = "requests", **kwargs) -> DependencyEntry:
    defaults = {
        "version": "2.31.0",
        "source": SOURCE_WHEEL,
        "classification": CLASSIFICATION_PURE_PYTHON,
        "status": STATUS_ACTIVE,
        "added_at": "2026-03-25T12:00:00+00:00",
        "vendor_path": f"vendor/{name}",
    }
    defaults.update(kwargs)
    return DependencyEntry(name=name, **defaults)


def test_dependency_entry_round_trip() -> None:
    entry = _make_entry()
    data = entry.to_dict()
    restored = DependencyEntry.from_dict(data)
    assert restored.name == "requests"
    assert restored.version == "2.31.0"
    assert restored.classification == CLASSIFICATION_PURE_PYTHON
    assert restored.status == STATUS_ACTIVE


def test_manifest_add_entry_deduplicates_by_name() -> None:
    manifest = DependencyManifest()
    manifest.add_entry(_make_entry("requests", version="2.30.0"))
    manifest.add_entry(_make_entry("requests", version="2.31.0"))
    assert len(manifest.entries) == 1
    assert manifest.entries[0].version == "2.31.0"


def test_manifest_remove_entry_marks_status_as_removed() -> None:
    manifest = DependencyManifest()
    manifest.add_entry(_make_entry("requests"))
    result = manifest.remove_entry("requests")
    assert result is True
    assert manifest.entries[0].status == STATUS_REMOVED
    assert len(manifest.active_entries()) == 0
    assert len(manifest.removed_entries()) == 1


def test_manifest_remove_nonexistent_returns_false() -> None:
    manifest = DependencyManifest()
    assert manifest.remove_entry("nonexistent") is False


def test_manifest_find_by_name() -> None:
    manifest = DependencyManifest()
    manifest.add_entry(_make_entry("requests"))
    manifest.add_entry(_make_entry("flask"))
    assert manifest.find_by_name("flask") is not None
    assert manifest.find_by_name("flask").version == "2.31.0"
    assert manifest.find_by_name("missing") is None


def test_manifest_to_dict_round_trip() -> None:
    manifest = DependencyManifest()
    manifest.add_entry(_make_entry("requests"))
    manifest.add_entry(_make_entry("flask", classification=CLASSIFICATION_NATIVE_EXTENSION))
    data = manifest.to_dict()
    restored = DependencyManifest.from_dict(data)
    assert len(restored.entries) == 2
    assert restored.schema_version == DEPENDENCY_MANIFEST_SCHEMA_VERSION


def test_save_and_load_manifest_round_trip(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "cbcs").mkdir()

    manifest = DependencyManifest()
    manifest.add_entry(_make_entry("requests"))
    manifest.add_entry(_make_entry("numpy", classification=CLASSIFICATION_NATIVE_EXTENSION))

    saved_path = save_dependency_manifest(str(project_root), manifest)
    assert saved_path.exists()

    loaded = load_dependency_manifest(str(project_root))
    assert len(loaded.entries) == 2
    assert loaded.find_by_name("requests").classification == CLASSIFICATION_PURE_PYTHON
    assert loaded.find_by_name("numpy").classification == CLASSIFICATION_NATIVE_EXTENSION


def test_load_manifest_returns_empty_when_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    loaded = load_dependency_manifest(str(project_root))
    assert len(loaded.entries) == 0


def test_load_manifest_returns_empty_for_invalid_json(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)
    manifest_path = project_root / "cbcs" / "dependencies.json"
    manifest_path.write_text("{invalid json", encoding="utf-8")
    loaded = load_dependency_manifest(str(project_root))
    assert len(loaded.entries) == 0


def test_manifest_path_is_under_cbcs(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    path = dependency_manifest_path(str(project_root))
    assert "cbcs" in path.parts
    assert path.name == "dependencies.json"


def test_add_entry_sets_added_at_timestamp() -> None:
    manifest = DependencyManifest()
    entry = DependencyEntry(
        name="test_pkg",
        version="1.0",
        source=SOURCE_FOLDER,
        classification=CLASSIFICATION_PURE_PYTHON,
    )
    manifest.add_entry(entry)
    assert manifest.entries[0].added_at  # non-empty timestamp
