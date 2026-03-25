"""Unit tests for rename symbol refactor service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.refactor_service import apply_rename_plan, plan_rename_symbol

pytestmark = pytest.mark.unit


def test_plan_rename_symbol_collects_hits_for_symbol_under_cursor(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "helper.py").write_text("def task_name():\n    return 1\n", encoding="utf-8")
    current_file = project_root / "main.py"
    source = "from helper import task_name\nvalue = task_name()\n"
    current_file.write_text(source, encoding="utf-8")

    plan = plan_rename_symbol(
        project_root=str(project_root.resolve()),
        current_file_path=str(current_file.resolve()),
        source_text=source,
        cursor_position=source.rfind("task_name") + 2,
        new_symbol="task_new_name",
    )

    assert plan is not None
    assert plan.old_symbol == "task_name"
    assert plan.new_symbol == "task_new_name"
    assert len(plan.hits) >= 2


def test_apply_rename_plan_updates_all_references(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    helper = project_root / "helper.py"
    helper.write_text("def task_name():\n    return 1\n", encoding="utf-8")
    main = project_root / "main.py"
    source = "from helper import task_name\nvalue = task_name()\n"
    main.write_text(source, encoding="utf-8")

    plan = plan_rename_symbol(
        project_root=str(project_root.resolve()),
        current_file_path=str(main.resolve()),
        source_text=source,
        cursor_position=source.rfind("task_name") + 2,
        new_symbol="renamed_task",
    )
    assert plan is not None

    result = apply_rename_plan(plan)

    assert result.changed_occurrences >= 2
    assert "renamed_task" in helper.read_text(encoding="utf-8")
    assert "renamed_task" in main.read_text(encoding="utf-8")
    assert "task_name" not in helper.read_text(encoding="utf-8")


def test_apply_rename_plan_rolls_back_on_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    helper = project_root / "helper.py"
    helper.write_text("def task_name():\n    return 1\n", encoding="utf-8")
    main = project_root / "main.py"
    source = "from helper import task_name\nvalue = task_name()\n"
    main.write_text(source, encoding="utf-8")

    plan = plan_rename_symbol(
        project_root=str(project_root.resolve()),
        current_file_path=str(main.resolve()),
        source_text=source,
        cursor_position=source.rfind("task_name") + 2,
        new_symbol="renamed_task",
    )
    assert plan is not None

    original_helper = helper.read_text(encoding="utf-8")
    original_main = main.read_text(encoding="utf-8")
    original_write_text = Path.write_text
    failing_target = str(main.resolve())
    call_count = {"count": 0}

    def flaky_write_text(self: Path, data: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        call_count["count"] += 1
        if str(self.resolve()) == failing_target and call_count["count"] == 2:
            raise OSError("simulated write failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", flaky_write_text)

    with pytest.raises(OSError):
        apply_rename_plan(plan)

    assert helper.read_text(encoding="utf-8") == original_helper
    assert main.read_text(encoding="utf-8") == original_main
