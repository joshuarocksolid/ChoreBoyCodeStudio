"""Shared test helpers for minimal canonical ChoreBoy Code Studio projects."""

from __future__ import annotations

import json
from pathlib import Path


def write_minimal_project(
    project_root: Path,
    *,
    name: str = "test_project",
    entry_file: str | None = "run.py",
    entry_text: str = "print('ok')\n",
) -> Path:
    """Write `cbcs/project.json` and an optional runnable entry file."""
    manifest_path = project_root / "cbcs" / "project.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if entry_file is not None:
        entry_path = project_root / entry_file
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text(entry_text, encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "name": name}, indent=2),
        encoding="utf-8",
    )
    return manifest_path
