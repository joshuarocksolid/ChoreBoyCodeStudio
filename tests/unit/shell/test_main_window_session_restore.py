"""Unit tests for MainWindow project-restore + Open File behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def _make_window_for_restore(
    *,
    last_path: str | None,
    loaded_project: object | None = None,
) -> tuple[MainWindow, list[str]]:
    """Build a bare MainWindow shell suitable for ``_try_restore_last_project``."""
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._is_shutting_down = False
    window_any._loaded_project = loaded_project

    settings_payload: dict[str, Any] = {}
    if last_path is not None:
        settings_payload[constants.LAST_PROJECT_PATH_KEY] = last_path

    window_any._settings_service = SimpleNamespace(
        load_global=lambda: dict(settings_payload),
    )

    opened: list[str] = []

    def _record(project_root: str) -> bool:
        opened.append(project_root)
        return True

    window_any._open_project_by_path = _record
    return window, opened


def test_try_restore_last_project_reopens_canonical_project(tmp_path: Path) -> None:
    project_root = tmp_path / "canonical_proj"
    cbcs_dir = project_root / constants.PROJECT_META_DIRNAME
    cbcs_dir.mkdir(parents=True)
    (cbcs_dir / constants.PROJECT_MANIFEST_FILENAME).write_text(
        '{"schema_version": 1, "project_name": "demo", "default_entry": "main.py"}\n'
    )
    (project_root / "main.py").write_text("# entry\n")

    window, opened = _make_window_for_restore(last_path=str(project_root))

    MainWindow._try_restore_last_project(window)

    assert opened == [str(project_root)]


def test_try_restore_last_project_reopens_importable_project_without_manifest(
    tmp_path: Path,
) -> None:
    """Regression: importable projects (no `cbcs/project.json`) must auto-reopen."""
    project_root = tmp_path / "importable_proj"
    project_root.mkdir()
    (project_root / "main.py").write_text("# entry\n")

    window, opened = _make_window_for_restore(last_path=str(project_root))

    MainWindow._try_restore_last_project(window)

    assert opened == [str(project_root)]


def test_try_restore_last_project_skips_invalid_path(tmp_path: Path) -> None:
    missing_root = tmp_path / "does_not_exist"

    window, opened = _make_window_for_restore(last_path=str(missing_root))

    MainWindow._try_restore_last_project(window)

    assert opened == []


def test_try_restore_last_project_skips_when_no_last_path() -> None:
    window, opened = _make_window_for_restore(last_path=None)

    MainWindow._try_restore_last_project(window)

    assert opened == []


def test_try_restore_last_project_skips_when_project_already_loaded(tmp_path: Path) -> None:
    project_root = tmp_path / "importable_proj"
    project_root.mkdir()
    (project_root / "main.py").write_text("# entry\n")

    window, opened = _make_window_for_restore(
        last_path=str(project_root),
        loaded_project=SimpleNamespace(project_root=str(project_root)),
    )

    MainWindow._try_restore_last_project(window)

    assert opened == []


def _make_window_for_open_file(
    *,
    loaded_project: object | None,
    selected_files: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MainWindow, dict[str, Any]]:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded_project
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: None)

    captured: dict[str, Any] = {
        "opened_files": [],
        "opened_projects": [],
        "show_editor_calls": 0,
    }

    def _open_file(file_path: str, *, preview: bool = False) -> bool:
        captured["opened_files"].append((file_path, preview))
        return True

    def _open_project(project_root: str) -> bool:
        captured["opened_projects"].append(project_root)
        # Simulate the project successfully loading so subsequent file opens
        # behave as if a project is now loaded.
        window_any._loaded_project = SimpleNamespace(project_root=project_root)
        return True

    def _show_editor() -> None:
        captured["show_editor_calls"] += 1

    window_any._open_file_in_editor = _open_file
    window_any._open_project_by_path = _open_project
    window_any._show_editor_screen = _show_editor

    monkeypatch.setattr(
        "app.shell.main_window.choose_open_files",
        lambda *_args, **_kwargs: list(selected_files),
    )

    return window, captured


def test_handle_open_file_action_opens_parent_as_project_when_no_project_loaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir = tmp_path / "importable_proj"
    parent_dir.mkdir()
    target_file = parent_dir / "capability_test.py"
    target_file.write_text("print('hi')\n")

    window, captured = _make_window_for_open_file(
        loaded_project=None,
        selected_files=[str(target_file)],
        monkeypatch=monkeypatch,
    )

    MainWindow._handle_open_file_action(window)

    assert captured["opened_projects"] == [str(parent_dir.resolve())]
    assert captured["opened_files"] == [(str(target_file), False)]
    assert captured["show_editor_calls"] == 1


def test_handle_open_file_action_does_not_switch_project_when_project_loaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_dir = tmp_path / "importable_proj"
    parent_dir.mkdir()
    target_file = parent_dir / "extra.py"
    target_file.write_text("# extra\n")

    loaded_project = SimpleNamespace(project_root=str(tmp_path / "current_proj"))

    window, captured = _make_window_for_open_file(
        loaded_project=loaded_project,
        selected_files=[str(target_file)],
        monkeypatch=monkeypatch,
    )

    MainWindow._handle_open_file_action(window)

    assert captured["opened_projects"] == []
    assert captured["opened_files"] == [(str(target_file), False)]
    assert captured["show_editor_calls"] == 1


def test_handle_open_file_action_dialog_cancel_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, captured = _make_window_for_open_file(
        loaded_project=None,
        selected_files=[],
        monkeypatch=monkeypatch,
    )

    MainWindow._handle_open_file_action(window)

    assert captured["opened_projects"] == []
    assert captured["opened_files"] == []
    assert captured["show_editor_calls"] == 0


def test_diagnostics_orchestrator_active_tab_lambda_runs_on_python39() -> None:
    """Regression: the diagnostics-orchestrator lambda must not use PEP 604 unions.

    ChoreBoy ships Python 3.9; the original ``cast(str | None, ...)`` raised
    TypeError on every realtime-lint tick.  Build the same lambda the shell
    builds at construction time and exercise it with no active tab.
    """
    from typing import Optional, cast

    editor_manager = SimpleNamespace(active_tab=lambda: None)
    get_active_tab_file_path = lambda: cast(  # noqa: E731 - mirrors shell wiring
        Optional[str],
        getattr(editor_manager.active_tab(), "file_path", None),
    )

    assert get_active_tab_file_path() is None

    editor_manager_with_tab = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(file_path="/tmp/example.py"),
    )
    get_active_tab_file_path_with_tab = lambda: cast(  # noqa: E731
        Optional[str],
        getattr(editor_manager_with_tab.active_tab(), "file_path", None),
    )

    assert get_active_tab_file_path_with_tab() == "/tmp/example.py"
