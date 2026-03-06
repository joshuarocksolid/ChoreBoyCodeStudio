"""Shell action-state helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunActionState:
    """Computed enabled state for run controls."""

    run_enabled: bool
    debug_enabled: bool
    run_project_enabled: bool
    debug_project_enabled: bool
    stop_enabled: bool
    restart_enabled: bool
    continue_enabled: bool
    pause_enabled: bool
    step_over_enabled: bool
    step_into_enabled: bool
    step_out_enabled: bool
    toggle_breakpoint_enabled: bool
    python_console_enabled: bool
    remove_all_breakpoints_enabled: bool
    package_enabled: bool


def map_run_action_state(
    *,
    has_project: bool,
    is_running: bool,
    is_debug_mode: bool = False,
    is_debug_paused: bool = False,
    has_breakpoints: bool = False,
) -> RunActionState:
    """Map shell run lifecycle state to Run/Stop enabled flags.

    ``python_console_enabled`` is always ``True`` because the REPL is now
    managed independently via ``ReplSessionManager``.
    """
    if is_running:
        return RunActionState(
            run_enabled=False,
            debug_enabled=False,
            run_project_enabled=False,
            debug_project_enabled=False,
            stop_enabled=True,
            restart_enabled=is_debug_mode,
            continue_enabled=is_debug_mode and is_debug_paused,
            pause_enabled=is_debug_mode and not is_debug_paused,
            step_over_enabled=is_debug_mode and is_debug_paused,
            step_into_enabled=is_debug_mode and is_debug_paused,
            step_out_enabled=is_debug_mode and is_debug_paused,
            toggle_breakpoint_enabled=not is_debug_mode,
            python_console_enabled=True,
            remove_all_breakpoints_enabled=has_breakpoints,
            package_enabled=False,
        )
    if not has_project:
        return RunActionState(
            run_enabled=False,
            debug_enabled=False,
            run_project_enabled=False,
            debug_project_enabled=False,
            stop_enabled=False,
            restart_enabled=False,
            continue_enabled=False,
            pause_enabled=False,
            step_over_enabled=False,
            step_into_enabled=False,
            step_out_enabled=False,
            toggle_breakpoint_enabled=False,
            python_console_enabled=True,
            remove_all_breakpoints_enabled=has_breakpoints,
            package_enabled=False,
        )
    return RunActionState(
        run_enabled=True,
        debug_enabled=True,
        run_project_enabled=True,
        debug_project_enabled=True,
        stop_enabled=False,
        restart_enabled=False,
        continue_enabled=False,
        pause_enabled=False,
        step_over_enabled=False,
        step_into_enabled=False,
        step_out_enabled=False,
        toggle_breakpoint_enabled=True,
        python_console_enabled=True,
        remove_all_breakpoints_enabled=has_breakpoints,
        package_enabled=True,
    )
