"""Integration tests for shell-side structured debug session parsing."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Mapping

import pytest

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.debug.debug_session import DebugSession
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService

pytestmark = [pytest.mark.integration, pytest.mark.runtime_parity]


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
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="Debug Session Project",
            default_entry="run.py",
            working_directory=".",
        ),
        entries=[],
    )


def test_debug_session_tracks_structured_pause_and_resume_events(tmp_path: Path) -> None:
    """DebugSession should ingest structured debug messages from a live debug run."""
    project_root = tmp_path / "project"
    (project_root / "cbcs").mkdir(parents=True)
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
            if event.event_type == "debug" and isinstance(event.payload, Mapping):
                session.apply_protocol_message(event.payload)

    assert _wait_until(
        lambda: (_feed_events() or True) and session.state.execution_state.value == "paused",
        timeout_seconds=12.0,
    )
    assert session.state.engine_name == "bdb"
    if not any(
        Path(frame.file_path).resolve() == script_path.resolve() and frame.line_number == 2
        for frame in session.state.frames
    ):
        service.send_debug_command("continue")
        assert _wait_until(
            lambda: (_feed_events() or True)
            and any(
                Path(frame.file_path).resolve() == script_path.resolve() and frame.line_number == 2
                for frame in session.state.frames
            ),
            timeout_seconds=12.0,
        )

    service.send_debug_command("continue")
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events), timeout_seconds=15.0)

    _feed_events()
    assert session.state.execution_state.value in {"running", "exited"}
