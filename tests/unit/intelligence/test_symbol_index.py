"""Unit tests for project Python symbol index."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.intelligence.symbol_index import build_python_symbol_index

pytestmark = pytest.mark.unit


def test_build_python_symbol_index_collects_functions_and_classes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "module.py").write_text(
        "class Widget:\n    pass\n\ndef helper():\n    return 1\n",
        encoding="utf-8",
    )

    index = build_python_symbol_index(str(project_root))

    assert "Widget" in index
    assert "helper" in index
    assert index["Widget"][0].line_number == 1
