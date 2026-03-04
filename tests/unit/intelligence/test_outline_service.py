"""Unit tests for file outline extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.outline_service import build_file_outline

pytestmark = pytest.mark.unit


def test_build_file_outline_extracts_classes_and_functions(tmp_path: Path) -> None:
    file_path = tmp_path / "module.py"
    file_path.write_text(
        "class Alpha:\n    pass\n\n\ndef run():\n    return 1\n",
        encoding="utf-8",
    )
    outline = build_file_outline(str(file_path))
    assert [entry.kind for entry in outline] == ["class", "function"]
    assert [entry.name for entry in outline] == ["Alpha", "run"]


def test_build_file_outline_returns_empty_for_non_python(tmp_path: Path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("# title\n", encoding="utf-8")
    assert build_file_outline(str(file_path)) == []
