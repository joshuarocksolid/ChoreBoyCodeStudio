"""Unit tests for tree-sitter-backed syntax highlighters."""

from __future__ import annotations

import functools
from dataclasses import replace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextCharFormat, QTextCursor, QTextDocument  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.syntax_engine import DEFAULT_DARK_PALETTE, DEFAULT_LIGHT_PALETTE  # noqa: E402
from app.editors.syntax_registry import default_syntax_highlighter_registry  # noqa: E402
from app.treesitter.highlighter import TreeSitterHighlighter  # noqa: E402
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
