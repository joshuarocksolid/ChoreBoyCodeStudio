"""Shell action-state helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunActionState:
    """Computed enabled state for run controls."""

    run_enabled: bool
    stop_enabled: bool


def map_run_action_state(*, has_project: bool, is_running: bool) -> RunActionState:
    """Map shell run lifecycle state to Run/Stop enabled flags."""
    if not has_project:
        return RunActionState(run_enabled=False, stop_enabled=False)
    if is_running:
        return RunActionState(run_enabled=False, stop_enabled=True)
    return RunActionState(run_enabled=True, stop_enabled=False)
