"""Import boundary tests for syntax highlighting modules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_treesitter_highlighter_core_does_not_import_editor_overlay_policy() -> None:
    source = Path("app/treesitter/highlighter_core.py").read_text(encoding="utf-8")
    assert "app.editors.editor_overlay_policy" not in source
    tree = ast.parse(source)
    overlay_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.editors.editor_overlay_policy"
    ]
    assert overlay_imports == []


def test_syntax_palette_from_tokens_round_trips_theme_fields() -> None:
    from PySide2.QtGui import QPalette

    from app.editors.syntax_engine import SYNTAX_PALETTE_FIELD_MAP, syntax_palette_from_tokens
    from app.shell.theme_tokens import tokens_from_palette

    tokens = tokens_from_palette(QPalette(), force_mode="dark")
    palette = syntax_palette_from_tokens(tokens)
    for token_key, field_name in SYNTAX_PALETTE_FIELD_MAP.items():
        assert token_key in palette
        assert palette[token_key] == getattr(tokens, field_name)
