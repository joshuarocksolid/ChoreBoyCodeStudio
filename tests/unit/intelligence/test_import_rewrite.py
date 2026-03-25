"""Unit tests for Python import rewrite planning."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pytest

from app.intelligence.import_rewrite import apply_import_rewrites, plan_import_rewrites
from app.persistence.atomic_write import atomic_write_text

pytestmark = pytest.mark.unit


def test_plan_import_rewrites_updates_import_lines(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "app").mkdir()
    (project_root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "app" / "consumer.py").write_text(
        "from app.module import value\nimport app.module\nprint(value)\n",
        encoding="utf-8",
    )

    previews = plan_import_rewrites(
        str(project_root),
        old_relative_path="app/module.py",
        new_relative_path="app/new_module.py",
    )

    assert len(previews) == 1
    preview = previews[0]
    assert "app.new_module" in preview.updated_content
    assert preview.changed_line_numbers == [1, 2]


def test_apply_import_rewrites_writes_updated_payload(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_file = project_root / "consumer.py"
    target_file.write_text("import app.module\n", encoding="utf-8")

    previews = plan_import_rewrites(
        str(project_root),
        old_relative_path="app/module.py",
        new_relative_path="app/new_module.py",
    )
    updated_files = apply_import_rewrites(previews)

    assert str(target_file.resolve()) in updated_files
    assert "app.new_module" in target_file.read_text(encoding="utf-8")


def test_apply_import_rewrites_rolls_back_on_atomic_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    first = project_root / "first.py"
    second = project_root / "second.py"
    first.write_text("import app.module\n", encoding="utf-8")
    second.write_text("from app.module import value\n", encoding="utf-8")

    previews = plan_import_rewrites(
        str(project_root),
        old_relative_path="app/module.py",
        new_relative_path="app/new_module.py",
    )
    assert len(previews) == 2

    original_first = first.read_text(encoding="utf-8")
    original_second = second.read_text(encoding="utf-8")
    failure_state = {"pending": True}

    def flaky_atomic_write(path: Union[Path, str], data: str, *, encoding: str = "utf-8") -> Path:
        resolved = Path(path).expanduser().resolve()
        if resolved == second.resolve() and failure_state["pending"]:
            failure_state["pending"] = False
            raise OSError("simulated import rewrite failure")
        return atomic_write_text(resolved, data, encoding=encoding)

    monkeypatch.setattr("app.intelligence.import_rewrite.atomic_write_text", flaky_atomic_write)

    with pytest.raises(OSError, match="simulated import rewrite failure"):
        apply_import_rewrites(previews)

    assert first.read_text(encoding="utf-8") == original_first
    assert second.read_text(encoding="utf-8") == original_second
