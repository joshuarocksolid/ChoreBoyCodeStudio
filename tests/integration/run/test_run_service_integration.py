"""Integration tests for run service orchestration."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService

pytestmark = pytest.mark.integration


def _wait_until(predicate, timeout_seconds: float = 5.0) -> bool:
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
            name="Test Project",
            default_entry="run.py",
            default_mode="python_script",
            working_directory=".",
            safe_mode=True,
        ),
        entries=[],
    )


def test_run_service_starts_runner_and_writes_artifacts(tmp_path: Path) -> None:
    """Run service should create manifest/log artifacts and emit process events."""
    project_root = tmp_path / "project"
    (project_root / ".cbcs").mkdir(parents=True)
    (project_root / "run.py").write_text("print('RUN_SERVICE_OK')\n", encoding="utf-8")
    loaded_project = _build_loaded_project(project_root)

    events: list[ProcessEvent] = []
    service = RunService(
        on_event=events.append,
        runtime_executable=None,
        runner_boot_path=str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve()),
    )

    session = service.start_run(loaded_project)
    assert Path(session.manifest_path).exists()
    assert Path(session.log_file_path).exists() is False

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    assert Path(session.log_file_path).exists()
    assert "RUN_SERVICE_OK" in Path(session.log_file_path).read_text(encoding="utf-8")
    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)


def test_run_service_stop_terminates_long_running_run(tmp_path: Path) -> None:
    """Stop should terminate long-running runs with user-terminated exit flag."""
    project_root = tmp_path / "project"
    (project_root / ".cbcs").mkdir(parents=True)
    (project_root / "run.py").write_text("import time\nprint('tick')\ntime.sleep(30)\n", encoding="utf-8")
    loaded_project = _build_loaded_project(project_root)

    events: list[ProcessEvent] = []
    service = RunService(
        on_event=events.append,
        runtime_executable=None,
        runner_boot_path=str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve()),
    )

    service.start_run(loaded_project)
    assert _wait_until(lambda: service.supervisor.is_running())

    service.stop_run()
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    assert any(event.event_type == "exit" and event.terminated_by_user for event in events)
