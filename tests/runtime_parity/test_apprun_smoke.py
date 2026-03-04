"""Runtime-parity smoke tests for FreeCAD AppRun execution path."""

from __future__ import annotations

import os
from pathlib import Path
import time

import pytest

from app.core import constants
from app.core.models import LoadedProject, ProjectMetadata
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> str:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping runtime parity smoke tests.")
    if not os.access(str(app_run), os.X_OK):
        pytest.skip(f"AppRun exists but is not executable at {app_run}; skipping runtime parity smoke tests.")
    return str(app_run.resolve())


def _loaded_project(project_root: Path) -> LoadedProject:
    return LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str((project_root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="runtime-parity",
            default_entry="main.py",
            working_directory=".",
        ),
        entries=[],
    )


def _wait_until(condition, *, timeout_seconds: float = 12.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_apprun_manifest_execution_smoke_and_log_contract(tmp_path: Path) -> None:
    """AppRun should execute run manifest and write run log under `cbcs/logs`."""
    runtime_executable = _require_apprun()
    project_root = tmp_path / "runtime_project"
    (project_root / "cbcs").mkdir(parents=True, exist_ok=True)
    entry_path = project_root / "main.py"
    entry_path.write_text("print('RUNTIME_PARITY_OK')\n", encoding="utf-8")
    (project_root / "cbcs" / "project.json").write_text(
        '{"schema_version": 1, "name": "runtime-parity", "default_entry": "main.py"}\n',
        encoding="utf-8",
    )

    events: list[ProcessEvent] = []
    service = RunService(
        on_event=events.append,
        runtime_executable=runtime_executable,
        runner_boot_path=str((Path(__file__).resolve().parents[2] / "run_runner.py").resolve()),
    )

    session = service.start_run(_loaded_project(project_root))
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events)), (
        "Timed out waiting for AppRun parity smoke process to exit."
    )

    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)
    assert any("RUNTIME_PARITY_OK" in (event.text or "") for event in events if event.event_type == "output")
    assert Path(session.manifest_path).is_file()
    assert str(Path(session.log_file_path).parent).endswith("cbcs/logs")
    assert Path(session.log_file_path).is_file()
