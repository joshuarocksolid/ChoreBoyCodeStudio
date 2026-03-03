"""Integration tests for run service orchestration."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.debug.debug_event_protocol import parse_debug_output_line
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService
from app.core import constants

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
    assert session.log_file_path.endswith(".log")
    assert session.mode == constants.RUN_MODE_PYTHON_SCRIPT

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)
    combined_output = "".join(event.text or "" for event in events if event.event_type == "output")
    assert "RUN_SERVICE_OK" in combined_output
    log_path = Path(session.log_file_path)
    assert log_path.exists()
    assert "RUN_SERVICE_OK" in log_path.read_text(encoding="utf-8")


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


def test_run_service_python_repl_supports_input_and_output(tmp_path: Path) -> None:
    """Python REPL mode should accept stdin and emit evaluated output."""
    project_root = tmp_path / "project"
    (project_root / ".cbcs").mkdir(parents=True)
    (project_root / "run.py").write_text("print('unused')\n", encoding="utf-8")
    loaded_project = _build_loaded_project(project_root)

    events: list[ProcessEvent] = []
    service = RunService(
        on_event=events.append,
        runtime_executable=None,
        runner_boot_path=str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve()),
    )

    service.start_run(loaded_project, mode=constants.RUN_MODE_PYTHON_REPL)
    assert _wait_until(lambda: service.supervisor.is_running())
    service.send_input("print('REPL_OK')\n")
    service.send_input("exit()\n")

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events), timeout_seconds=8.0)
    assert any(event.event_type == "output" and "REPL_OK" in (event.text or "") for event in events)


def test_run_service_projectless_python_repl_uses_home_cwd_and_executes_multiline(tmp_path: Path) -> None:
    """Projectless REPL mode should run from home cwd and execute multiline blocks."""
    events: list[ProcessEvent] = []
    service = RunService(
        on_event=events.append,
        runtime_executable=None,
        runner_boot_path=str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve()),
        state_root=str((tmp_path / "state").resolve()),
    )

    session = service.start_run(None, mode=constants.RUN_MODE_PYTHON_REPL)
    assert Path(session.manifest_path).exists()
    assert _wait_until(lambda: service.supervisor.is_running())

    service.send_input("import os\n")
    service.send_input("print(os.getcwd())\n")
    service.send_input("for i in range(2):\n    print(i)\n\n")
    service.send_input("exit()\n")

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events), timeout_seconds=8.0)
    output_text = "".join(event.text or "" for event in events if event.event_type == "output")
    assert str(Path.home().expanduser().resolve()) in output_text
    assert "0\n1" in output_text


def test_run_service_python_debug_hits_breakpoint_and_continues(tmp_path: Path) -> None:
    """Debug mode should pause on configured breakpoint and resume via stdin command."""
    project_root = tmp_path / "project"
    (project_root / ".cbcs").mkdir(parents=True)
    script_path = project_root / "run.py"
    script_path.write_text("value = 41\nvalue = value + 1\nprint(value)\n", encoding="utf-8")
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
    assert _wait_until(lambda: service.is_debug_paused, timeout_seconds=8.0)

    def _first_paused_frame() -> tuple[Path, int] | None:
        for event in events:
            if event.event_type != "output" or not event.text:
                continue
            parsed_event = parse_debug_output_line(event.text)
            if parsed_event is None or parsed_event.event_type != "paused" or not parsed_event.frames:
                continue
            frame = parsed_event.frames[0]
            return (Path(frame.file_path).resolve(), frame.line_number)
        return None

    assert _wait_until(lambda: _first_paused_frame() is not None, timeout_seconds=8.0)
    first_paused_frame = _first_paused_frame()
    assert first_paused_frame is not None
    assert first_paused_frame[0] == script_path.resolve()
    assert first_paused_frame[1] == 2

    service.send_input("continue\n")
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events), timeout_seconds=8.0)
    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)
    assert any(event.event_type == "output" and "__CB_DEBUG_PAUSED__" in (event.text or "") for event in events)
