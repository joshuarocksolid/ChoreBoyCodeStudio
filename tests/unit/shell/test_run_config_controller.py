"""Unit tests for run-config controller orchestration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.models import LoadedProject, ProjectMetadata
from app.project.run_configs import RunConfiguration
from app.shell.run_config_controller import RunConfigController

pytestmark = pytest.mark.unit


def _loaded_project(tmp_path: Path) -> LoadedProject:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "name": "demo", "default_entry": "run.py"}, indent=2) + "\n",
        encoding="utf-8",
    )
    return LoadedProject(
        project_root=str(project_root.resolve()),
        manifest_path=str(manifest_path.resolve()),
        metadata=ProjectMetadata(
            schema_version=1,
            name="demo",
            default_entry="run.py",
            default_argv=["--default"],
            working_directory=".",
            env_overrides={"A": "1"},
            run_configs=[{"name": "Default", "entry_file": "run.py", "argv": []}],
        ),
        entries=[],
    )


def test_parse_config_input_validates_and_normalizes_fields() -> None:
    controller = RunConfigController()

    config = controller.parse_config_input(
        name=" Debug ",
        entry_file=" app/main.py ",
        argv_text="--foo   --bar",
        working_directory_text=" src ",
        env_overrides_text="A=1, B= two",
    )

    assert config.name == "Debug"
    assert config.entry_file == "app/main.py"
    assert config.argv == ["--foo", "--bar"]
    assert config.working_directory == "src"
    assert config.env_overrides == {"A": "1", "B": "two"}


def test_upsert_config_persists_updated_payload(tmp_path: Path) -> None:
    controller = RunConfigController()
    loaded_project = _loaded_project(tmp_path)
    existing = controller.load_configs(loaded_project)
    updated = RunConfiguration(name="Default", entry_file="app/main.py", argv=["--x"])

    merged = controller.upsert_config(
        loaded_project=loaded_project,
        existing_configs=existing,
        updated_config=updated,
    )

    assert merged == [updated]
    persisted = json.loads(Path(loaded_project.manifest_path).read_text(encoding="utf-8"))
    assert persisted["run_configs"] == [{"name": "Default", "entry_file": "app/main.py", "argv": ["--x"]}]


def test_delete_config_removes_entry_and_persists_manifest(tmp_path: Path) -> None:
    controller = RunConfigController()
    loaded_project = _loaded_project(tmp_path)
    existing = [
        RunConfiguration(name="Default", entry_file="run.py", argv=[]),
        RunConfiguration(name="Debug", entry_file="debug.py", argv=[]),
    ]

    remaining = controller.delete_config(
        loaded_project=loaded_project,
        existing_configs=existing,
        config_name="Default",
    )

    assert [config.name for config in remaining] == ["Debug"]
    persisted = json.loads(Path(loaded_project.manifest_path).read_text(encoding="utf-8"))
    assert persisted["run_configs"] == [{"name": "Debug", "entry_file": "debug.py", "argv": []}]
