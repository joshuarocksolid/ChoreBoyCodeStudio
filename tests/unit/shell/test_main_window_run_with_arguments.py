"""Unit tests for the Run With Arguments / Run Configurations main-window plumbing.

These tests target the wiring: which kwargs are forwarded into ``_start_session``, which
configuration is resolved when F5 fires, and that recent argv strings reach the global
settings store. UI rendering of the dialog itself is covered by manual acceptance tests
(``docs/ACCEPTANCE_TESTS.md``); we deliberately do not poke field widgets here.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.project.run_configs import RunConfiguration
from app.shell.main_window import MainWindow
from app.shell.run_config_controller import RunConfigController
from app.shell.run_with_arguments_dialog import RunInvocation

pytestmark = pytest.mark.unit


def _build_window_with_project(loaded_project: LoadedProject) -> Any:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._loaded_project = loaded_project
    window_any._active_named_run_config_name = None
    window_any._run_config_controller = RunConfigController()
    return window_any


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


def test_launch_ad_hoc_run_invocation_forwards_argv_env_and_wd(tmp_path: Path) -> None:
    loaded = _loaded_project_with_configs(tmp_path, default_entry="main.py")
    window_any = _build_window_with_project(loaded)
    window_any._ensure_run_preflight_ready = lambda **_kwargs: True
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    invocation = RunInvocation(
        entry_file="/tmp/proj/run.py",
        argv=["--config", "/tmp/with space/cfg.toml", "--verbose"],
        argv_text='--config "/tmp/with space/cfg.toml" --verbose',
        working_directory="/tmp/proj",
        env_overrides={"DEBUG": "1"},
        save_request=False,
    )

    result = MainWindow._launch_ad_hoc_run_invocation(window_any, invocation)

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


def test_launch_ad_hoc_run_invocation_skips_when_preflight_blocks(tmp_path: Path) -> None:
    loaded = _loaded_project_with_configs(tmp_path)
    window_any = _build_window_with_project(loaded)
    window_any._ensure_run_preflight_ready = lambda **_kwargs: False
    window_any._start_session = lambda **_kwargs: (_ for _ in ()).throw(
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

    assert MainWindow._launch_ad_hoc_run_invocation(window_any, invocation) is False


def test_handle_run_project_action_uses_active_named_run_configuration(tmp_path: Path) -> None:
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
    window_any = _build_window_with_project(loaded)
    window_any._active_named_run_config_name = "Debug"
    window_any._ensure_run_preflight_ready = lambda **_kwargs: True
    window_any._refresh_active_run_config_indicator = lambda: None
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_run_project_action(window_any)

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


def test_handle_run_project_action_falls_back_to_default_argv_when_no_active_config(tmp_path: Path) -> None:
    loaded = _loaded_project_with_configs(
        tmp_path,
        default_entry="app.py",
        default_argv=["--from-default-argv"],
    )
    window_any = _build_window_with_project(loaded)
    window_any._active_named_run_config_name = None
    window_any._ensure_run_preflight_ready = lambda **_kwargs: True
    calls: list[dict[str, object]] = []
    window_any._start_session = lambda **kwargs: calls.append(kwargs) or True

    started = MainWindow._handle_run_project_action(window_any)

    assert started is True
    assert calls == [{"mode": constants.RUN_MODE_PYTHON_SCRIPT, "entry_file": "app.py"}]


def test_handle_run_with_arguments_action_persists_argv_text_in_recent_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.persistence.settings_service import SettingsService

    loaded = _loaded_project_with_configs(tmp_path)
    window_any = _build_window_with_project(loaded)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: None)
    window_any._settings_service = SettingsService(state_root=tmp_path / "state")
    window_any._current_theme_tokens = lambda: None
    window_any._ensure_run_preflight_ready = lambda **_kwargs: True
    window_any._start_session = lambda **_kwargs: True

    monkeypatch.setattr(
        "app.shell.main_window.RunWithArgumentsDialog.run_dialog",
        lambda *_args, **_kwargs: RunInvocation(
            entry_file="app.py",
            argv=["--alpha"],
            argv_text="--alpha",
            working_directory=None,
            env_overrides={},
            save_request=False,
        ),
    )

    result = MainWindow._handle_run_with_arguments_action(window_any)

    assert result is True
    assert window_any._settings_service.load_recent_argv_history() == ["--alpha"]


def test_handle_run_with_arguments_action_cancelled_dialog_does_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.persistence.settings_service import SettingsService

    loaded = _loaded_project_with_configs(tmp_path)
    window_any = _build_window_with_project(loaded)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: None)
    window_any._settings_service = SettingsService(state_root=tmp_path / "state")
    window_any._current_theme_tokens = lambda: None
    window_any._start_session = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("session must not start when the dialog is cancelled")
    )

    monkeypatch.setattr(
        "app.shell.main_window.RunWithArgumentsDialog.run_dialog",
        lambda *_args, **_kwargs: None,
    )

    assert MainWindow._handle_run_with_arguments_action(window_any) is False
    assert window_any._settings_service.load_recent_argv_history() == []
