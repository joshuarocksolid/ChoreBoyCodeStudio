"""Unit tests for run-output/debug routing coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.core import constants
from app.debug.debug_session import DebugSession
from app.run.problem_parser import ProblemEntry
from app.run.process_supervisor import ProcessEvent
from app.shell.run_output_coordinator import RunOutputCoordinator

pytestmark = pytest.mark.unit


@dataclass
class _CoordinatorHarness:
    active_mode: str | None = constants.RUN_MODE_PYTHON_SCRIPT
    shutting_down: bool = False
    auto_open_console: bool = False
    auto_open_problems: bool = False
    problems: list[ProblemEntry] = field(default_factory=list)
    debug_session: DebugSession = field(default_factory=DebugSession)
    output_tail: list[str] = field(default_factory=list)
    console_lines: list[tuple[str, str]] = field(default_factory=list)
    debug_lines: list[str] = field(default_factory=list)
    statuses: list[tuple[str, int | None]] = field(default_factory=list)
    focused_tabs: list[str] = field(default_factory=list)
    debug_inspector_updates: int = 0
    refresh_calls: int = 0
    debug_input_enabled: list[bool] = field(default_factory=list)
    finalized_return_codes: list[int | None] = field(default_factory=list)

    def build(self) -> RunOutputCoordinator:
        return RunOutputCoordinator(
            is_shutting_down=lambda: self.shutting_down,
            get_active_session_mode=lambda: self.active_mode,
            set_active_session_mode=lambda mode: setattr(self, "active_mode", mode),
            get_debug_session=lambda: self.debug_session,
            append_output_tail=self.output_tail.append,
            append_console_line=lambda text, stream: self.console_lines.append((text, stream)),
            append_debug_output_line=self.debug_lines.append,
            apply_debug_inspector_event=self._record_debug_inspector_update,
            refresh_run_action_states=self._record_refresh_call,
            set_run_status=lambda status, return_code=None: self.statuses.append((status, return_code)),
            focus_run_log_tab=lambda: self.focused_tabs.append("run_log"),
            focus_problems_tab=lambda: self.focused_tabs.append("problems"),
            set_debug_command_input_enabled=self.debug_input_enabled.append,
            finalize_run_log=self.finalized_return_codes.append,
            update_problems_from_output=lambda: list(self.problems),
            auto_open_console_on_run_output_enabled=lambda: self.auto_open_console,
            auto_open_problems_on_run_failure_enabled=lambda: self.auto_open_problems,
        )

    def _record_debug_inspector_update(self) -> None:
        self.debug_inspector_updates += 1

    def _record_refresh_call(self) -> None:
        self.refresh_calls += 1


def test_apply_output_routes_run_log_and_debug_console_lines() -> None:
    harness = _CoordinatorHarness(
        active_mode=constants.RUN_MODE_PYTHON_DEBUG,
        auto_open_console=True,
    )
    coordinator = harness.build()

    coordinator.apply(ProcessEvent(event_type="output", stream="stdout", text="hello\n"))

    assert harness.output_tail == ["hello\n"]
    assert harness.console_lines == [("hello\n", "stdout")]
    assert harness.debug_lines == ["hello"]
    assert harness.focused_tabs == ["run_log"]
    assert harness.refresh_calls == 0


def test_apply_output_debug_protocol_events_refresh_without_appending_log() -> None:
    harness = _CoordinatorHarness(active_mode=constants.RUN_MODE_PYTHON_DEBUG)
    coordinator = harness.build()

    coordinator.apply(ProcessEvent(event_type="output", stream="stdout", text="__CB_DEBUG_PAUSED__\n"))

    assert harness.output_tail == []
    assert harness.console_lines == []
    assert harness.debug_lines == ["[debug] Paused at breakpoint."]
    assert harness.debug_inspector_updates == 1
    assert harness.refresh_calls == 1


def test_apply_exit_clears_session_and_focuses_problems_for_failed_run() -> None:
    harness = _CoordinatorHarness(
        active_mode=constants.RUN_MODE_PYTHON_DEBUG,
        auto_open_problems=True,
        problems=[
            ProblemEntry(
                file_path="/tmp/project/main.py",
                line_number=5,
                context="<module>",
                message="RuntimeError: boom",
            )
        ],
    )
    coordinator = harness.build()

    coordinator.apply(ProcessEvent(event_type="exit", return_code=1, terminated_by_user=False))

    assert harness.active_mode is None
    assert harness.debug_input_enabled == [False]
    assert harness.finalized_return_codes == [1]
    assert harness.statuses == [("failed", 1)]
    assert harness.focused_tabs == ["problems"]
    assert harness.refresh_calls == 1
    assert any("Run finished (code=1)." in line[0] for line in harness.console_lines)
