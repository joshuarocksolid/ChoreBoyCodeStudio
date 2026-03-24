"""Unit tests for tree-sitter-backed syntax highlighters."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextCharFormat, QTextCursor, QTextDocument  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.syntax_engine import DEFAULT_DARK_PALETTE, DEFAULT_LIGHT_PALETTE  # noqa: E402
from app.editors.syntax_registry import default_syntax_highlighter_registry  # noqa: E402
from app.treesitter.loader import available_language_keys as loader_available_language_keys, initialize_tree_sitter_runtime  # noqa: E402

pytestmark = pytest.mark.unit
_TREE_SITTER_AVAILABLE = initialize_tree_sitter_runtime().is_available
_AVAILABLE_LANGUAGE_KEYS = set(loader_available_language_keys()) if _TREE_SITTER_AVAILABLE else set()


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _render(file_path: str, text: str, *, is_dark: bool = False) -> tuple[QTextDocument, Any]:
    if not _TREE_SITTER_AVAILABLE:
        pytest.skip("Tree-sitter runtime unavailable in this environment.")
    document = QTextDocument()
    registry = default_syntax_highlighter_registry()
    highlighter: Any = registry.create_for_path(
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
    formatted = _format_at(document, line_number, column)
    if formatted is None:
        return None
    return formatted.foreground().color().name().lower()


def _format_at(document: QTextDocument, line_number: int, column: int):  # type: ignore[no-untyped-def]
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
            return QTextCharFormat(formatted_range.format)
    return None


def test_python_tree_sitter_highlighter_formats_keywords() -> None:
    source = "def build(value):\n    return value\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    keyword_color = _color_at(document, 0, 0)
    control_keyword_color = _color_at(document, 1, 4)
    assert keyword_color == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    assert control_keyword_color == DEFAULT_LIGHT_PALETTE["keyword_control"].lower()


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


def test_markdown_tree_sitter_highlighter_formats_strong_and_markers() -> None:
    source = "**Bold** *it*\n- item\n"
    document, highlighter = _render("/tmp/readme.md", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    strong_color = _color_at(document, 0, 2)
    emphasis_color = _color_at(document, 0, 10)
    strong_format = _format_at(document, 0, 2)
    emphasis_format = _format_at(document, 0, 10)
    list_marker_color = _color_at(document, 1, 0)
    assert strong_color == DEFAULT_LIGHT_PALETTE["markdown_strong"].lower()
    assert emphasis_color == DEFAULT_LIGHT_PALETTE["markdown_emphasis"].lower()
    assert strong_format is not None
    assert emphasis_format is not None
    assert strong_format.fontWeight() > emphasis_format.fontWeight()
    assert list_marker_color == DEFAULT_LIGHT_PALETTE["punctuation"].lower()


def test_python_tree_sitter_highlighter_formats_builtins_and_escapes() -> None:
    line0 = "def build(self):"
    line1 = '    print("line\\n")'
    line2 = "    return self"
    source = f"{line0}\n{line1}\n{line2}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    self_param_color = _color_at(document, 0, line0.index("self"))
    builtin_call_color = _color_at(document, 1, line1.index("print"))
    escape_color = _color_at(document, 1, line1.index("\\n"))
    self_usage_color = _color_at(document, 2, line2.index("self"))
    assert self_param_color == DEFAULT_LIGHT_PALETTE["builtin"].lower()
    assert builtin_call_color == DEFAULT_LIGHT_PALETTE["builtin"].lower()
    assert self_usage_color == DEFAULT_LIGHT_PALETTE["builtin"].lower()
    assert escape_color == DEFAULT_LIGHT_PALETTE["escape"].lower()


def test_javascript_tree_sitter_highlighter_formats_builtin_and_constants() -> None:
    if "javascript" not in _AVAILABLE_LANGUAGE_KEYS:
        pytest.skip("Optional javascript tree-sitter grammar not vendored.")
    source = "const enabled = true;\nfunction read(){ return this.value; }\n"
    document, highlighter = _render("/tmp/main.js", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    true_color = _color_at(document, 0, source.splitlines()[0].index("true"))
    this_color = _color_at(document, 1, source.splitlines()[1].index("this"))
    assert true_color == DEFAULT_LIGHT_PALETTE["semantic_constant"].lower()
    assert this_color == DEFAULT_LIGHT_PALETTE["builtin"].lower()


def test_yaml_tree_sitter_highlighter_formats_mapping_keys() -> None:
    source = "root:\n  child: 1\n{name: 2}\n"
    document, highlighter = _render("/tmp/config.yaml", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    key_root = _color_at(document, 0, source.splitlines()[0].index("root"))
    key_child = _color_at(document, 1, source.splitlines()[1].index("child"))
    key_inline = _color_at(document, 2, source.splitlines()[2].index("name"))
    assert key_root == DEFAULT_LIGHT_PALETTE["json_key"].lower()
    assert key_child == DEFAULT_LIGHT_PALETTE["json_key"].lower()
    assert key_inline == DEFAULT_LIGHT_PALETTE["json_key"].lower()


def test_sql_tree_sitter_highlighter_formats_function_calls() -> None:
    if "sql" not in _AVAILABLE_LANGUAGE_KEYS:
        pytest.skip("Optional SQL tree-sitter grammar not vendored.")
    source = "SELECT COUNT(*) FROM items;\n"
    document, highlighter = _render("/tmp/query.sql", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    function_color = _color_at(document, 0, source.index("COUNT"))
    assert function_color == DEFAULT_LIGHT_PALETTE["semantic_function"].lower()


def test_theme_switch_updates_tree_sitter_palette() -> None:
    source = "def build(value):\n    return value\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    light_keyword_color = _color_at(document, 0, 0)
    light_control_keyword_color = _color_at(document, 1, 4)
    highlighter.set_theme_palette(None, is_dark=True)
    highlighter.rehighlight()
    QApplication.processEvents()
    dark_keyword_color = _color_at(document, 0, 0)
    dark_control_keyword_color = _color_at(document, 1, 4)
    assert light_keyword_color == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    assert dark_keyword_color == DEFAULT_DARK_PALETTE["keyword"].lower()
    assert light_control_keyword_color == DEFAULT_LIGHT_PALETTE["keyword_control"].lower()
    assert dark_control_keyword_color == DEFAULT_DARK_PALETTE["keyword_control"].lower()


def test_python_tree_sitter_highlighter_repaints_comment_after_in_place_edit() -> None:
    source = "def foo():\n    return 1\n"
    document, _highlighter = _render("/tmp/main.py", source, is_dark=False)
    keyword_color = _color_at(document, 0, 0)
    assert keyword_color == DEFAULT_LIGHT_PALETTE["keyword"].lower()

    cursor = QTextCursor(document)
    cursor.setPosition(0)
    cursor.insertText("#")
    QApplication.processEvents()

    comment_color = _color_at(document, 0, 0)
    assert comment_color == DEFAULT_LIGHT_PALETTE["comment"].lower()


def test_python_tree_sitter_highlighter_repaints_shifted_lines_after_line_join() -> None:
    source = "flag = True\n\nif cond:\n    print(1)\nelse:\n    print(2)\n"
    document, _highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert _color_at(document, 4, 0) == DEFAULT_LIGHT_PALETTE["keyword_control"].lower()
    assert _color_at(document, 5, 4) == DEFAULT_LIGHT_PALETTE["builtin"].lower()

    cursor = QTextCursor(document)
    cursor.setPosition(source.index("if cond"))
    cursor.deletePreviousChar()
    QApplication.processEvents()

    assert _color_at(document, 3, 0) == DEFAULT_LIGHT_PALETTE["keyword_control"].lower()
    assert _color_at(document, 4, 4) == DEFAULT_LIGHT_PALETTE["builtin"].lower()


def test_python_generic_identifiers_not_colored() -> None:
    line0 = "def build(value):"
    line1 = "    return value"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    keyword_color = _color_at(document, 0, 0)
    assert keyword_color == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    value_usage_color = _color_at(document, 1, line1.index("value"))
    assert value_usage_color is None


def test_python_freecad_macro_coloring() -> None:
    lines = [
        "import FreeCAD",
        "doc = FreeCAD.newDocument('Test')",
        "box = doc.addObject('Part::Box', 'B')",
        "box.Length = 50",
        "print(box.Width)",
    ]
    source = "\n".join(lines) + "\n"
    document, highlighter = _render("/tmp/macro.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    import_kw = _color_at(document, 0, 0)
    assert import_kw == DEFAULT_LIGHT_PALETTE["keyword_import"].lower()
    freecad_standalone = _color_at(document, 0, lines[0].index("FreeCAD"))
    assert freecad_standalone is None
    doc_lhs = _color_at(document, 1, 0)
    assert doc_lhs is None
    new_document_call = _color_at(document, 1, lines[1].index("newDocument"))
    assert new_document_call == DEFAULT_LIGHT_PALETTE["semantic_method"].lower()
    string_color = _color_at(document, 1, lines[1].index("'Test'"))
    assert string_color == DEFAULT_LIGHT_PALETTE["string"].lower()
    box_standalone = _color_at(document, 3, 0)
    assert box_standalone is None
    length_prop = _color_at(document, 3, lines[3].index("Length"))
    assert length_prop == DEFAULT_LIGHT_PALETTE["semantic_property"].lower()
    print_builtin = _color_at(document, 4, 0)
    assert print_builtin == DEFAULT_LIGHT_PALETTE["builtin"].lower()


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
