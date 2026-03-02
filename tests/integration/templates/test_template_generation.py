"""Integration tests for generated template projects."""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from app.core.models import LoadedProject
from app.project.project_service import open_project
from app.run.process_supervisor import ProcessEvent
from app.run.run_service import RunService
from app.templates.template_service import TemplateService

pytestmark = pytest.mark.integration


def _wait_until(predicate, timeout_seconds: float = 5.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _repo_templates_root() -> Path:
    return Path(__file__).resolve().parents[3] / "templates"


def _runner_boot_path() -> str:
    return str((Path(__file__).resolve().parents[3] / "run_runner.py").resolve())


def _run_generated_project(loaded_project: LoadedProject) -> tuple[str, list[ProcessEvent]]:
    events: list[ProcessEvent] = []
    service = RunService(on_event=events.append, runner_boot_path=_runner_boot_path())
    session = service.start_run(loaded_project)
    assert _wait_until(lambda: any(event.event_type == "exit" for event in events))
    return session.log_file_path, events


def test_materialized_utility_template_runs_successfully(tmp_path: Path) -> None:
    """Utility template should materialize and execute successfully."""
    service = TemplateService(templates_root=str(_repo_templates_root()))
    project_root = service.materialize_template(
        template_id="utility_script",
        destination_path=tmp_path / "utility_project",
        project_name="Utility",
    )
    loaded_project = open_project(project_root)
    log_path, events = _run_generated_project(loaded_project)

    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)
    assert "Utility template ready." in Path(log_path).read_text(encoding="utf-8")


def test_materialized_headless_template_runs_successfully(tmp_path: Path) -> None:
    """Headless tool template should materialize and execute successfully."""
    service = TemplateService(templates_root=str(_repo_templates_root()))
    project_root = service.materialize_template(
        template_id="headless_tool",
        destination_path=tmp_path / "headless_project",
        project_name="Headless",
    )
    loaded_project = open_project(project_root)
    log_path, events = _run_generated_project(loaded_project)

    assert any(event.event_type == "exit" and event.return_code == 0 for event in events)
    assert "Headless tool template ready." in Path(log_path).read_text(encoding="utf-8")


def test_materialized_qt_template_contains_expected_entrypoints(tmp_path: Path) -> None:
    """Qt template should generate expected source files and metadata."""
    service = TemplateService(templates_root=str(_repo_templates_root()))
    project_root = service.materialize_template(
        template_id="qt_app",
        destination_path=tmp_path / "qt_project",
        project_name="QtApp",
    )
    loaded_project = open_project(project_root)
    manifest = loaded_project.metadata

    assert manifest.template == "qt_app"
    assert manifest.default_entry == "main.py"
    assert manifest.default_mode == "qt_app"
    assert (project_root / "main.py").exists()
    assert (project_root / "app" / "main_window.py").exists()
