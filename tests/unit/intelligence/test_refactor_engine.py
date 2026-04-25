"""Unit tests for Rope refactor apply behavior."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.refactor_engine import RopeRefactorEngine
from app.intelligence.semantic_models import SemanticRenamePatch, SemanticRenamePlan, exact_metadata
from app.persistence.atomic_write import atomic_write_text

pytestmark = pytest.mark.unit


def test_apply_rename_rolls_back_on_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    helper = project_root / "helper.py"
    helper.write_text("def task_name():\n    return 1\n", encoding="utf-8")
    main = project_root / "main.py"
    main.write_text("from helper import task_name\nvalue = task_name()\n", encoding="utf-8")
    original_helper = helper.read_text(encoding="utf-8")
    original_main = main.read_text(encoding="utf-8")

    plan = SemanticRenamePlan(
        old_symbol="task_name",
        new_symbol="renamed_task",
        hits=[],
        preview_patches=[
            SemanticRenamePatch(
                file_path=str(helper),
                relative_path="helper.py",
                diff_text="",
                updated_content=original_helper.replace("task_name", "renamed_task"),
                changed_line_numbers=[1],
            ),
            SemanticRenamePatch(
                file_path=str(main),
                relative_path="main.py",
                diff_text="",
                updated_content=original_main.replace("task_name", "renamed_task"),
                changed_line_numbers=[1, 2],
            ),
        ],
        metadata=exact_metadata("rope"),
    )
    call_count = {"count": 0}

    def flaky_atomic_write(path: Path | str, data: str, *, encoding: str = "utf-8") -> Path:
        call_count["count"] += 1
        if call_count["count"] == 2:
            raise OSError("simulated write failure")
        return atomic_write_text(path, data, encoding=encoding)

    monkeypatch.setattr("app.intelligence.refactor_engine.atomic_write_text", flaky_atomic_write)

    with pytest.raises(OSError):
        RopeRefactorEngine().apply_rename(plan)

    assert helper.read_text(encoding="utf-8") == original_helper
    assert main.read_text(encoding="utf-8") == original_main
