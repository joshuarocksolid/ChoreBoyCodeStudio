"""Integration tests for importing plain Python folders as projects."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import pytest

from app.project.project_service import open_project
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


def _runner_boot_path() -> str:
    return str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve())


def test_open_plain_python_folder_auto_initializes_manifest(tmp_path: Path) -> None:
    """Opening a plain Python folder should auto-generate `cbcs/project.json`."""
    project_root = tmp_path / "plain_python_project"
    project_root.mkdir(parents=True)
    (project_root / "run.py").write_text("print('IMPORT_OK')\n", encoding="utf-8")
    (project_root / "app").mkdir()
    (project_root / "app" / "helper.py").write_text("print('helper')\n", encoding="utf-8")

    loaded_project = open_project(project_root)
    manifest_path = project_root / "cbcs" / "project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest_path.exists()
    assert payload["template"] == "imported_external"
    assert payload["default_entry"] == "run.py"
    assert loaded_project.metadata.default_entry == "run.py"
    assert all(not entry.relative_path.startswith("cbcs") for entry in loaded_project.entries)


def test_open_plain_python_folder_infers_entry_from_pyproject_scripts(tmp_path: Path) -> None:
    """Pyproject scripts should drive entrypoint inference during first-open import."""
    project_root = tmp_path / "pyproject_import_project"
    (project_root / "src" / "demo_pkg").mkdir(parents=True)
    (project_root / "src" / "demo_pkg" / "cli.py").write_text("def main():\n    print('OK')\n", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(
        "[project]\n"
        "name = \"demo\"\n"
        "[project.scripts]\n"
        "demo = \"demo_pkg.cli:main\"\n",
        encoding="utf-8",
    )

    loaded_project = open_project(project_root)

    assert loaded_project.metadata.default_entry == "src/demo_pkg/cli.py"


def test_auto_initialized_project_runs_successfully(tmp_path: Path) -> None:
    """Imported plain Python folders should run through the standard run path."""
    project_root = tmp_path / "plain_runnable_project"
    project_root.mkdir(parents=True)
    (project_root / "main.py").write_text("print('IMPORTED_RUN_OK')\n", encoding="utf-8")

    loaded_project = open_project(project_root)
    assert loaded_project.metadata.default_entry == "main.py"

    events: list[ProcessEvent] = []
    run_service = RunService(
        on_event=events.append,
        runtime_executable=sys.executable,
        runner_boot_path=_runner_boot_path(),
    )
    session = run_service.start_run(loaded_project)

    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)
    combined_output = "".join(event.text or "" for event in events if event.event_type == "output")
    assert "IMPORTED_RUN_OK" in combined_output
