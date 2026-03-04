"""Unit tests for the ReplSessionManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.shell.repl_session_manager import ReplSessionManager

pytestmark = pytest.mark.unit


class _FakeSupervisor:
    def __init__(self) -> None:
        self._running = False
        self.start_calls: list[tuple[list[str], str]] = []
        self.stop_calls: int = 0

    def is_running(self) -> bool:
        return self._running

    def start(self, command: list[str], *, cwd: str, env=None) -> int:
        self.start_calls.append((command, cwd))
        self._running = True
        return 12345

    def stop(self, *, terminate_timeout_seconds: float = 2.0) -> int | None:
        self.stop_calls += 1
        self._running = False
        return 0

    def send_input(self, text: str) -> None:
        pass


def _make_manager(**kwargs) -> tuple[ReplSessionManager, _FakeSupervisor]:
    mgr = ReplSessionManager(state_root="/tmp/test-repl-state", **kwargs)
    fake_sup = _FakeSupervisor()
    mgr._supervisor = fake_sup  # type: ignore[assignment]
    return mgr, fake_sup


def test_start_launches_subprocess(tmp_path) -> None:
    mgr = ReplSessionManager(state_root=str(tmp_path))
    assert mgr.is_running is False
    with patch.object(mgr, "_launch") as mock_launch:
        mgr.start()
        mock_launch.assert_called_once()


def test_stop_suppresses_auto_restart() -> None:
    mgr, sup = _make_manager()
    sup._running = True
    mgr.stop()
    assert mgr._auto_restart is False
    assert sup.stop_calls == 1


def test_restart_stops_then_starts() -> None:
    mgr = ReplSessionManager(state_root="/tmp/test-repl-state")
    stop_mock = MagicMock()
    launch_mock = MagicMock()
    mgr.stop = stop_mock  # type: ignore[method-assign]
    mgr._launch = launch_mock  # type: ignore[method-assign]
    mgr.restart()
    stop_mock.assert_called_once()
    launch_mock.assert_called_once()


def test_send_input_appends_newline() -> None:
    mgr, sup = _make_manager()
    sup._running = True
    sent: list[str] = []
    sup.send_input = lambda text: sent.append(text)  # type: ignore[assignment]
    mgr.send_input("print(1)")
    assert sent == ["print(1)\n"]


def test_send_input_preserves_existing_newline() -> None:
    mgr, sup = _make_manager()
    sup._running = True
    sent: list[str] = []
    sup.send_input = lambda text: sent.append(text)  # type: ignore[assignment]
    mgr.send_input("print(1)\n")
    assert sent == ["print(1)\n"]


def test_shutdown_prevents_restart() -> None:
    mgr, sup = _make_manager()
    sup._running = True
    mgr.shutdown()
    assert mgr._shutting_down is True
    assert mgr._auto_restart is False
    assert sup.stop_calls == 1


def test_output_callback_invoked() -> None:
    lines: list[tuple[str, str]] = []
    mgr, _ = _make_manager(on_output=lambda text, stream: lines.append((text, stream)))
    from app.run.process_supervisor import ProcessEvent
    mgr._handle_event(ProcessEvent(event_type="output", stream="stdout", text="hello\n"))
    assert lines == [("hello\n", "stdout")]


def test_session_ended_callback_invoked() -> None:
    ended: list[tuple[int | None, bool]] = []
    mgr, _ = _make_manager(
        on_session_ended=lambda rc, tbu: ended.append((rc, tbu)),
    )
    mgr._auto_restart = False
    from app.run.process_supervisor import ProcessEvent
    mgr._handle_event(ProcessEvent(event_type="exit", return_code=0, terminated_by_user=False))
    assert ended == [(0, False)]


def test_build_command_for_apprun_bootstraps_runner_parent_path(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner_boot = tmp_path / "run_runner.py"
    runner_boot.write_text("print('stub')\n", encoding="utf-8")
    mgr = ReplSessionManager(
        runtime_executable="/opt/freecad/AppRun",
        runner_boot_path=str(runner_boot),
        state_root=str(tmp_path / "state"),
    )

    command = mgr._build_command("/tmp/run_manifest.json")

    assert command[0] == "/opt/freecad/AppRun"
    assert command[1] == "-c"
    payload = command[2]
    assert "sys.path.insert(0" in payload
    assert str(tmp_path.resolve()) in payload
    assert "runpy.run_path" in payload
