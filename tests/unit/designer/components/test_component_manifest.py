"""Unit tests for component manifest persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.designer.components import ComponentManifestEntry, load_component_manifest, save_component_manifest

pytestmark = pytest.mark.unit


def test_save_and_load_component_manifest_round_trip(tmp_path: Path) -> None:
    entries = {
        "ButtonPart": ComponentManifestEntry(
            name="ButtonPart",
            file_name="ButtonPart.ui",
            root_class_name="QPushButton",
            root_object_name="pushButton",
        )
    }
    save_component_manifest(tmp_path, entries)
    loaded = load_component_manifest(tmp_path)
    assert loaded == entries
