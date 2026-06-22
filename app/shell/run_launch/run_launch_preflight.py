"""Run preflight checks before launching a session."""

from __future__ import annotations

from app.shell.run_launch.run_launch_workflow_host import RunLaunchWorkflowHost
from app.support.preflight import build_run_preflight


def ensure_run_preflight_ready(
    host: RunLaunchWorkflowHost,
    *,
    title: str,
    entry_file: str,
    working_directory: str | None = None,
    config_name: str | None = None,
) -> bool:
    result = build_run_preflight(
        loaded_project=host.loaded_project(),
        entry_file=entry_file,
        working_directory=working_directory,
        config_name=config_name,
    )
    if result.is_ready:
        return True
    host.show_run_preflight_result(title, result.summary, result.issues)
    return False
