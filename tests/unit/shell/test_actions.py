"""Unit tests for shell action-state mapping helpers."""

import pytest

from app.shell.actions import map_run_action_state

pytestmark = pytest.mark.unit


def test_map_run_action_state_without_project_disables_run_and_stop() -> None:
    """No loaded project should disable run controls."""
    state = map_run_action_state(has_project=False, is_running=False)
    assert state.run_enabled is False
    assert state.stop_enabled is False


def test_map_run_action_state_while_running_disables_run_enables_stop() -> None:
    """Running state should enforce single-run policy."""
    state = map_run_action_state(has_project=True, is_running=True)
    assert state.run_enabled is False
    assert state.stop_enabled is True


def test_map_run_action_state_idle_project_enables_run_only() -> None:
    """Idle project state should allow run and disable stop."""
    state = map_run_action_state(has_project=True, is_running=False)
    assert state.run_enabled is True
    assert state.stop_enabled is False
