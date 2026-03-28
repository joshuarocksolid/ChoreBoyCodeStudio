"""Unit tests for MainWindow run/debug command routing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.debug.debug_breakpoints import build_breakpoint
from app.debug.debug_models import DebugExceptionPolicy, DebugSourceMap
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def test_handle_run_action_routes_to_active_file_entry() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(file_path="/tmp/project/a.py", is_dirty=False, current_content="")
    )
    window_any._breakpoints_by_file = {}

    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_run_action(window)

    assert started is True
    assert len(calls) == 1
    assert calls[0]["mode"] == constants.RUN_MODE_PYTHON_SCRIPT
    assert calls[0]["entry_file"] == str(Path("/tmp/project/a.py").expanduser().resolve())
    assert calls[0]["breakpoints"] is None
    assert calls[0]["skip_save"] is False


def test_handle_debug_action_routes_to_active_file_and_collects_breakpoints() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(file_path="/tmp/project/debug.py", is_dirty=False, current_content="")
    )
    window_any._all_breakpoints = lambda: [
        build_breakpoint("/tmp/project/debug.py", 2),
        build_breakpoint("/tmp/project/debug.py", 9),
        build_breakpoint("/tmp/project/other.py", 1),
    ]
    window_any._debug_exception_policy = DebugExceptionPolicy()

    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_debug_action(window)

    assert started is True
    assert len(calls) == 1
    assert calls[0]["mode"] == constants.RUN_MODE_PYTHON_DEBUG
    assert calls[0]["entry_file"] == str(Path("/tmp/project/debug.py").expanduser().resolve())
    assert [
        (breakpoint.file_path, breakpoint.line_number)
        for breakpoint in cast(list[Any], calls[0]["breakpoints"])
    ] == [
        ("/tmp/project/debug.py", 2),
        ("/tmp/project/debug.py", 9),
        ("/tmp/project/other.py", 1),
    ]


def test_handle_run_project_action_uses_project_entry_resolution(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    (project_root / "app.py").write_text("print('run')\n", encoding="utf-8")
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text('{"schema_version": 1, "name": "T", "default_entry": "app.py"}', encoding="utf-8")
    loaded = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str(manifest_path.resolve()),
        metadata=ProjectMetadata(schema_version=1, name="T", default_entry="app.py"),
        entries=[],
    )
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded
    window_any._ensure_run_preflight_ready = lambda **_kwargs: True
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_run_project_action(window)

    assert started is True
    assert calls == [{"mode": constants.RUN_MODE_PYTHON_SCRIPT, "entry_file": "app.py"}]


def test_handle_run_project_action_stops_when_preflight_fails_without_modal_resolution(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text('{"schema_version": 1, "name": "T", "default_entry": "missing.py"}', encoding="utf-8")
    loaded = LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str(manifest_path.resolve()),
        metadata=ProjectMetadata(schema_version=1, name="T", default_entry="missing.py"),
        entries=[],
    )
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded
    window_any._ensure_run_preflight_ready = lambda **_kwargs: False
    window_any._resolve_project_entry_for_project_run = (
        lambda: (_ for _ in ()).throw(AssertionError("run path should not invoke modal entry resolution"))
    )
    window_any._start_session = lambda **_kwargs: (_ for _ in ()).throw(AssertionError("session should not start"))

    started = MainWindow._handle_run_project_action(window)

    assert started is False


def test_start_active_file_session_rejects_non_python_file(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(file_path="/tmp/project/readme.txt", is_dirty=False, current_content="")
    )
    window_any._breakpoints_by_file = {}
    window_any._start_session = lambda **_kwargs: True

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    started = MainWindow._start_active_file_session(window, mode=constants.RUN_MODE_PYTHON_SCRIPT)

    assert started is False
    assert warnings == [("Run unavailable", "Active file must be a Python file.")]


def test_handle_tree_run_file_routes_selected_python_entry() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_tree_run_file(window, "/tmp/project/folder/run.py")

    assert started is True
    assert calls == [
        {
            "mode": constants.RUN_MODE_PYTHON_SCRIPT,
            "entry_file": str(Path("/tmp/project/folder/run.py").expanduser().resolve()),
        }
    ]


def test_handle_tree_run_file_ignores_non_python_target() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._start_session = lambda **_kwargs: True

    started = MainWindow._handle_tree_run_file(window, "/tmp/project/readme.md")

    assert started is False


def test_start_active_file_session_uses_transient_file_for_dirty_buffer() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(
            file_path="/tmp/project/dirty.py",
            is_dirty=True,
            current_content="print('dirty')\n",
        )
    )
    window_any._breakpoints_by_file = {}
    window_any._active_transient_entry_file_path = None
    window_any._write_transient_entry_file = lambda **_kwargs: "/tmp/transient.py"
    deleted: list[str] = []
    window_any._delete_transient_entry_file = deleted.append
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._start_active_file_session(window, mode=constants.RUN_MODE_PYTHON_SCRIPT)

    assert started is True
    assert len(calls) == 1
    assert calls[0]["mode"] == constants.RUN_MODE_PYTHON_SCRIPT
    assert calls[0]["entry_file"] == "/tmp/transient.py"
    assert calls[0]["breakpoints"] is None
    assert calls[0]["debug_exception_policy"] is None
    assert calls[0]["source_maps"] == [
        DebugSourceMap(runtime_path="/tmp/transient.py", source_path="/tmp/project/dirty.py")
    ]
    assert calls[0]["skip_save"] is True
    assert deleted == []
    assert window_any._active_transient_entry_file_path == "/tmp/transient.py"


def test_start_active_file_session_cleans_transient_file_when_start_fails() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(
            file_path="/tmp/project/dirty.py",
            is_dirty=True,
            current_content="print('dirty')\n",
        )
    )
    window_any._breakpoints_by_file = {}
    window_any._active_transient_entry_file_path = None
    window_any._write_transient_entry_file = lambda **_kwargs: "/tmp/transient.py"
    deleted: list[str] = []
    window_any._delete_transient_entry_file = deleted.append
    window_any._start_session = lambda **_kwargs: False

    started = MainWindow._start_active_file_session(window, mode=constants.RUN_MODE_PYTHON_SCRIPT)

    assert started is False
    assert deleted == ["/tmp/transient.py"]
    assert window_any._active_transient_entry_file_path is None


def test_start_active_file_session_debug_remaps_active_file_breakpoints_to_transient_path() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._editor_manager = SimpleNamespace(
        active_tab=lambda: SimpleNamespace(
            file_path="/tmp/project/dirty.py",
            is_dirty=True,
            current_content="print('dirty')\n",
        )
    )
    window_any._all_breakpoints = lambda: [
        build_breakpoint("/tmp/project/dirty.py", 2),
        build_breakpoint("/tmp/project/dirty.py", 9),
        build_breakpoint("/tmp/project/other.py", 1),
    ]
    window_any._debug_exception_policy = DebugExceptionPolicy()
    window_any._active_transient_entry_file_path = None
    window_any._write_transient_entry_file = lambda **_kwargs: "/tmp/transient.py"
    deleted: list[str] = []
    window_any._delete_transient_entry_file = deleted.append
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._start_active_file_session(window, mode=constants.RUN_MODE_PYTHON_DEBUG)

    assert started is True
    assert len(calls) == 1
    assert calls[0]["mode"] == constants.RUN_MODE_PYTHON_DEBUG
    assert calls[0]["entry_file"] == "/tmp/transient.py"
    assert calls[0]["skip_save"] is True
    assert [
        (breakpoint.file_path, breakpoint.line_number)
        for breakpoint in cast(list[Any], calls[0]["breakpoints"])
    ] == [
        ("/tmp/transient.py", 2),
        ("/tmp/transient.py", 9),
        ("/tmp/project/other.py", 1),
    ]
    assert deleted == []
    assert window_any._active_transient_entry_file_path == "/tmp/transient.py"


def test_handle_rerun_last_debug_target_replays_test_node_debug() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    calls: list[str] = []
    window_any._last_debug_target = {"kind": "test_node", "node_id": "tests/test_demo.py::test_it"}
    window_any._handle_debug_test_node_action = lambda node_id: calls.append(node_id)

    MainWindow._handle_rerun_last_debug_target_action(window)

    assert calls == ["tests/test_demo.py::test_it"]
