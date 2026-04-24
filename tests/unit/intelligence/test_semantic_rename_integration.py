"""Integration tests for semantic rename planning and apply flow."""
from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from app.intelligence.refactor_service import apply_rename_plan, plan_rename_symbol

pytestmark = pytest.mark.unit

FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "semantic"


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    source = FIXTURES_ROOT / fixture_name
    target = tmp_path / fixture_name
    shutil.copytree(source, target)
    return target


def test_plan_rename_symbol_builds_patch_style_preview(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    consumer_path = (project_root / "consumer.py").resolve()
    source = consumer_path.read_text(encoding="utf-8")

    plan = plan_rename_symbol(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=source.rfind("helper") + 2,
        new_symbol="renamed_helper",
    )

    assert plan is not None
    assert plan.metadata.source == "semantic"
    assert len(plan.preview_patches) == 2
    assert any("---" in patch.diff_text and "+++" in patch.diff_text for patch in plan.preview_patches)


def test_apply_rename_plan_updates_related_files_only(tmp_path: Path) -> None:
    project_root = _copy_fixture(tmp_path, "imported_project")
    consumer_path = (project_root / "consumer.py").resolve()
    source = consumer_path.read_text(encoding="utf-8")

    plan = plan_rename_symbol(
        project_root=str(project_root.resolve()),
        current_file_path=str(consumer_path),
        source_text=source,
        cursor_position=source.rfind("helper") + 2,
        new_symbol="renamed_helper",
    )
    assert plan is not None

    result = apply_rename_plan(plan)

    assert result.changed_occurrences >= 2
    assert "renamed_helper" in (project_root / "lib.py").read_text(encoding="utf-8")
    assert "renamed_helper" in consumer_path.read_text(encoding="utf-8")
