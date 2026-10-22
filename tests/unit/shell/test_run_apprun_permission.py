"""Run start PermissionError uses the FreeCAD 1.0 explanation."""

from __future__ import annotations

import pytest

from app.core import constants
from app.core.errors import RunLifecycleError
from app.run.runtime_launch import permission_denied_for_apprun
from app.shell.run_session_controller import RunSessionController

pytestmark = pytest.mark.unit


class _Supervisor:
    def is_running(self) -> bool:
        return False


class _Service:
    def __init__(self) -> None:
        self.supervisor = _Supervisor()

    def start_run(self, *_args: object, **_kwargs: object) -> None:
        exc = PermissionError(13, "Permission denied", "/opt/freecad/AppRun")
        raise RunLifecycleError(f"Failed to launch runner process: {exc}") from exc


def test_run_start_permission_error_explains_freecad_1() -> None:
    lines: list[str] = []
    controller = RunSessionController(_Service())  # type: ignore[arg-type]
    result = controller.start_session(
        loaded_project=None,
        mode=constants.RUN_MODE_PYTHON_SCRIPT,
        entry_file="/tmp/main.py",
        argv=None,
        working_directory=None,
        env_overrides=None,
        breakpoints=None,
        debug_exception_policy=None,
        source_maps=None,
        skip_save=True,
        save_all=lambda: True,
        before_start=lambda: None,
        append_console_line=lambda text, _stream: lines.append(text),
        append_python_console_line=lambda _text: None,
    )
    assert result.apprun_permission_denied
    assert result.error_message is not None
    assert "Running, debugging, and the Python console need FreeCAD 1.0" in result.error_message
    assert "LibrePy group" in result.error_message
    assert "/opt/freecad/AppRun" in result.error_message
    assert any("FreeCAD 1.0" in line for line in lines)
    wrapped = RunLifecycleError("Failed to launch runner process")
    assert permission_denied_for_apprun(wrapped) is False


def test_presenter_shows_freecad_explanation(monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[str] = []
    monkeypatch.setattr(
        "app.shell.startup_dialogs.present_freecad_requirement",
        lambda _parent, detail: shown.append(detail),
    )
    from app.shell.run_debug_presenter import RunDebugPresenter
    from app.shell.run_session_controller import RunSessionStartFailureReason, RunSessionStartResult

    class _Events:
        def bind_append_console_line(self) -> object:
            return lambda *_args: None

        def set_run_status(self, _status: str, return_code: int | None = None) -> None:
            del return_code

        def refresh_run_action_states(self) -> None:
            return None

    class _Controller:
        def start_session(self, **_kwargs: object) -> RunSessionStartResult:
            return RunSessionStartResult(
                started=False,
                failure_reason=RunSessionStartFailureReason.START_EXCEPTION,
                error_message="Running, debugging, and the Python console need FreeCAD 1.0",
                apprun_permission_denied=True,
            )

    class _Host:
        def run_event_workflow(self) -> _Events:
            return _Events()

        def run_session_controller(self) -> _Controller:
            return _Controller()

        def dialog_parent(self) -> None:
            return None

        def loaded_project(self) -> None:
            return None

        def save_workflow(self) -> object:
            return type("Save", (), {"handle_save_all_action": lambda self: True})()

        def prepare_for_session_start(self) -> None:
            return None

        def repl_event_workflow(self) -> object:
            return type("Repl", (), {"append_python_console_line": staticmethod(lambda _text: None)})()

    presenter = RunDebugPresenter(_Host())  # type: ignore[arg-type]
    started = presenter.start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, entry_file="/tmp/main.py")
    assert started is False
    assert shown == ["Running, debugging, and the Python console need FreeCAD 1.0"]
