"""Integration tests for debug breakpoint and stepping flow."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService

pytestmark = pytest.mark.integration


def _wait_until(predicate, timeout_seconds: float = 6.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _build_loaded_project(project_root: Path) -> LoadedProject:
    return LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / ".cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="Debug Project",
            default_entry="run.py",
            default_mode=constants.RUN_MODE_PYTHON_SCRIPT,
            working_directory=".",
            safe_mode=True,
        ),
        entries=[],
    )


def test_debug_flow_pauses_then_steps_and_finishes(tmp_path: Path) -> None:
    """Debug sessions should pause at breakpoint and accept stepping commands."""
    project_root = tmp_path / "project"
    (project_root / ".cbcs").mkdir(parents=True)
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
    assert _wait_until(lambda: service.is_debug_paused)

    service.send_input("next\n")
    service.send_input("continue\n")
    service.send_input("continue\n")

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    assert any(event.event_type == "output" and "2" in (event.text or "") for event in events)
