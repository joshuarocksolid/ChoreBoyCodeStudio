"""Unit tests for project entrypoint management in MainWindow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectMetadata
from app.project.project_manifest import load_project_manifest
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def _loaded_project(tmp_path: Path, *, default_entry: str) -> LoadedProject:
    project_root = tmp_path / "project"
    project_root.mkdir()
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Entry Test",
                "default_entry": default_entry,
            }
        ),
        encoding="utf-8",
    )
    return LoadedProject(
        project_root=str(project_root),
        manifest_path=str(manifest_path),
        metadata=ProjectMetadata(schema_version=1, name="Entry Test", default_entry=default_entry),
        entries=[],
    )


def test_set_project_entry_point_persists_manifest_and_refreshes_tree(tmp_path: Path) -> None:
    loaded_project = _loaded_project(tmp_path, default_entry="main.py")
    script_path = Path(loaded_project.project_root) / "scripts" / "entry.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("print('entry')\n", encoding="utf-8")

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded_project
    refresh_calls: list[LoadedProject] = []
    window_any._populate_project_tree = lambda project: refresh_calls.append(project)

    updated = MainWindow._set_project_entry_point(window, "scripts/entry.py")

    assert updated is True
    assert window_any._loaded_project.metadata.default_entry == "scripts/entry.py"
    assert refresh_calls and refresh_calls[-1].metadata.default_entry == "scripts/entry.py"
    assert load_project_manifest(loaded_project.manifest_path).default_entry == "scripts/entry.py"


def test_resolve_project_entry_for_project_run_prompts_when_default_entry_missing(tmp_path: Path) -> None:
    loaded_project = _loaded_project(tmp_path, default_entry="missing.py")
    replacement_path = Path(loaded_project.project_root) / "app.py"
    replacement_path.write_text("print('ok')\n", encoding="utf-8")

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded_project
    window_any._prompt_for_project_entry_replacement = lambda _missing: "app.py"
    set_calls: list[str] = []
    window_any._set_project_entry_point = lambda relative_path: set_calls.append(relative_path) or True

    resolved = MainWindow._resolve_project_entry_for_project_run(window)

    assert resolved == "app.py"
    assert set_calls == ["app.py"]
