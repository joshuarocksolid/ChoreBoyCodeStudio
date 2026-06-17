"""Unit tests for project entrypoint management in MainWindow."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectMetadata
from app.project.project_manifest import build_synthetic_project_metadata, load_project_manifest
from app.shell.main_window import MainWindow
from app.shell.project_tree_ui_workflow import ProjectTreeUiWorkflow

pytestmark = pytest.mark.unit


class _EntryPointTreeHost:
    """Minimal :class:`ProjectTreeUiWorkflowHost`` for entry-point persistence tests."""

    def __init__(
        self,
        loaded_project: LoadedProject,
        *,
        refresh_calls: list[LoadedProject] | None = None,
    ) -> None:
        self._loaded_project = loaded_project
        self._refresh_calls = refresh_calls if refresh_calls is not None else []

    def parent_widget(self) -> object:
        return SimpleNamespace()

    def loaded_project(self) -> LoadedProject | None:
        return self._loaded_project

    def set_loaded_project(self, project: LoadedProject) -> None:
        self._loaded_project = project

    def project_tree_presenter(self) -> Any:
        host = self

        return SimpleNamespace(
            populate=lambda project, **_kwargs: host._refresh_calls.append(project),
        )


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


def test_set_project_entry_point_materializes_lazy_manifest(tmp_path: Path) -> None:
    project_root = tmp_path / "lazy_proj"
    project_root.mkdir()
    meta = build_synthetic_project_metadata(project_root, default_entry="main.py")
    manifest_path = project_root / "cbcs" / "project.json"
    script_path = project_root / "scripts" / "entry.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("print('entry')\n", encoding="utf-8")

    loaded_project = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str(manifest_path.resolve()),
        metadata=meta,
        entries=[],
        manifest_materialized=False,
    )

    host = _EntryPointTreeHost(loaded_project)
    workflow = ProjectTreeUiWorkflow(host)

    assert workflow.set_project_entry_point("scripts/entry.py") is True
    assert manifest_path.is_file()
    assert load_project_manifest(manifest_path).default_entry == "scripts/entry.py"
    assert host.loaded_project().manifest_materialized is True


def test_set_project_entry_point_persists_manifest_and_refreshes_tree(tmp_path: Path) -> None:
    loaded_project = _loaded_project(tmp_path, default_entry="main.py")
    script_path = Path(loaded_project.project_root) / "scripts" / "entry.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("print('entry')\n", encoding="utf-8")

    refresh_calls: list[LoadedProject] = []
    host = _EntryPointTreeHost(loaded_project, refresh_calls=refresh_calls)
    workflow = ProjectTreeUiWorkflow(host)

    updated = workflow.set_project_entry_point("scripts/entry.py")

    assert updated is True
    assert host.loaded_project().metadata.default_entry == "scripts/entry.py"
    assert refresh_calls and refresh_calls[-1].metadata.default_entry == "scripts/entry.py"
    assert load_project_manifest(loaded_project.manifest_path).default_entry == "scripts/entry.py"


def test_resolve_project_entry_for_project_run_prompts_when_default_entry_missing(tmp_path: Path) -> None:
    loaded_project = _loaded_project(tmp_path, default_entry="missing.py")
    replacement_path = Path(loaded_project.project_root) / "app.py"
    replacement_path.write_text("print('ok')\n", encoding="utf-8")

    set_calls: list[str] = []
    window = SimpleNamespace(
        _loaded_project=loaded_project,
        _prompt_for_project_entry_replacement=lambda _missing: "app.py",
        _project_tree_ui_workflow=SimpleNamespace(
            set_project_entry_point=lambda relative_path: set_calls.append(relative_path) or True
        ),
    )

    resolved = MainWindow._resolve_project_entry_for_project_run(window)  # type: ignore[arg-type]

    assert resolved == "app.py"
    assert set_calls == ["app.py"]


def test_resolve_project_entry_for_project_run_returns_default_when_entry_exists(tmp_path: Path) -> None:
    loaded_project = _loaded_project(tmp_path, default_entry="main.py")
    entry_path = Path(loaded_project.project_root) / "main.py"
    entry_path.write_text("print('ok')\n", encoding="utf-8")

    window = SimpleNamespace(_loaded_project=loaded_project)

    resolved = MainWindow._resolve_project_entry_for_project_run(window)  # type: ignore[arg-type]

    assert resolved == "main.py"
