"""Unit tests for tree-sitter-backed syntax highlighters."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextDocument  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.syntax_engine import DEFAULT_DARK_PALETTE, DEFAULT_LIGHT_PALETTE  # noqa: E402
from app.editors.syntax_registry import default_syntax_highlighter_registry  # noqa: E402
from app.treesitter.loader import initialize_tree_sitter_runtime  # noqa: E402

pytestmark = pytest.mark.unit
_TREE_SITTER_AVAILABLE = initialize_tree_sitter_runtime().is_available


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _render(file_path: str, text: str, *, is_dark: bool = False):  # type: ignore[no-untyped-def]
    if not _TREE_SITTER_AVAILABLE:
        pytest.skip("Tree-sitter runtime unavailable in this environment.")
    document = QTextDocument()
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path=file_path,
        document=document,
        is_dark=is_dark,
        sample_text=text,
    )
    assert highlighter is not None
    document.setPlainText(text)
    highlighter.rehighlight()
    QApplication.processEvents()
    return document, highlighter


def _color_at(document: QTextDocument, line_number: int, column: int) -> str | None:
    block = document.findBlockByNumber(line_number)
    if not block.isValid():
        return None
    layout = block.layout()
    if layout is None:
        return None
    for formatted_range in layout.formats():
        start = formatted_range.start
        end = formatted_range.start + formatted_range.length
        if start <= column < end:
            return formatted_range.format.foreground().color().name().lower()
    return None


def test_python_tree_sitter_highlighter_formats_keywords() -> None:
    source = "def build(value):\n    return value\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    keyword_color = _color_at(document, 0, 0)
    assert keyword_color == DEFAULT_LIGHT_PALETTE["keyword"].lower()


def test_json_tree_sitter_highlighter_formats_keys_and_literals() -> None:
    source = '{"name": "alice", "enabled": true}\n'
    document, highlighter = _render("/tmp/data.json", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    key_color = _color_at(document, 0, source.index("name"))
    literal_color = _color_at(document, 0, source.index("true"))
    assert key_color == DEFAULT_LIGHT_PALETTE["json_key"].lower()
    assert literal_color == DEFAULT_LIGHT_PALETTE["json_literal"].lower()


def test_markdown_tree_sitter_highlighter_formats_headings() -> None:
    source = "# Heading\nBody\n"
    document, highlighter = _render("/tmp/readme.md", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    heading_color = _color_at(document, 0, source.index("#"))
    assert heading_color == DEFAULT_LIGHT_PALETTE["markdown_heading"].lower()


def test_theme_switch_updates_tree_sitter_palette() -> None:
    source = "def build(value):\n    return value\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    light_color = _color_at(document, 0, 0)
    highlighter.set_theme_palette(None, is_dark=True)
    highlighter.rehighlight()
    QApplication.processEvents()
    dark_color = _color_at(document, 0, 0)
    assert light_color == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    assert dark_color == DEFAULT_DARK_PALETTE["keyword"].lower()


def test_registry_returns_none_for_unknown_extensions_without_sniff_match() -> None:
    document = QTextDocument()
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/blob.bin",
        document=document,
        is_dark=False,
        sample_text="opaque bytes",
    )
    assert highlighter is None
