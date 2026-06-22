"""Characterization tests for clear-console policy sink matrix."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from app.shell.clear_console_policy import (
    clear_python_console_display,
    clear_run_output_sinks,
    prepare_new_run,
)

pytestmark = pytest.mark.unit


@dataclass
class FakeClearConsoleHost:
    console_model_cleared: bool = False
    run_log_cleared: bool = False
    run_log_begin_run_called: bool = False
    python_console_display_cleared: bool = False
    debug_output_cleared: bool = False
    output_tail_cleared: bool = False
    problems_cleared: bool = False
    debug_session_reset: bool = False
    debug_indicator_cleared: bool = False
    run_log_panel_present: bool = True
    python_console_present: bool = True
    debug_panel_present: bool = True
    events: list[str] = field(default_factory=list)

    def console_model(self) -> object:
        host = self

        def _clear() -> None:
            host.console_model_cleared = True
            host.events.append("console_model.clear")

        return SimpleNamespace(clear=_clear)

    def run_log_panel(self) -> object | None:
        if not self.run_log_panel_present:
            return None
        host = self

        return SimpleNamespace(
            clear=lambda: (
                setattr(host, "run_log_cleared", True),
                host.events.append("run_log.clear"),
            )[0],
            begin_run=lambda: (
                setattr(host, "run_log_begin_run_called", True),
                host.events.append("run_log.begin_run"),
            )[0],
        )

    def python_console_widget(self) -> object | None:
        if not self.python_console_present:
            return None
        host = self

        def _clear_console() -> None:
            host.python_console_display_cleared = True
            host.events.append("python_console.clear_console")

        return SimpleNamespace(clear_console=_clear_console)

    def debug_panel(self) -> object | None:
        if not self.debug_panel_present:
            return None
        host = self

        def _clear_output() -> None:
            host.debug_output_cleared = True
            host.events.append("debug_panel.clear_output")

        return SimpleNamespace(clear_output=_clear_output)

    def active_run_output_tail(self) -> object:
        host = self

        def _clear() -> None:
            host.output_tail_cleared = True
            host.events.append("output_tail.clear")

        return SimpleNamespace(clear=_clear)

    def clear_problems(self) -> None:
        self.problems_cleared = True
        self.events.append("clear_problems")

    def reset_debug_session(self) -> None:
        self.debug_session_reset = True
        self.events.append("reset_debug_session")

    def clear_debug_execution_indicator(self) -> None:
        self.debug_indicator_cleared = True
        self.events.append("clear_debug_execution_indicator")

    def run_log_begin_run(self) -> None:
        run_log_panel = self.run_log_panel()
        if run_log_panel is not None:
            self.run_log_begin_run_called = True
            self.events.append("run_log.begin_run")


def test_clear_run_output_sinks_clears_all_four() -> None:
    host = FakeClearConsoleHost()

    clear_run_output_sinks(host)

    assert host.console_model_cleared is True
    assert host.run_log_cleared is True
    assert host.python_console_display_cleared is True
    assert host.debug_output_cleared is True
    assert host.output_tail_cleared is False
    assert host.problems_cleared is False
    assert host.run_log_begin_run_called is False


def test_clear_python_console_display_only_touches_widget() -> None:
    host = FakeClearConsoleHost()

    clear_python_console_display(host)

    assert host.python_console_display_cleared is True
    assert host.console_model_cleared is False
    assert host.run_log_cleared is False
    assert host.debug_output_cleared is False


def test_prepare_new_run_resets_session_without_menu_clears() -> None:
    host = FakeClearConsoleHost()

    prepare_new_run(host)

    assert host.output_tail_cleared is True
    assert host.problems_cleared is True
    assert host.debug_session_reset is True
    assert host.debug_indicator_cleared is True
    assert host.run_log_begin_run_called is True
    assert host.console_model_cleared is False
    assert host.run_log_cleared is False
    assert host.python_console_display_cleared is False
    assert host.debug_output_cleared is False
