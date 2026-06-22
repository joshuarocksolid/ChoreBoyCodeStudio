"""Unit tests for shell run/debug command routing."""

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
from app.shell.run_launch_workflow import RunLaunchWorkflow

pytestmark = pytest.mark.unit


def _build_run_launch_workflow(**overrides: Any) -> tuple[RunLaunchWorkflow, Any]:
    loaded_project = overrides.get("loaded_project")
    active_config_name: list[str | None] = [overrides.get("active_named_run_config_name")]
    transient_path: list[str | None] = [overrides.get("active_transient_entry_file_path")]
    editor_manager = overrides.get(
        "editor_manager",
        lambda: SimpleNamespace(active_tab=lambda: None),
    )
    from app.shell.breakpoint_store import BreakpointStore

    debug_control_workflow = overrides.get(
        "debug_control_workflow",
        SimpleNamespace(
            breakpoint_store=BreakpointStore(),
            build_debug_breakpoints_for_launch=lambda **_kwargs: [],
        ),
    )
    host = SimpleNamespace(
        dialog_parent=SimpleNamespace(),
        loaded_project=lambda: loaded_project,
        set_loaded_project=lambda project: setattr(host, "_loaded_project_value", project) or setattr(
            host, "loaded_project", lambda: project
        ),
        active_named_run_config_name=lambda: active_config_name[0],
        set_active_named_run_config_name=lambda name: active_config_name.__setitem__(0, name),
        editor_manager=editor_manager,
        debug_control_workflow=lambda: debug_control_workflow,
        debug_exception_policy=lambda: overrides.get("debug_exception_policy", DebugExceptionPolicy()),
        run_config_controller=lambda: overrides.get("run_config_controller"),
        run_debug_presenter=lambda: SimpleNamespace(start_session=lambda **_kwargs: True),
        settings_service=lambda: SimpleNamespace(
            load_recent_argv_history=lambda: [],
            push_recent_argv_history=lambda _text: None,
        ),
        resolve_theme_tokens=lambda: None,
        show_run_preflight_result=lambda *_args, **_kwargs: None,
        refresh_run_action_states=lambda: None,
        editor_tab_factory=lambda: overrides.get(
            "editor_tab_factory", SimpleNamespace(open_file_in_editor=lambda *_a, **_k: True)
        ),
        editor_tabs_widget=lambda: overrides.get("editor_tabs_widget"),
        tab_index_for_path=lambda _path: -1,
        test_runner_workflow=lambda: overrides.get("test_runner_workflow", SimpleNamespace()),
        active_transient_entry_file_path=lambda: transient_path[0],
        set_active_transient_entry_file_path=lambda path: transient_path.__setitem__(0, path),
        status_bar=SimpleNamespace(addPermanentWidget=lambda *_args: None),
        show_warning=lambda *_args, **_kwargs: None,
        show_information=lambda *_args, **_kwargs: None,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )
    workflow = RunLaunchWorkflow(cast(Any, host))
    return workflow, host


def test_handle_run_action_routes_to_active_file_entry() -> None:
    workflow, _host = _build_run_launch_workflow(
        editor_manager=lambda: SimpleNamespace(
            active_tab=lambda: SimpleNamespace(file_path="/tmp/project/a.py", is_dirty=False, current_content="")
        ),
    )
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow.handle_run_action()

    assert started is True
    assert len(calls) == 1
    assert calls[0]["mode"] == constants.RUN_MODE_PYTHON_SCRIPT
    assert calls[0]["entry_file"] == str(Path("/tmp/project/a.py").expanduser().resolve())
    assert calls[0]["breakpoints"] is None
    assert calls[0]["skip_save"] is False


def test_handle_debug_action_routes_to_active_file_and_collects_breakpoints() -> None:
    breakpoints = [
        build_breakpoint("/tmp/project/debug.py", 2),
        build_breakpoint("/tmp/project/debug.py", 9),
        build_breakpoint("/tmp/project/other.py", 1),
    ]
    workflow, _host = _build_run_launch_workflow(
        editor_manager=lambda: SimpleNamespace(
            active_tab=lambda: SimpleNamespace(file_path="/tmp/project/debug.py", is_dirty=False, current_content="")
        ),
        debug_control_workflow=SimpleNamespace(
            build_debug_breakpoints_for_launch=lambda **_kwargs: breakpoints,
        ),
    )
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow.handle_debug_action()

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


def test_handle_run_project_action_uses_project_entry_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    workflow, _host = _build_run_launch_workflow(
        loaded_project=loaded,
        active_named_run_config_name=None,
    )
    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_actions.ensure_run_preflight_ready",
        lambda *_args, **_kwargs: True,
    )
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow.handle_run_project_action()

    assert started is True
    assert calls == [{"mode": constants.RUN_MODE_PYTHON_SCRIPT, "entry_file": "app.py"}]


def test_handle_run_project_action_stops_when_preflight_fails_without_modal_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    workflow, _host = _build_run_launch_workflow(
        loaded_project=loaded,
        active_named_run_config_name=None,
    )
    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_actions.ensure_run_preflight_ready",
        lambda *_args, **_kwargs: False,
    )
    workflow.start_session = lambda **_kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("session should not start")
    )

    started = workflow.handle_run_project_action()

    assert started is False


def test_start_active_file_session_rejects_non_python_file(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, host = _build_run_launch_workflow(
        editor_manager=lambda: SimpleNamespace(
            active_tab=lambda: SimpleNamespace(file_path="/tmp/project/readme.txt", is_dirty=False, current_content="")
        ),
    )
    workflow.start_session = lambda **_kwargs: True  # type: ignore[method-assign]

    warnings: list[tuple[str, str]] = []
    host.show_warning = lambda title, message: warnings.append((title, message))

    started = workflow._start_active_file_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)

    assert started is False
    assert warnings == [("Run unavailable", "Active file must be a Python file.")]


def test_handle_tree_run_file_routes_selected_python_entry() -> None:
    workflow, _host = _build_run_launch_workflow()
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow.handle_tree_run_file("/tmp/project/folder/run.py")

    assert started is True
    assert calls == [
        {
            "mode": constants.RUN_MODE_PYTHON_SCRIPT,
            "entry_file": str(Path("/tmp/project/folder/run.py").expanduser().resolve()),
        }
    ]


def test_handle_tree_run_file_ignores_non_python_target() -> None:
    workflow, _host = _build_run_launch_workflow()
    workflow.start_session = lambda **_kwargs: True  # type: ignore[method-assign]

    started = workflow.handle_tree_run_file("/tmp/project/readme.md")

    assert started is False


def test_start_active_file_session_uses_transient_file_for_dirty_buffer() -> None:
    workflow, host = _build_run_launch_workflow(
        editor_manager=lambda: SimpleNamespace(
            active_tab=lambda: SimpleNamespace(
                file_path="/tmp/project/dirty.py",
                is_dirty=True,
                current_content="print('dirty')\n",
            )
        ),
        active_transient_entry_file_path=None,
    )
    workflow._active_file_launch.write_transient_entry_file = lambda **_kwargs: "/tmp/transient.py"  # type: ignore[method-assign]
    deleted: list[str] = []
    workflow._active_file_launch.delete_transient_entry_file = deleted.append  # type: ignore[method-assign]
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow._start_active_file_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)

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
    assert host.active_transient_entry_file_path() == "/tmp/transient.py"


def test_start_active_file_session_cleans_transient_file_when_start_fails() -> None:
    workflow, host = _build_run_launch_workflow(
        editor_manager=lambda: SimpleNamespace(
            active_tab=lambda: SimpleNamespace(
                file_path="/tmp/project/dirty.py",
                is_dirty=True,
                current_content="print('dirty')\n",
            )
        ),
        active_transient_entry_file_path=None,
    )
    workflow._active_file_launch.write_transient_entry_file = lambda **_kwargs: "/tmp/transient.py"  # type: ignore[method-assign]
    deleted: list[str] = []
    workflow._active_file_launch.delete_transient_entry_file = deleted.append  # type: ignore[method-assign]
    workflow.start_session = lambda **_kwargs: False  # type: ignore[method-assign]

    started = workflow._start_active_file_session(mode=constants.RUN_MODE_PYTHON_SCRIPT)

    assert started is False
    assert deleted == ["/tmp/transient.py"]
    assert host.active_transient_entry_file_path() is None


def test_start_active_file_session_debug_remaps_active_file_breakpoints_to_transient_path() -> None:
    breakpoints = [
        build_breakpoint("/tmp/project/dirty.py", 2),
        build_breakpoint("/tmp/project/dirty.py", 9),
        build_breakpoint("/tmp/project/other.py", 1),
    ]
    workflow, host = _build_run_launch_workflow(
        editor_manager=lambda: SimpleNamespace(
            active_tab=lambda: SimpleNamespace(
                file_path="/tmp/project/dirty.py",
                is_dirty=True,
                current_content="print('dirty')\n",
            )
        ),
        debug_control_workflow=SimpleNamespace(
            build_debug_breakpoints_for_launch=lambda **_kwargs: [
                build_breakpoint(
                    "/tmp/transient.py" if bp.file_path == "/tmp/project/dirty.py" else bp.file_path,
                    bp.line_number,
                )
                for bp in breakpoints
            ],
        ),
        active_transient_entry_file_path=None,
    )
    workflow._active_file_launch.write_transient_entry_file = lambda **_kwargs: "/tmp/transient.py"  # type: ignore[method-assign]
    deleted: list[str] = []
    workflow._active_file_launch.delete_transient_entry_file = deleted.append  # type: ignore[method-assign]
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow._start_active_file_session(mode=constants.RUN_MODE_PYTHON_DEBUG)

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
    assert host.active_transient_entry_file_path() == "/tmp/transient.py"


def test_handle_rerun_last_debug_target_replays_test_node_debug() -> None:
    calls: list[str] = []
    workflow, host = _build_run_launch_workflow()
    host.test_runner_workflow = lambda: SimpleNamespace(debug_test_node=lambda node_id: calls.append(node_id))
    workflow.record_debug_target_from_dict({"kind": "test_node", "node_id": "tests/test_demo.py::test_it"})

    workflow.handle_rerun_last_debug_target_action()

    assert calls == ["tests/test_demo.py::test_it"]
