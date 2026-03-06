"""Unit tests for the ReplSessionManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.shell.repl_session_manager import ReplSessionManager

pytestmark = pytest.mark.unit


class _FakeSupervisor:
    def __init__(self) -> None:
        self._running = False
        self.start_calls: list[tuple[str, str]] = []
        self.stop_calls: int = 0
        self.inputs: list[str] = []

    def is_running(self) -> bool:
        return self._running

    def start_manifest(self, *, manifest_path: str, cwd: str, env=None) -> int:
        self.start_calls.append((manifest_path, cwd))
        self._running = True
        return 12345

    def stop(self) -> int | None:
        self.stop_calls += 1
        self._running = False
        return 0

    def send_input(self, text: str) -> None:
        self.inputs.append(text)


def _make_manager(**kwargs) -> tuple[ReplSessionManager, _FakeSupervisor]:
    if "state_root" not in kwargs:
        kwargs["state_root"] = "/tmp/test-repl-state"
    mgr = ReplSessionManager(**kwargs)
    fake_sup = _FakeSupervisor()
    mgr._host_manager = fake_sup  # type: ignore[assignment]
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
    mgr.send_input("print(1)")
    assert sup.inputs == ["print(1)\n"]


def test_send_input_preserves_existing_newline() -> None:
    mgr, sup = _make_manager()
    mgr.send_input("print(1)\n")
    assert sup.inputs == ["print(1)\n"]


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


def test_launch_delegates_manifest_start_to_host_manager(tmp_path) -> None:  # type: ignore[no-untyped-def]
    mgr, sup = _make_manager(state_root=str(tmp_path))

    mgr._launch()

    assert len(sup.start_calls) == 1
    manifest_path, cwd = sup.start_calls[0]
    assert str(manifest_path).endswith(".json")
    assert cwd
