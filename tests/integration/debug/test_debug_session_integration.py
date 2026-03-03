"""Integration tests for shell-side debug session parsing."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.debug.debug_session import DebugSession
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
            name="Debug Session Project",
            default_entry="run.py",
            working_directory=".",
            safe_mode=True,
        ),
        entries=[],
    )


def test_debug_session_tracks_paused_and_running_markers(tmp_path: Path) -> None:
    """DebugSession should ingest output markers emitted by running debug process."""
    project_root = tmp_path / "project"
    (project_root / ".cbcs").mkdir(parents=True)
    script_path = project_root / "run.py"
    script_path.write_text("x = 5\nx = x + 1\nprint(x)\n", encoding="utf-8")
    loaded_project = _build_loaded_project(project_root)

    events: list[ProcessEvent] = []
    service = RunService(
        on_event=events.append,
        runtime_executable=None,
        runner_boot_path=str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve()),
    )
    session = DebugSession()

    service.start_run(
        loaded_project,
        mode=constants.RUN_MODE_PYTHON_DEBUG,
        breakpoints=[{"file_path": str(script_path.resolve()), "line_number": 2}],
    )
    assert _wait_until(lambda: service.supervisor.is_running())

    def _feed_events() -> None:
        for event in events:
            if event.event_type == "output" and event.text:
                session.ingest_output_line(event.text)

    assert _wait_until(
        lambda: (_feed_events() or True) and session.state.execution_state.value in {"paused", "running"},
        timeout_seconds=8.0,
    )

    service.send_input("continue\n")
    service.send_input("continue\n")
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events), timeout_seconds=8.0)
