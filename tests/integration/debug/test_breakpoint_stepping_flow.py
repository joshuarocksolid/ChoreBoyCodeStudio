"""Integration tests for debug breakpoint and stepping flow."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Mapping

import pytest

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService

pytestmark = [pytest.mark.integration, pytest.mark.slow, pytest.mark.timeout(180)]


def _wait_until(predicate, timeout_seconds: float = 6.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _debug_is_paused(events: list[ProcessEvent]) -> bool:
    paused = False
    for event in events:
        if event.event_type != "debug" or not isinstance(event.payload, Mapping):
            continue
        if event.payload.get("kind") != "event":
            continue
        event_name = str(event.payload.get("event", "")).strip()
        if event_name == "stopped":
            paused = True
        elif event_name in {"continued", "session_ready", "session_ended"}:
            paused = False
    return paused


def _build_loaded_project(project_root: Path) -> LoadedProject:
    return LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="Debug Project",
            default_entry="run.py",
            working_directory=".",
        ),
        entries=[],
    )


def _has_debug_events(events: list[ProcessEvent]) -> bool:
    return any(event.event_type == "debug" for event in events)


def test_debug_flow_pauses_then_steps_and_finishes(tmp_path: Path) -> None:
    """Debug sessions should pause at breakpoint and accept stepping commands."""
    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)
    script_path = project_root / "run.py"
    script_path.write_text("value = 1\nvalue += 1\nprint(value)\n", encoding="utf-8")
    loaded_project = _build_loaded_project(project_root)

    events: list[ProcessEvent] = []
    service = RunService(
        on_event=events.append,
        runtime_executable=None,
        runner_boot_path=str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve()),
    )

    service.start_run(
        loaded_project,
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        breakpoints=[{"file_path": str(script_path.resolve()), "line_number": 2}],
    )
    assert _wait_until(lambda: service.supervisor.is_running())
    if not _wait_until(lambda: _debug_is_paused(events)):
        if not _has_debug_events(events):
            service.stop_run()
            pytest.skip(
                "Debug transport did not emit events in this environment "
                "(runner subprocess started but no debug channel; known Cloud/AppRun limitation)."
            )
        assert _debug_is_paused(events)

    def stopped_event_count() -> int:
        count = 0
        for event in events:
            if event.event_type != "debug" or not isinstance(event.payload, Mapping):
                continue
            if event.payload.get("kind") == "event" and event.payload.get("event") == "stopped":
                count += 1
        return count

    paused_events_before_step = stopped_event_count()
    service.send_debug_command("step_over")
    assert _wait_until(lambda: _debug_is_paused(events) and stopped_event_count() > paused_events_before_step)

    service.send_debug_command("continue")

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events), timeout_seconds=15.0)
    assert any(event.event_type == "output" and "2" in (event.text or "") for event in events)
