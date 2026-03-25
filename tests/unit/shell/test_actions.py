"""Unit tests for shell action-state mapping helpers."""

import pytest

from app.shell.actions import map_run_action_state

pytestmark = pytest.mark.unit


def test_map_run_action_state_without_project_disables_run_and_stop() -> None:
    """No loaded project should still allow Python Console start."""
    state = map_run_action_state(has_project=False, is_running=False)
    assert state.run_enabled is False
    assert state.debug_enabled is False
    assert state.stop_enabled is False
    assert state.pause_enabled is False
    assert state.python_console_enabled is True


def test_map_run_action_state_while_running_disables_run_enables_stop() -> None:
    """Running state should enforce single-run policy."""
    state = map_run_action_state(has_project=True, is_running=True)
    assert state.run_enabled is False
    assert state.debug_enabled is False
    assert state.stop_enabled is True
    assert state.pause_enabled is False
    assert state.step_over_enabled is False


def test_map_run_action_state_running_without_project_allows_stop_only() -> None:
    """Running without a project should still expose Stop; REPL is always available."""
    state = map_run_action_state(has_project=False, is_running=True)
    assert state.run_enabled is False
    assert state.debug_enabled is False
    assert state.stop_enabled is True
    assert state.python_console_enabled is True


def test_map_run_action_state_idle_project_enables_run_only() -> None:
    """Idle project state should allow run and disable stop."""
    state = map_run_action_state(has_project=True, is_running=False)
    assert state.run_enabled is True
    assert state.debug_enabled is True
    assert state.stop_enabled is False
    assert state.pause_enabled is False
    assert state.python_console_enabled is True


def test_map_run_action_state_paused_debug_enables_step_controls() -> None:
    """Paused debug sessions should enable continue and step commands."""
    state = map_run_action_state(has_project=True, is_running=True, is_debug_mode=True, is_debug_paused=True)
    assert state.continue_enabled is True
    assert state.pause_enabled is False
    assert state.step_over_enabled is True
    assert state.step_into_enabled is True
    assert state.step_out_enabled is True


def test_map_run_action_state_running_debug_enables_pause_only() -> None:
    """Running debug mode should allow pause and disable stepping."""
    state = map_run_action_state(has_project=True, is_running=True, is_debug_mode=True, is_debug_paused=False)
    assert state.pause_enabled is True
    assert state.continue_enabled is False
    assert state.step_over_enabled is False


def test_remove_all_breakpoints_disabled_when_no_breakpoints() -> None:
    state = map_run_action_state(has_project=True, is_running=False, has_breakpoints=False)
    assert state.remove_all_breakpoints_enabled is False


def test_remove_all_breakpoints_enabled_when_breakpoints_exist() -> None:
    state = map_run_action_state(has_project=True, is_running=False, has_breakpoints=True)
    assert state.remove_all_breakpoints_enabled is True


def test_remove_all_breakpoints_enabled_while_running_with_breakpoints() -> None:
    state = map_run_action_state(has_project=True, is_running=True, has_breakpoints=True)
    assert state.remove_all_breakpoints_enabled is True


def test_python_console_always_enabled() -> None:
    """REPL is independent; python_console_enabled should always be True."""
    for running in (True, False):
        for project in (True, False):
            state = map_run_action_state(has_project=project, is_running=running)
            assert state.python_console_enabled is True, (
                f"python_console_enabled should be True when has_project={project}, is_running={running}"
            )
