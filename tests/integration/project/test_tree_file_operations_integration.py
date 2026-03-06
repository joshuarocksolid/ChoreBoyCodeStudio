"""Integration tests for project tree operation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.import_rewrite import apply_import_rewrites, plan_import_rewrites
from app.project.file_operations import create_directory, create_file, move_path, rename_path

pytestmark = pytest.mark.integration


def test_file_move_and_import_rewrite_flow(tmp_path: Path) -> None:
    """Moving a module should allow planned import rewrites to be applied."""
    project_root = tmp_path / "project"
    create_directory(str(project_root))
    create_directory(str(project_root / "pkg"))
    create_file(str(project_root / "pkg" / "__init__.py"))
    create_file(str(project_root / "pkg" / "module.py"), content="value = 1\n")
    create_file(
        str(project_root / "consumer.py"),
        content="from pkg.module import value\nprint(value)\n",
    )

    moved_path = project_root / "pkg" / "renamed.py"
    move_result = move_path(str(project_root / "pkg" / "module.py"), str(moved_path))
    assert move_result.success is True

    previews = plan_import_rewrites(str(project_root), "pkg/module.py", "pkg/renamed.py")
    assert previews
    updated_files = apply_import_rewrites(previews)
    assert str((project_root / "consumer.py").resolve()) in updated_files
    assert "pkg.renamed" in (project_root / "consumer.py").read_text(encoding="utf-8")


def test_rename_path_preserves_filesystem_consistency(tmp_path: Path) -> None:
    """Rename helper should move file content without mutation."""
    file_path = tmp_path / "sample.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")
    destination = tmp_path / "renamed.py"

    result = rename_path(str(file_path), str(destination))

    assert result.success is True
    assert destination.exists()
    assert destination.read_text(encoding="utf-8") == "print('ok')\n"
