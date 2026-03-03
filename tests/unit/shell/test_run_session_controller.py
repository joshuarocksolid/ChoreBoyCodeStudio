"""Unit tests for shell run-session controller logic."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.run.run_service import RunSession
from app.shell.menus import MenuStubRegistry
from app.shell.run_session_controller import RunSessionController

pytestmark = pytest.mark.unit


@dataclass
class _FakeAction:
    enabled: bool = False

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self.enabled = enabled


class _FakeSupervisor:
    def __init__(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running


class _FakeRunService:
    def __init__(self) -> None:
        self.supervisor = _FakeSupervisor()
        self.is_debug_mode = False
        self.is_debug_paused = False
        self.stopped = False
        self.paused = False

    def start_run(  # type: ignore[no-untyped-def]
        self,
        loaded_project: LoadedProject | None,
        *,
        mode: str,
        entry_file=None,
        argv=None,
        working_directory=None,
        env_overrides=None,
        breakpoints=None,
    ) -> RunSession:
        self.supervisor._running = True
        self.is_debug_mode = mode == constants.RUN_MODE_PYTHON_DEBUG
        project_root = loaded_project.project_root if loaded_project is not None else "/tmp/repl"
        entry = loaded_project.metadata.default_entry if loaded_project is not None else "__repl__.py"
        return RunSession(
            run_id="run123",
            manifest_path=f"{project_root}/.cbcs/runs/run.json",
            log_file_path=f"{project_root}/logs/run_run123.log",
            project_root=project_root,
            entry_file=entry,
            mode=mode,
        )

    def stop_run(self) -> int:
        self.supervisor._running = False
        self.stopped = True
        return 0

    def pause_run(self) -> bool:
        self.paused = True
        return True


def _loaded_project() -> LoadedProject:
    return LoadedProject(
        project_root="/tmp/project",
        manifest_path="/tmp/project/.cbcs/project.json",
        metadata=ProjectMetadata(schema_version=1, name="proj"),
        entries=[],
    )


def _menu_registry() -> MenuStubRegistry:
    actions = {
        "shell.action.run.run": _FakeAction(),
        "shell.action.run.debug": _FakeAction(),
        "shell.action.run.stop": _FakeAction(),
        "shell.action.run.restart": _FakeAction(),
        "shell.action.run.continue": _FakeAction(),
        "shell.action.run.pause": _FakeAction(),
        "shell.action.run.stepOver": _FakeAction(),
        "shell.action.run.stepInto": _FakeAction(),
        "shell.action.run.stepOut": _FakeAction(),
        "shell.action.run.toggleBreakpoint": _FakeAction(),
        "shell.action.run.pythonConsole": _FakeAction(),
        "shell.action.run.removeAllBreakpoints": _FakeAction(),
    }
    return MenuStubRegistry(actions=actions)


def test_start_session_requires_loaded_project() -> None:
    controller = RunSessionController(_FakeRunService())  # type: ignore[arg-type]
    result = controller.start_session(
        loaded_project=None,
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        entry_file=None,
        argv=None,
        working_directory=None,
        env_overrides=None,
        breakpoints=None,
        skip_save=False,
        save_all=lambda: True,
        before_start=lambda: None,
        append_console_line=lambda _text, _stream: None,
        append_python_console_line=lambda _text: None,
    )
    assert result.started is False
    assert result.error_message == "Open a project before running code."


def test_start_session_rejects_repl_without_loaded_project() -> None:
    """REPL is now managed separately; RunSessionController always requires a project."""
    controller = RunSessionController(_FakeRunService())  # type: ignore[arg-type]
    result = controller.start_session(
        loaded_project=None,
        mode=constants.RUN_MODE_PYTHON_REPL,
        entry_file=None,
        argv=None,
        working_directory=None,
        env_overrides=None,
        breakpoints=None,
        skip_save=True,
        save_all=lambda: True,
        before_start=lambda: None,
        append_console_line=lambda _text, _stream: None,
        append_python_console_line=lambda _text: None,
    )
    assert result.started is False
    assert result.error_message == "Open a project before running code."


def test_start_session_success_updates_active_mode_and_returns_session() -> None:
    controller = RunSessionController(_FakeRunService())  # type: ignore[arg-type]
    lines: list[str] = []
    result = controller.start_session(
        loaded_project=_loaded_project(),
        mode=constants.RUN_MODE_PYTHON_REPL,
        entry_file=None,
        argv=None,
        working_directory=None,
        env_overrides=None,
        breakpoints=None,
        skip_save=True,
        save_all=lambda: True,
        before_start=lambda: lines.append("prepared"),
        append_console_line=lambda text, _stream: lines.append(text.strip()),
        append_python_console_line=lambda text: lines.append(text),
    )

    assert result.started is True
    assert result.session is not None
    assert controller.active_session_mode == constants.RUN_MODE_PYTHON_REPL
    assert "prepared" in lines
    assert any("Run started" in line for line in lines)


def test_refresh_action_states_updates_run_action_enablement() -> None:
    run_service = _FakeRunService()
    controller = RunSessionController(run_service)  # type: ignore[arg-type]
    registry = _menu_registry()

    controller.refresh_action_states(registry, has_project=False)
    assert registry.action("shell.action.run.run").enabled is False
    assert registry.action("shell.action.run.pythonConsole").enabled is True

    controller.refresh_action_states(registry, has_project=True)
    assert registry.action("shell.action.run.run").enabled is True
    assert registry.action("shell.action.run.stop").enabled is False

    run_service.supervisor._running = True
    controller.refresh_action_states(registry, has_project=True)
    assert registry.action("shell.action.run.run").enabled is False
    assert registry.action("shell.action.run.stop").enabled is True
