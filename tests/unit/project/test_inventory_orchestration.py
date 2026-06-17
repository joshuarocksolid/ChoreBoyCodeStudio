"""Spy tests for one-walk-per-generation inventory orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.project.file_excludes import EffectiveExcludes
from app.shell.project_inventory_orchestrator import ProjectInventoryOrchestrator

pytestmark = pytest.mark.unit


def test_project_open_rebuilds_snapshot_once_before_consumers(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    orchestrator = ProjectInventoryOrchestrator()
    effective = EffectiveExcludes.merge()
    build_calls: list[str] = []

    def _spy_build(project_root, *, exclude_patterns=()):  # type: ignore[no-untyped-def]
        build_calls.append(str(project_root))
        from app.project.file_inventory import build_project_inventory_snapshot as real_build

        return real_build(project_root, exclude_patterns=exclude_patterns)

    with patch("app.shell.project_inventory_orchestrator.build_project_inventory_snapshot", side_effect=_spy_build):
        orchestrator.rebuild(str(tmp_path), effective)
        snapshot = orchestrator.snapshot
        assert snapshot is not None
        assert len(build_calls) == 1

        # Consumers read the shared snapshot without rebuilding.
        python_paths = list(snapshot.python_file_paths)
        module_names = list(snapshot.module_names)
        assert python_paths
        assert module_names
        assert len(build_calls) == 1
