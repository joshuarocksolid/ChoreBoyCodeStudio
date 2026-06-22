"""Unit tests for Run With Arguments / Run Configurations workflow plumbing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.shell.run_config_controller import RunConfigController
from app.shell.run_launch_workflow import RunLaunchWorkflow
from app.shell.run_with_arguments_dialog import (
    RunInvocation,
    RunWithArgumentsOutcomeKind,
    RunWithArgumentsResult,
)

pytestmark = pytest.mark.unit


def _loaded_project_with_configs(
    tmp_path: Path,
    *,
    default_entry: str = "app.py",
    default_argv: list[str] | None = None,
    run_configs: list[dict[str, Any]] | None = None,
) -> LoadedProject:
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True, exist_ok=True)
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        '{"schema_version": 1, "name": "T", "default_entry": "%s"}' % default_entry,
        encoding="utf-8",
    )
    return LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str(manifest_path.resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="T",
            default_entry=default_entry,
            default_argv=list(default_argv or []),
            run_configs=list(run_configs or []),
        ),
        entries=[],
    )


def _build_run_launch_workflow(
    loaded_project: LoadedProject,
    *,
    active_named_run_config_name: str | None = None,
) -> tuple[RunLaunchWorkflow, Any]:
    run_config_controller = RunConfigController()
    host = SimpleNamespace(
        dialog_parent=lambda: SimpleNamespace(),
        loaded_project=lambda: loaded_project,
        set_loaded_project=lambda project: setattr(host, "loaded_project", lambda: project),
        active_named_run_config_name=lambda: active_named_run_config_name,
        set_active_named_run_config_name=lambda name: setattr(host, "active_named_run_config_name", name),
        editor_manager=lambda: SimpleNamespace(active_tab=lambda: None),
        debug_control_workflow=lambda: SimpleNamespace(build_debug_breakpoints_for_launch=lambda **_kwargs: []),
        debug_exception_policy=lambda: SimpleNamespace(),
        run_config_controller=lambda: run_config_controller,
        run_debug_presenter=lambda: SimpleNamespace(start_session=lambda **_kwargs: True),
        settings_service=lambda: SimpleNamespace(
            load_recent_argv_history=lambda: [],
            push_recent_argv_history=lambda _text: None,
        ),
        resolve_theme_tokens=lambda: None,
        show_run_preflight_result=lambda *_args, **_kwargs: None,
        refresh_run_action_states=lambda: None,
        editor_tab_factory=lambda: SimpleNamespace(open_file_in_editor=lambda *_a, **_k: True),
        editor_tabs_widget=lambda: None,
        tab_index_for_path=lambda _path: -1,
        test_runner_workflow=lambda: SimpleNamespace(),
        active_transient_entry_file_path=lambda: None,
        set_active_transient_entry_file_path=lambda path: setattr(host, "active_transient_entry_file_path", lambda: path),
        status_bar=SimpleNamespace(addPermanentWidget=lambda *_args: None),
        show_warning=lambda *_args, **_kwargs: None,
        show_information=lambda *_args, **_kwargs: None,
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )
    return RunLaunchWorkflow(cast(Any, host)), host


def test_launch_ad_hoc_run_invocation_forwards_argv_env_and_wd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = _loaded_project_with_configs(tmp_path, default_entry="main.py")
    workflow, _host = _build_run_launch_workflow(loaded)
    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_arguments.ensure_run_preflight_ready",
        lambda *_args, **_kwargs: True,
    )
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    invocation = RunInvocation(
        entry_file="/tmp/proj/run.py",
        argv=["--config", "/tmp/with space/cfg.toml", "--verbose"],
        argv_text='--config "/tmp/with space/cfg.toml" --verbose',
        working_directory="/tmp/proj",
        env_overrides={"DEBUG": "1"},
        save_request=False,
    )

    result = workflow.launch_ad_hoc_run_invocation(invocation)

    assert result is True
    assert calls == [
        {
            "mode": constants.RUN_MODE_PYTHON_SCRIPT,
            "entry_file": "/tmp/proj/run.py",
            "argv": ["--config", "/tmp/with space/cfg.toml", "--verbose"],
            "working_directory": "/tmp/proj",
            "env_overrides": {"DEBUG": "1"},
        }
    ]


def test_launch_ad_hoc_run_invocation_skips_when_preflight_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = _loaded_project_with_configs(tmp_path)
    workflow, _host = _build_run_launch_workflow(loaded)
    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_arguments.ensure_run_preflight_ready",
        lambda *_args, **_kwargs: False,
    )
    workflow.start_session = lambda **_kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("session should not start when preflight refuses")
    )

    invocation = RunInvocation(
        entry_file="/tmp/proj/missing.py",
        argv=[],
        argv_text="",
        working_directory=None,
        env_overrides={},
        save_request=False,
    )

    assert workflow.launch_ad_hoc_run_invocation(invocation) is False


def test_handle_run_project_action_uses_active_named_run_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_payload = {
        "name": "Debug",
        "entry_file": "debug.py",
        "argv": ["--profile=dev"],
        "working_directory": ".",
        "env_overrides": {"X": "1"},
    }
    loaded = _loaded_project_with_configs(
        tmp_path,
        default_entry="app.py",
        default_argv=["--default"],
        run_configs=[config_payload],
    )
    workflow, _host = _build_run_launch_workflow(loaded, active_named_run_config_name="Debug")
    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_actions.ensure_run_preflight_ready",
        lambda *_args, **_kwargs: True,
    )
    workflow.refresh_active_run_config_indicator = lambda: None  # type: ignore[method-assign]
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow.handle_run_project_action()

    assert started is True
    assert calls == [
        {
            "mode": constants.RUN_MODE_PYTHON_SCRIPT,
            "entry_file": "debug.py",
            "argv": ["--profile=dev"],
            "working_directory": ".",
            "env_overrides": {"X": "1"},
            "breakpoints": None,
            "debug_exception_policy": None,
        }
    ]


def test_handle_run_project_action_falls_back_to_default_argv_when_no_active_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = _loaded_project_with_configs(
        tmp_path,
        default_entry="app.py",
        default_argv=["--from-default-argv"],
    )
    workflow, _host = _build_run_launch_workflow(loaded, active_named_run_config_name=None)
    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_actions.ensure_run_preflight_ready",
        lambda *_args, **_kwargs: True,
    )
    calls: list[dict[str, object]] = []
    workflow.start_session = lambda **kwargs: calls.append(kwargs) or True  # type: ignore[method-assign]

    started = workflow.handle_run_project_action()

    assert started is True
    assert calls == [{"mode": constants.RUN_MODE_PYTHON_SCRIPT, "entry_file": "app.py"}]


def test_handle_run_with_arguments_action_persists_argv_text_in_recent_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.persistence.settings_service import SettingsService

    loaded = _loaded_project_with_configs(tmp_path)
    workflow, host = _build_run_launch_workflow(loaded)
    settings_service = SettingsService(state_root=tmp_path / "state")
    host.settings_service = lambda: settings_service
    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_arguments.ensure_run_preflight_ready",
        lambda *_args, **_kwargs: True,
    )
    workflow.start_session = lambda **_kwargs: True  # type: ignore[method-assign]

    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_arguments.RunWithArgumentsDialog.run_dialog",
        lambda *_args, **_kwargs: RunWithArgumentsResult(
            outcome=RunWithArgumentsOutcomeKind.RUN,
            invocation=RunInvocation(
                entry_file="app.py",
                argv=["--alpha"],
                argv_text="--alpha",
                working_directory=None,
                env_overrides={},
                save_request=False,
            ),
        ),
    )

    result = workflow.handle_run_with_arguments_action()

    assert result is True
    assert host.settings_service().load_recent_argv_history() == ["--alpha"]


def test_handle_run_with_arguments_action_cancelled_dialog_does_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.persistence.settings_service import SettingsService

    loaded = _loaded_project_with_configs(tmp_path)
    workflow, host = _build_run_launch_workflow(loaded)
    settings_service = SettingsService(state_root=tmp_path / "state")
    host.settings_service = lambda: settings_service
    workflow.start_session = lambda **_kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("session must not start when the dialog is cancelled")
    )

    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_arguments.RunWithArgumentsDialog.run_dialog",
        lambda *_args, **_kwargs: RunWithArgumentsResult(),
    )

    assert workflow.handle_run_with_arguments_action() is False
    assert host.settings_service().load_recent_argv_history() == []


def test_manage_configurations_click_sets_outcome_only() -> None:
    from PySide2.QtWidgets import QApplication

    from app.shell.run_with_arguments_dialog import RunWithArgumentsDialog, RunWithArgumentsInitial

    app = QApplication.instance() or QApplication([])
    _ = app

    dialog = RunWithArgumentsDialog(RunWithArgumentsInitial())
    dialog._on_manage_configurations_clicked()

    assert dialog._outcome == RunWithArgumentsOutcomeKind.OPEN_CONFIGURATIONS


def test_handle_run_with_arguments_action_open_configurations_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = _loaded_project_with_configs(tmp_path)
    workflow, _host = _build_run_launch_workflow(loaded)
    calls: list[str] = []

    monkeypatch.setattr(
        "app.shell.run_launch.run_launch_arguments.RunWithArgumentsDialog.run_dialog",
        lambda *_args, **_kwargs: RunWithArgumentsResult(
            outcome=RunWithArgumentsOutcomeKind.OPEN_CONFIGURATIONS,
        ),
    )
    workflow.handle_run_with_configuration_action = lambda: calls.append("configs") or True  # type: ignore[method-assign]
    workflow.start_session = lambda **_kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("session must not start when opening configurations")
    )

    assert workflow.handle_run_with_arguments_action() is True
    assert calls == ["configs"]
