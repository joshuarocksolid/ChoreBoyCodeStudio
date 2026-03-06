"""Compatibility guards for Python 3.9 runtime constraints."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_syntax_registry_avoids_runtime_pipe_union_aliases() -> None:
    """Runtime-evaluated aliases should avoid ``|`` unions on Python 3.9."""
    source_path = Path("app/editors/syntax_registry.py")
    source = source_path.read_text(encoding="utf-8")
    assert "from __future__ import annotations" in source
    assert "HighlighterFactory =" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value_segment = ast.get_source_segment(source, node.value) or ""
        assert "|" not in value_segment
