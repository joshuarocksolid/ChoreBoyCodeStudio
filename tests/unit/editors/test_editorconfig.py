"""Unit tests for minimal `.editorconfig` indentation resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editors.editorconfig import resolve_editorconfig_indentation

pytestmark = pytest.mark.unit


def test_resolve_editorconfig_indentation_matches_file_pattern(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".editorconfig").write_text(
        "[*]\n"
        "indent_style = spaces\n"
        "indent_size = 2\n"
        "tab_width = 2\n"
        "\n"
        "[*.py]\n"
        "indent_size = 4\n"
        "tab_width = 4\n",
        encoding="utf-8",
    )
    file_path = project_root / "main.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    resolved = resolve_editorconfig_indentation(str(file_path), project_root=str(project_root))

    assert resolved is not None
    assert resolved.indent_style == "spaces"
    assert resolved.indent_size == 4
    assert resolved.tab_width == 4


def test_resolve_editorconfig_indentation_returns_none_without_valid_keys(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".editorconfig").write_text("[*.py]\ncharset = utf-8\n", encoding="utf-8")
    file_path = project_root / "main.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    resolved = resolve_editorconfig_indentation(str(file_path), project_root=str(project_root))

    assert resolved is None
