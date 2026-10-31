"""Unit tests for tree-sitter-backed syntax highlighters."""

from __future__ import annotations

import functools
from dataclasses import replace
from typing import Any

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtGui import QTextCharFormat, QTextCursor, QTextDocument  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402

from app.editors.syntax_engine import DEFAULT_DARK_PALETTE, DEFAULT_LIGHT_PALETTE  # noqa: E402
from app.editors.syntax_registry import default_syntax_highlighter_registry  # noqa: E402
from app.treesitter.highlighter_core import TreeSitterHighlighter  # noqa: E402
from app.treesitter.language_registry import default_tree_sitter_language_registry  # noqa: E402
from app.treesitter.loader import available_language_keys as loader_available_language_keys, initialize_tree_sitter_runtime  # noqa: E402

pytestmark = pytest.mark.unit


@functools.lru_cache(maxsize=1)
def _tree_sitter_state() -> tuple[bool, frozenset[str]]:
    """Initialize the tree-sitter runtime lazily on first test access.

    Module-level initialization adds noticeable cost to test *collection*; the
    cache here moves that cost to the first test that actually needs it while
    keeping the result consistent across the whole session.
    """
    runtime = initialize_tree_sitter_runtime()
    if not runtime.is_available:
        return False, frozenset()
    return True, frozenset(loader_available_language_keys())


def _tree_sitter_available() -> bool:
    return _tree_sitter_state()[0]


def _available_language_keys() -> frozenset[str]:
    return _tree_sitter_state()[1]


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _render(file_path: str, text: str, *, is_dark: bool = False) -> tuple[QTextDocument, Any]:
    if not _tree_sitter_available():
        pytest.skip("Tree-sitter runtime unavailable in this environment.")
    document = QTextDocument()
    registry = default_syntax_highlighter_registry()
    highlighter: Any = registry.create_for_path(
        file_path=file_path,
        document=document,
        is_dark=is_dark,
        sample_text=text,
    )
    if highlighter is None:
        pytest.skip(f"tree-sitter highlighter unavailable for {file_path}")
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
    heading_color = _color_at(document, 0, source.index("Heading"))
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


def test_python_word_operators_use_dedicated_keyword_operator_color() -> None:
    line0 = "if APP_DIR not in sys.path and FOO:"
    line1 = "    Foo(app_dir=1, log_file=2)"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    not_color = _color_at(document, 0, line0.index("not"))
    in_color = _color_at(document, 0, line0.index(" in ") + 1)
    and_color = _color_at(document, 0, line0.index("and"))
    expected = DEFAULT_LIGHT_PALETTE["keyword_operator"].lower()
    assert not_color == expected
    assert in_color == expected
    assert and_color == expected
    arithmetic_color = _color_at(document, 1, line1.index("="))
    assert arithmetic_color == DEFAULT_LIGHT_PALETTE["operator"].lower()


def test_python_keyword_argument_names_use_parameter_color() -> None:
    line0 = "Foo(app_dir=1, log_file=2)"
    source = f"{line0}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    app_dir_color = _color_at(document, 0, line0.index("app_dir"))
    log_file_color = _color_at(document, 0, line0.index("log_file"))
    expected = DEFAULT_LIGHT_PALETTE["parameter"].lower()
    assert app_dir_color == expected
    assert log_file_color == expected


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


def test_python_match_case_keywords_are_highlighted_as_control() -> None:
    line0 = "match value:"
    line1 = "    case 1:"
    line2 = "        pass"
    source = "\n".join((line0, line1, line2)) + "\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    expected = DEFAULT_LIGHT_PALETTE["keyword_control"].lower()
    assert _color_at(document, 0, line0.index("match")) == expected
    assert _color_at(document, 1, line1.index("case")) == expected


def test_python_args_and_kwargs_definitions_use_parameter_color() -> None:
    line0 = "def call(*args, **kwargs):"
    line1 = "    return args, kwargs"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    expected = DEFAULT_LIGHT_PALETTE["parameter"].lower()
    assert _color_at(document, 0, line0.index("args")) == expected
    assert _color_at(document, 0, line0.index("kwargs")) == expected


def test_python_walrus_and_inplace_operators_use_operator_color() -> None:
    line0 = "if (n := 1) > 0:"
    line1 = "    n **= 2"
    line2 = "    n //= 2"
    line3 = "    y = a @ b"
    source = "\n".join((line0, line1, line2, line3)) + "\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    expected = DEFAULT_LIGHT_PALETTE["operator"].lower()
    assert _color_at(document, 0, line0.index(":=")) == expected
    assert _color_at(document, 1, line1.index("**=")) == expected
    assert _color_at(document, 2, line2.index("//=")) == expected
    assert _color_at(document, 3, line3.index("@")) == expected


def test_python_fstring_interpolation_contents_are_styled() -> None:
    line0 = "name = 'alice'"
    line1 = "value = f'hello {name!r:>10s}'"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    name_in_interp_color = _color_at(document, 1, line1.index("{name") + 1)
    assert name_in_interp_color == DEFAULT_LIGHT_PALETTE["semantic_variable"].lower()
    type_conversion_color = _color_at(document, 1, line1.index("!r"))
    assert type_conversion_color == DEFAULT_LIGHT_PALETTE["decorator"].lower()
    brace_color = _color_at(document, 1, line1.index("{"))
    assert brace_color == DEFAULT_LIGHT_PALETTE["punctuation"].lower()


def test_python_fstring_complex_interpolation_breaks_out_of_string_color() -> None:
    line0 = "import os"
    line1 = "import sys"
    line2 = 'msg = f"cwd: {os.getcwd()}"'
    line3 = 'msg2 = f"argv ({len(sys.argv)} items)"'
    source = "\n".join((line0, line1, line2, line3)) + "\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=True)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    palette = DEFAULT_DARK_PALETTE
    assert _color_at(document, 2, line2.index("cwd")) == palette["string"].lower()
    assert _color_at(document, 2, line2.index("{")) == palette["punctuation"].lower()
    assert _color_at(document, 2, line2.index("os")) == palette["semantic_import"].lower()
    assert _color_at(document, 2, line2.index("getcwd")) == palette["semantic_method"].lower()
    assert _color_at(document, 3, line3.index("len")) == palette["builtin"].lower()
    assert _color_at(document, 3, line3.index("sys")) == palette["semantic_import"].lower()
    argv_in_interp = line3.index("sys.argv") + len("sys.")
    assert _color_at(document, 3, argv_in_interp) == palette["semantic_property"].lower()


def test_python_fstring_prefix_uses_string_prefix_token() -> None:
    line = 'value = f"hello"'
    source = f"{line}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    assert _color_at(document, 0, line.index("f")) == DEFAULT_LIGHT_PALETTE["string_prefix"].lower()
    assert _color_at(document, 0, line.index("hello")) == DEFAULT_LIGHT_PALETTE["string"].lower()


def test_python_plain_string_quotes_and_content_remain_string_colored() -> None:
    line = 'value = "hello"'
    source = f"{line}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    expected = DEFAULT_LIGHT_PALETTE["string"].lower()
    assert _color_at(document, 0, line.index('"')) == expected
    assert _color_at(document, 0, line.index("hello")) == expected


def test_python_tree_sitter_highlighter_formats_builtin_exceptions_and_dunders() -> None:
    line0 = "try:"
    line1 = "    raise ValueError('x')"
    line2 = "except Exception as err:"
    line3 = "    pass"
    line4 = ""
    line5 = "if __name__ == '__main__':"
    line6 = "    print(__file__)"
    source = "\n".join([line0, line1, line2, line3, line4, line5, line6]) + "\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    expected = DEFAULT_LIGHT_PALETTE["builtin"].lower()
    assert _color_at(document, 1, line1.index("ValueError")) == expected
    assert _color_at(document, 2, line2.index("Exception")) == expected
    assert _color_at(document, 5, line5.index("__name__")) == expected
    assert _color_at(document, 6, line6.index("__file__")) == expected


def test_javascript_tree_sitter_highlighter_formats_builtin_and_constants() -> None:
    if "javascript" not in _available_language_keys():
        pytest.skip("Optional javascript tree-sitter grammar not vendored.")
    source = "const enabled = true;\nfunction read(){ return this.value; }\n"
    document, highlighter = _render("/tmp/main.js", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    true_color = _color_at(document, 0, source.splitlines()[0].index("true"))
    this_color = _color_at(document, 1, source.splitlines()[1].index("this"))
    assert true_color == DEFAULT_LIGHT_PALETTE["semantic_constant"].lower()
    assert this_color == DEFAULT_LIGHT_PALETTE["builtin"].lower()


def test_javascript_locals_color_module_level_function_reference() -> None:
    if "javascript" not in _available_language_keys():
        pytest.skip("Optional javascript tree-sitter grammar not vendored.")
    line0 = "function helper() { return 1; }"
    line1 = "run(helper);"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/main.js", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    reference_color = _color_at(document, 1, line1.index("helper"))
    assert reference_color == DEFAULT_LIGHT_PALETTE["semantic_function"].lower()


def test_javascript_locals_color_module_level_class_reference() -> None:
    if "javascript" not in _available_language_keys():
        pytest.skip("Optional javascript tree-sitter grammar not vendored.")
    line0 = "class Widget {}"
    line1 = "factory(Widget);"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/main.js", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    reference_color = _color_at(document, 1, line1.index("Widget"))
    assert reference_color == DEFAULT_LIGHT_PALETTE["semantic_class"].lower()


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
    source = "SELECT COUNT(*) FROM items;\n"
    document, highlighter = _render("/tmp/query.sql", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    function_color = _color_at(document, 0, source.index("COUNT"))
    assert function_color == DEFAULT_LIGHT_PALETTE["semantic_function"].lower()
    table_color = _color_at(document, 0, source.index("items"))
    assert table_color == DEFAULT_LIGHT_PALETTE["class"].lower()


def test_sql_extended_keywords_are_styled_as_keywords() -> None:
    source = (
        "WITH RECURSIVE cte AS (SELECT 1) "
        "SELECT name FROM events RETURNING id;\n"
    )
    document, _ = _render("/tmp/extended.sql", source, is_dark=False)
    keyword_color = DEFAULT_LIGHT_PALETTE["keyword"].lower()
    assert _color_at(document, 0, source.index("WITH")) == keyword_color
    assert _color_at(document, 0, source.index("RECURSIVE")) == keyword_color
    assert _color_at(document, 0, source.index("RETURNING")) == keyword_color


def test_sql_column_type_keyword_is_styled_as_class() -> None:
    source = "CREATE TABLE log (id BIGINT PRIMARY KEY, body TEXT);\n"
    document, _ = _render("/tmp/types.sql", source, is_dark=False)
    type_color = DEFAULT_LIGHT_PALETTE["class"].lower()
    assert _color_at(document, 0, source.index("BIGINT")) == type_color
    assert _color_at(document, 0, source.index("TEXT")) == type_color


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


def test_python_locals_color_parameter_references_without_capturing_every_identifier() -> None:
    line0 = "def build(value):"
    line1 = "    return value"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    keyword_color = _color_at(document, 0, 0)
    assert keyword_color == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    value_usage_color = _color_at(document, 1, line1.index("value"))
    assert value_usage_color == DEFAULT_LIGHT_PALETTE["semantic_parameter"].lower()


def test_python_locals_color_module_level_function_reference() -> None:
    line0 = "def helper():"
    line1 = "    return 1"
    line2 = ""
    line3 = "run(helper)"
    source = "\n".join((line0, line1, line2, line3)) + "\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    reference_color = _color_at(document, 3, line3.index("helper"))
    assert reference_color == DEFAULT_LIGHT_PALETTE["semantic_function"].lower()


def test_python_locals_color_module_level_class_reference() -> None:
    line0 = "class Widget:"
    line1 = "    pass"
    line2 = ""
    line3 = "factory(Widget)"
    source = "\n".join((line0, line1, line2, line3)) + "\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    reference_color = _color_at(document, 3, line3.index("Widget"))
    assert reference_color == DEFAULT_LIGHT_PALETTE["semantic_class"].lower()


def test_python_locals_color_walrus_binding_references() -> None:
    line0 = "if (count := compute()) > 0:"
    line1 = "    print(count)"
    line2 = "log(count)"
    source = "\n".join((line0, line1, line2)) + "\n"
    document, highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    inside_color = _color_at(document, 1, line1.index("count"))
    after_color = _color_at(document, 2, line2.index("count"))
    expected = DEFAULT_LIGHT_PALETTE["semantic_variable"].lower()
    assert inside_color == expected
    assert after_color == expected


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
    assert freecad_standalone == DEFAULT_LIGHT_PALETTE["semantic_import"].lower()
    doc_lhs = _color_at(document, 1, 0)
    assert doc_lhs == DEFAULT_LIGHT_PALETTE["semantic_variable"].lower()
    new_document_call = _color_at(document, 1, lines[1].index("newDocument"))
    assert new_document_call == DEFAULT_LIGHT_PALETTE["semantic_method"].lower()
    string_color = _color_at(document, 1, lines[1].index("'Test'"))
    assert string_color == DEFAULT_LIGHT_PALETTE["string"].lower()
    box_standalone = _color_at(document, 3, 0)
    assert box_standalone == DEFAULT_LIGHT_PALETTE["semantic_variable"].lower()
    length_prop = _color_at(document, 3, lines[3].index("Length"))
    assert length_prop == DEFAULT_LIGHT_PALETTE["semantic_property"].lower()
    print_builtin = _color_at(document, 4, 0)
    assert print_builtin == DEFAULT_LIGHT_PALETTE["builtin"].lower()


def test_python_highlighter_formats_imports_annotations_async_and_locals() -> None:
    line0 = "from datetime import datetime as dt"
    line1 = ""
    line2 = "async def build(value: datetime) -> datetime:"
    line3 = "    current = dt.now()"
    line4 = "    await work(value)"
    line5 = "    return current"
    source = "\n".join((line0, line1, line2, line3, line4, line5)) + "\n"
    document, _highlighter = _render("/tmp/main.py", source, is_dark=False)
    assert _color_at(document, 0, line0.index("datetime")) == DEFAULT_LIGHT_PALETTE["semantic_import"].lower()
    assert _color_at(document, 2, 0) == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    assert _color_at(document, 2, line2.index("datetime")) == DEFAULT_LIGHT_PALETTE["semantic_class"].lower()
    assert _color_at(document, 3, line3.index("current")) == DEFAULT_LIGHT_PALETTE["semantic_variable"].lower()
    assert _color_at(document, 3, line3.index("dt")) == DEFAULT_LIGHT_PALETTE["semantic_import"].lower()
    assert _color_at(document, 4, line4.index("await")) == DEFAULT_LIGHT_PALETTE["keyword_control"].lower()
    assert _color_at(document, 4, line4.index("value")) == DEFAULT_LIGHT_PALETTE["semantic_parameter"].lower()


def test_html_tree_sitter_injects_script_and_style_languages() -> None:
    line0 = "<script>const answer = 1;</script>"
    line1 = "<style>body{color:red;}</style>"
    source = f"{line0}\n{line1}\n"
    document, highlighter = _render("/tmp/index.html", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    assert _color_at(document, 0, line0.index("const")) == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    assert _color_at(document, 1, line1.index("body")) == DEFAULT_LIGHT_PALETTE["class"].lower()
    assert _color_at(document, 1, line1.index("color")) == DEFAULT_LIGHT_PALETTE["semantic_property"].lower()


def test_yaml_document_markers_and_tags_are_styled() -> None:
    line0 = "%YAML 1.2"
    line1 = "---"
    line2 = "value: !!str hello"
    source = "\n".join((line0, line1, line2)) + "\n"
    document, _ = _render("/tmp/sample.yaml", source, is_dark=False)
    assert _color_at(document, 0, 0) == DEFAULT_LIGHT_PALETTE["keyword_import"].lower()
    assert _color_at(document, 1, 0) == DEFAULT_LIGHT_PALETTE["punctuation"].lower()
    assert _color_at(document, 2, line2.index("!!str")) == DEFAULT_LIGHT_PALETTE["decorator"].lower()


def test_toml_datetime_uses_number_color_distinct_from_string() -> None:
    line0 = 'name = "alice"'
    line1 = "born = 2023-01-15T10:00:00Z"
    source = f"{line0}\n{line1}\n"
    document, _ = _render("/tmp/sample.toml", source, is_dark=False)
    string_color = _color_at(document, 0, line0.index('"alice"'))
    datetime_color = _color_at(document, 1, line1.index("2023"))
    assert string_color == DEFAULT_LIGHT_PALETTE["string"].lower()
    assert datetime_color == DEFAULT_LIGHT_PALETTE["number"].lower()
    assert string_color != datetime_color


def test_jsonc_lexical_pass_colors_line_and_block_comments() -> None:
    line0 = "{ // top-level comment"
    line1 = '  "name": "alice", /* trailing */'
    line2 = '  "url": "http://example.com"'
    line3 = "}"
    source = "\n".join((line0, line1, line2, line3)) + "\n"
    document, _ = _render("/tmp/settings.jsonc", source, is_dark=False)
    expected_comment = DEFAULT_LIGHT_PALETTE["comment"].lower()
    assert _color_at(document, 0, line0.index("//")) == expected_comment
    assert _color_at(document, 1, line1.index("/*")) == expected_comment
    url_value_color = _color_at(document, 2, line2.index("http"))
    assert url_value_color != expected_comment


def test_html_tree_sitter_highlighter_styles_comments_and_entities() -> None:
    line0 = "<!-- top -->"
    line1 = "<p>hello&amp;world</p>"
    source = f"{line0}\n{line1}\n"
    document, _ = _render("/tmp/index.html", source, is_dark=False)
    assert _color_at(document, 0, line0.index("top")) == DEFAULT_LIGHT_PALETTE["comment"].lower()
    assert _color_at(document, 1, line1.index("&amp;")) == DEFAULT_LIGHT_PALETTE["escape"].lower()


def test_css_tree_sitter_highlighter_styles_pseudo_and_important() -> None:
    line0 = "a:hover { color: red !important; }"
    source = f"{line0}\n"
    document, _ = _render("/tmp/main.css", source, is_dark=False)
    assert _color_at(document, 0, line0.index("hover")) == DEFAULT_LIGHT_PALETTE["keyword_control"].lower()
    assert _color_at(document, 0, line0.index("!important")) == DEFAULT_LIGHT_PALETTE["keyword"].lower()


def test_xml_tree_sitter_highlighter_styles_cdata_text() -> None:
    line0 = "<root>"
    line1 = "<![CDATA[raw payload]]>"
    line2 = "</root>"
    source = f"{line0}\n{line1}\n{line2}\n"
    document, _ = _render("/tmp/doc.xml", source, is_dark=False)
    assert _color_at(document, 1, line1.index("raw")) == DEFAULT_LIGHT_PALETTE["string"].lower()


def test_markdown_tree_sitter_injects_fenced_python_code_blocks() -> None:
    source = "```python\nprint(1)\n```\n"
    document, highlighter = _render("/tmp/readme.md", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    assert _color_at(document, 1, 0) == DEFAULT_LIGHT_PALETTE["builtin"].lower()


def test_toml_tree_sitter_highlighter_formats_keys_and_literals() -> None:
    source = "[tool.demo]\nname = \"demo\"\nenabled = true\n"
    document, highlighter = _render("/tmp/pyproject.toml", source, is_dark=False)
    assert highlighter.__class__.__name__ == "TreeSitterHighlighter"
    assert _color_at(document, 0, source.splitlines()[0].index("tool")) == DEFAULT_LIGHT_PALETTE["json_key"].lower()
    assert _color_at(document, 1, 0) == DEFAULT_LIGHT_PALETTE["json_key"].lower()
    assert _color_at(document, 2, source.splitlines()[2].index("true")) == DEFAULT_LIGHT_PALETTE["json_literal"].lower()


def test_ini_fallback_highlighter_formats_desktop_entries() -> None:
    source = "[Desktop Entry]\nName=ChoreBoy Code Studio\nTerminal=false\n"
    document, highlighter = _render("/tmp/choreboy_code_studio.desktop", source, is_dark=False)
    assert highlighter.__class__.__name__ == "IniSyntaxHighlighter"
    assert _color_at(document, 0, 1) == DEFAULT_LIGHT_PALETTE["class"].lower()
    assert _color_at(document, 1, 0) == DEFAULT_LIGHT_PALETTE["json_key"].lower()
    assert _color_at(document, 2, source.splitlines()[2].index("false")) == DEFAULT_LIGHT_PALETTE["json_literal"].lower()


def test_python_invalid_locals_query_reports_diagnostic_without_losing_highlights() -> None:
    source = "def build(value):\n    return value\n"
    document = QTextDocument()
    resolved = default_tree_sitter_language_registry().resolve_for_path(
        file_path="/tmp/main.py",
        sample_text=source,
    )
    assert resolved is not None
    highlighter = TreeSitterHighlighter(
        document,
        resolved_language=replace(resolved, locals_query_source="("),
        is_dark=False,
    )
    document.setPlainText(source)
    highlighter.rehighlight()
    QApplication.processEvents()
    assert highlighter.query_diagnostics()
    assert _color_at(document, 0, 0) == DEFAULT_LIGHT_PALETTE["keyword"].lower()


def test_inserting_a_method_rehighlights_the_edit_not_the_file(tmp_path: Any, qapp: QApplication) -> None:
    """One inserted method is one buffer update, and only the edited lines are rehighlighted."""
    from types import SimpleNamespace

    from app.editors.editor_manager import EditorManager
    from app.shell.editor_tab_buffer_workflow import EditorTabBufferWorkflow

    lines = ["class SaleWindow:", "    def __init__(self):", "        return"]
    while len(lines) < 1000:
        lines.append("    def early_%d(self):" % len(lines))
        lines.append("        return %d" % len(lines))
    insert_at = len(lines)
    lines.append("    def marker_after(self):")
    lines.append("        return 1")
    while len(lines) < 2000:
        lines.append("    def later_%d(self):" % len(lines))
        lines.append("        return %d" % len(lines))
    source = "\n".join(lines) + "\n"
    path = tmp_path / "sale_window.py"
    path.write_text(source, encoding="utf-8")
    file_path = str(path.resolve())
    document, highlighter = _render(file_path, source)
    qapp.processEvents()
    blocks = {"n": 0}
    text_calls = {"n": 0}
    real_block = highlighter.rehighlightBlock

    def _count_block(block: Any) -> None:
        blocks["n"] += 1
        real_block(block)

    highlighter.rehighlightBlock = _count_block  # type: ignore[method-assign]
    manager = EditorManager()
    manager.open_file_with_content(file_path, source)
    host = SimpleNamespace(
        editor_tabs_widget=lambda: object(),
        local_history_schedule_autosave=lambda *_args: None,
        editor_auto_save=lambda: False,
        start_auto_save_to_file_timer=lambda: None,
        local_history_discard_pending_autosave=lambda *_args: None,
        local_history_delete_draft=lambda *_args: None,
        refresh_save_action_states=lambda: None,
        diagnostics_schedule_realtime_lint=lambda *_args: None,
        is_shutting_down=lambda: False,
        status_controller=lambda: None,
        editor_widgets_by_path=lambda: {},
    )
    worked = {"n": 0}

    def _advance(*_args: Any) -> None:
        worked["n"] += 1

    widget = SimpleNamespace(document=lambda: document, toPlainText=document.toPlainText)
    workflow = EditorTabBufferWorkflow(
        host=host,  # type: ignore[arg-type]
        editor_manager=manager,
        editor_tabs_coordinator=SimpleNamespace(
            advance_buffer_revision=_advance,
            refresh_tab_presentation=lambda *_args: None,
            promote_preview_tab=lambda *_args: False,
        ),
        outline_workflow=SimpleNamespace(schedule_refresh=lambda: None),
        markdown_workflow=SimpleNamespace(),
        tab_workflow=SimpleNamespace(),
    )
    real_text = workflow.handle_editor_text_changed

    def _count_text(changed_path: str, widget: Any) -> None:
        text_calls["n"] += 1
        real_text(changed_path, widget)

    document.contentsChanged.connect(lambda: _count_text(file_path, widget))
    method = "\n    def print_receipt(self):\n        return 1\n"
    cursor = QTextCursor(document.findBlockByNumber(insert_at))
    cursor.insertText(method)
    qapp.processEvents()
    after = source.splitlines()[insert_at]
    assert after.startswith("    def marker_after")
    marker_line = document.findBlockByNumber(insert_at + method.count("\n")).text()
    assert marker_line.startswith("    def marker_after"), marker_line
    assert _color_at(document, insert_at + method.count("\n"), 4) == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    assert worked["n"] == 1, (worked, text_calls, blocks)
    assert blocks["n"] < 40, (worked, text_calls, blocks)


def test_typing_ten_characters_rebuilds_locals_at_most_once(qapp: QApplication) -> None:
    from app.qt.QtTest import QTest

    source = "def build(value):\n    return value\n"
    document, highlighter = _render("/tmp/locals_type.py", source)
    rebuilds = {"n": 0}
    real = highlighter._refresh_local_tokens

    def _count() -> set[int]:
        rebuilds["n"] += 1
        return real()

    highlighter._refresh_local_tokens = _count  # type: ignore[method-assign]
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.End)
    for character in "abcdefghij":
        cursor.insertText(character)
    assert rebuilds["n"] <= 1, rebuilds
    QTest.qWait(200)
    qapp.processEvents()
    assert rebuilds["n"] == 1, rebuilds


def test_a_renamed_local_takes_its_color_after_idle(qapp: QApplication) -> None:
    from app.qt.QtTest import QTest

    source = "def build(value):\n    return value\n"
    document, _highlighter = _render("/tmp/locals_rename.py", source)
    assert _color_at(document, 0, 0) == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.Start)
    cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, len("def build("))
    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len("value"))
    cursor.insertText("total")
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.Start)
    cursor.movePosition(QTextCursor.Down)
    line = document.findBlockByNumber(1).text()
    column = line.index("value")
    cursor.setPosition(document.findBlockByNumber(1).position() + column)
    cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len("value"))
    cursor.insertText("total")
    assert _color_at(document, 0, 0) == DEFAULT_LIGHT_PALETTE["keyword"].lower()
    QTest.qWait(200)
    qapp.processEvents()
    renamed = document.findBlockByNumber(1).text()
    assert _color_at(document, 1, renamed.index("total")) == DEFAULT_LIGHT_PALETTE["semantic_parameter"].lower()


def _replace_in_line(document: QTextDocument, row: int, old: str, new: str) -> None:
    block = document.findBlockByNumber(row)
    column = block.text().index(old)
    cursor = QTextCursor(document)
    cursor.setPosition(block.position() + column)
    cursor.setPosition(block.position() + column + len(old), QTextCursor.KeepAnchor)
    cursor.insertText(new)


def test_one_edit_in_a_big_file_rebuilds_the_locals_of_one_statement(qapp: QApplication) -> None:
    from tests.form_builder.qtside.test_m6_2b_perf import _window_source

    source = _window_source()
    document, highlighter = _render("/tmp/locals_big.py", source)
    qapp.processEvents()
    lines = source.split("\n")
    def_row = lines.index("    def helper_40(self, value):")
    other_row = lines.index("    def helper_41(self, value):")
    variable = DEFAULT_LIGHT_PALETTE["semantic_variable"].lower()
    assert _color_at(document, def_row + 2, lines[def_row + 2].index("total")) == variable

    _replace_in_line(document, def_row + 1, "total", "result")
    qapp.processEvents()
    highlighter._cancel_local_rebuild()

    regions: list[tuple[int, int]] = []
    fulls = {"n": 0}
    queried: list[tuple[int, int]] = []
    repainted: list[tuple[int, int]] = []
    real_region = highlighter._rebuild_local_region
    real_full = highlighter._rebuild_local_tokens
    real_query = highlighter._query_capture_ranges
    real_window = highlighter._rehighlight_line_window

    def _region(**kwargs: Any) -> Any:
        regions.append((kwargs["region"].first, kwargs["region"].last))
        return real_region(**kwargs)

    def _full() -> None:
        fulls["n"] += 1
        real_full()

    def _query(line_ranges: list[tuple[int, int]]) -> Any:
        queried.extend(line_ranges)
        return real_query(line_ranges)

    def _window(start: int, end: int) -> None:
        repainted.append((start, end))
        real_window(start, end)

    highlighter._rebuild_local_region = _region  # type: ignore[method-assign]
    highlighter._rebuild_local_tokens = _full  # type: ignore[method-assign]
    highlighter._query_capture_ranges = _query  # type: ignore[method-assign]
    highlighter._rehighlight_line_window = _window  # type: ignore[method-assign]
    highlighter._apply_deferred_locals()

    scope = (def_row, def_row + 2)
    assert fulls["n"] == 0
    assert regions == [scope], regions
    assert queried and all(scope[0] <= a <= b <= scope[1] for a, b in queried), queried
    assert repainted and all(scope[0] <= a <= b <= scope[1] for a, b in repainted), repainted
    assert _color_at(document, def_row + 1, lines[def_row + 1].index("total")) == variable
    # The return line still says total. Nothing defines it now.
    assert _color_at(document, def_row + 2, lines[def_row + 2].index("total")) != variable
    assert _color_at(document, other_row + 2, lines[other_row + 2].index("total")) == variable


def test_a_renamed_local_in_one_method_leaves_the_other_methods_alone(qapp: QApplication) -> None:
    from app.qt.QtTest import QTest
    from tests.form_builder.qtside.test_m6_2b_perf import _window_source

    source = _window_source()
    document, _highlighter = _render("/tmp/locals_big_rename.py", source)
    qapp.processEvents()
    lines = source.split("\n")
    def_row = lines.index("    def helper_60(self, value):")
    other_row = lines.index("    def helper_61(self, value):")
    variable = DEFAULT_LIGHT_PALETTE["semantic_variable"].lower()
    parameter = DEFAULT_LIGHT_PALETTE["semantic_parameter"].lower()
    _replace_in_line(document, def_row + 1, "total", "result")
    _replace_in_line(document, def_row + 2, "total", "result")
    QTest.qWait(300)
    qapp.processEvents()
    assert _color_at(document, def_row + 1, document.findBlockByNumber(def_row + 1).text().index("result")) == variable
    assert _color_at(document, def_row + 2, document.findBlockByNumber(def_row + 2).text().index("result")) == variable
    assert _color_at(document, def_row + 1, document.findBlockByNumber(def_row + 1).text().index("value")) == parameter
    assert _color_at(document, other_row + 1, lines[other_row + 1].index("total")) == variable
    assert _color_at(document, other_row + 2, lines[other_row + 2].index("total")) == variable


def test_renaming_a_module_function_recolors_its_callers_elsewhere(qapp: QApplication) -> None:
    filler = "".join("def filler_%d(a):\n    return a\n\n\n" % index for index in range(60))
    source = "def helper():\n    return 1\n\n\n" + filler + "def use():\n    return helper\n"
    document, highlighter = _render("/tmp/locals_ripple.py", source)
    qapp.processEvents()
    lines = source.split("\n")
    call_row = lines.index("    return helper")
    function = DEFAULT_LIGHT_PALETTE["semantic_function"].lower()
    column = lines[call_row].index("helper")
    assert _color_at(document, call_row, column) == function
    _replace_in_line(document, 0, "helper", "helper2")
    qapp.processEvents()
    highlighter._cancel_local_rebuild()
    highlighter._apply_deferred_locals()
    assert _color_at(document, call_row, column) != function
    _replace_in_line(document, call_row, "helper", "helper2")
    highlighter._cancel_local_rebuild()
    highlighter._apply_deferred_locals()
    assert _color_at(document, call_row, column) == function


def test_incremental_locals_match_a_fresh_build_after_random_edits(qapp: QApplication) -> None:
    import random

    filler = "".join("def filler_%d(a):\n    return a\n\n\n" % index for index in range(50))
    source = (
        "import os\n\nLIMIT = 10\n\n\n"
        "class Base:\n    kind = 'base'\n\n    def describe(self, extra):\n        label = self.kind + extra\n"
        "        return [label for _ in range(LIMIT)]\n\n\n"
        "def top(value, *rest):\n    total = value + len(rest)\n    fn = lambda x: x + total\n    return fn(LIMIT)\n\n\n"
        + filler
    )

    def locals_of(highlighter: Any) -> dict[int, tuple[Any, ...]]:
        return {
            row: tuple(sorted((s.start_col, s.end_col, s.token_name) for s in spans))
            for row, spans in highlighter._locals_by_row.items()
            if spans
        }

    words = ["total", "value", "label", "x", "LIMIT", "self", "(", ")", "\n", "    ", "def ", "= 1"]
    compared = 0
    for seed in range(3):
        rnd = random.Random(seed)
        document, highlighter = _render("/tmp/locals_fuzz_%d.py" % seed, source)
        qapp.processEvents()
        for _step in range(18):
            for _edit in range(rnd.choice((1, 2))):
                text = document.toPlainText()
                cursor = QTextCursor(document)
                position = rnd.randrange(0, len(text) + 1)
                kind = rnd.choice(("insert", "delete", "newline"))
                cursor.setPosition(position)
                if kind == "insert":
                    cursor.insertText(rnd.choice(words))
                elif kind == "delete":
                    cursor.setPosition(min(len(text), position + rnd.randint(1, 5)), QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()
                else:
                    cursor.insertText("\n")
                qapp.processEvents()
            highlighter._cancel_local_rebuild()
            highlighter._apply_deferred_locals()
            _fresh_document, fresh = _render("/tmp/locals_fuzz_fresh.py", document.toPlainText())
            if str(highlighter._tree.root_node) != str(fresh._tree.root_node):
                continue  # An incremental parse may recover from an error differently.
            compared += 1
            assert locals_of(highlighter) == locals_of(fresh), (seed, _step)
    assert compared >= 20


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
