"""Unit tests for syntax highlighters (quality + theme behavior)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextDocument  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.syntax_json import JsonSyntaxHighlighter  # noqa: E402
from app.editors.syntax_json import _DARK_COLORS as JSON_DARK  # noqa: E402
from app.editors.syntax_json import _LIGHT_COLORS as JSON_LIGHT  # noqa: E402
from app.editors.syntax_markdown import MarkdownSyntaxHighlighter  # noqa: E402
from app.editors.syntax_markdown import _DARK_COLORS as MD_DARK  # noqa: E402
from app.editors.syntax_markdown import _LIGHT_COLORS as MD_LIGHT  # noqa: E402
from app.editors.syntax_python import PythonSyntaxHighlighter  # noqa: E402
from app.editors.syntax_python import _DARK_COLORS, _LIGHT_COLORS  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _render(highlighter_cls, text: str, *, is_dark: bool = False):  # type: ignore[no-untyped-def]
    document = QTextDocument()
    highlighter = highlighter_cls(document, is_dark=is_dark)
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


class TestPythonSyntaxHighlighter:
    def test_triple_quoted_strings_preserve_multiline_state(self) -> None:
        source = 'value = """line one\nline two\nline three"""\n'
        document, _ = _render(PythonSyntaxHighlighter, source, is_dark=False)
        line_two_color = _color_at(document, 1, 2)
        assert line_two_color == _LIGHT_COLORS["string"].lower()

    def test_comment_markers_inside_strings_do_not_become_comments(self) -> None:
        source = 'value = "# not comment"\n'
        document, _ = _render(PythonSyntaxHighlighter, source, is_dark=False)
        hash_color = _color_at(document, 0, source.index("#"))
        assert hash_color == _LIGHT_COLORS["string"].lower()

    def test_decorator_function_class_and_parameters_have_distinct_tokens(self) -> None:
        source = "@cached_property\ndef build_value(count, flag=False):\nclass Demo:\n"
        document, _ = _render(PythonSyntaxHighlighter, source, is_dark=False)
        decorator_color = _color_at(document, 0, 0)
        function_color = _color_at(document, 1, source.splitlines()[1].index("build_value"))
        parameter_color = _color_at(document, 1, source.splitlines()[1].index("count"))
        class_color = _color_at(document, 2, source.splitlines()[2].index("Demo"))
        assert decorator_color == _LIGHT_COLORS["decorator"].lower()
        assert function_color == _LIGHT_COLORS["function"].lower()
        assert parameter_color == _LIGHT_COLORS["parameter"].lower()
        assert class_color == _LIGHT_COLORS["class"].lower()

    def test_number_variants_are_highlighted(self) -> None:
        source = "a=0xFF\nb=0b1010\nc=12_000\nd=6.02e23\n"
        document, _ = _render(PythonSyntaxHighlighter, source, is_dark=False)
        assert _color_at(document, 0, source.splitlines()[0].index("0")) == _LIGHT_COLORS["number"].lower()
        assert _color_at(document, 1, source.splitlines()[1].index("0")) == _LIGHT_COLORS["number"].lower()
        assert _color_at(document, 2, source.splitlines()[2].index("1")) == _LIGHT_COLORS["number"].lower()
        assert _color_at(document, 3, source.splitlines()[3].index("6")) == _LIGHT_COLORS["number"].lower()

    def test_set_dark_mode_rebuilds_palette(self) -> None:
        document = QTextDocument()
        highlighter = PythonSyntaxHighlighter(document, is_dark=False)
        before = dict(highlighter._palette)
        highlighter.set_dark_mode(True)
        after = dict(highlighter._palette)
        assert before != after
        assert highlighter._is_dark is True

    def test_light_and_dark_color_tables_differ(self) -> None:
        assert _LIGHT_COLORS != _DARK_COLORS
        for key in _LIGHT_COLORS:
            assert key in _DARK_COLORS


class TestJsonSyntaxHighlighter:
    def test_json_keys_remain_distinct_from_value_strings(self) -> None:
        source = '{"name": "alice", "enabled": true}\n'
        document, _ = _render(JsonSyntaxHighlighter, source, is_dark=False)
        key_color = _color_at(document, 0, source.index("name"))
        value_color = _color_at(document, 0, source.index("alice"))
        literal_color = _color_at(document, 0, source.index("true"))
        assert key_color == JSON_LIGHT["json_key"].lower()
        assert value_color == JSON_LIGHT["string"].lower()
        assert literal_color == JSON_LIGHT["json_literal"].lower()

    def test_escaped_quotes_inside_json_string_stay_in_string_span(self) -> None:
        source = '{"message": "hello \\"world\\""}\n'
        document, _ = _render(JsonSyntaxHighlighter, source, is_dark=False)
        quote_color = _color_at(document, 0, source.index('\\"'))
        assert quote_color == JSON_LIGHT["string"].lower()

    def test_light_and_dark_color_tables_differ(self) -> None:
        assert JSON_LIGHT != JSON_DARK


class TestMarkdownSyntaxHighlighter:
    def test_fenced_code_blocks_preserve_state_across_lines(self) -> None:
        source = "```python\nx = 1\n```\n"
        document, _ = _render(MarkdownSyntaxHighlighter, source, is_dark=False)
        code_color = _color_at(document, 1, 0)
        assert code_color == MD_LIGHT["markdown_code"].lower()

    def test_heading_emphasis_and_inline_code_tokens(self) -> None:
        source = "# Title with **bold** and `code`\n"
        document, _ = _render(MarkdownSyntaxHighlighter, source, is_dark=False)
        heading_color = _color_at(document, 0, 0)
        emphasis_color = _color_at(document, 0, source.index("bold"))
        code_color = _color_at(document, 0, source.index("code"))
        assert heading_color == MD_LIGHT["markdown_heading"].lower()
        assert emphasis_color == MD_LIGHT["markdown_emphasis"].lower()
        assert code_color == MD_LIGHT["markdown_code"].lower()

    def test_light_and_dark_color_tables_differ(self) -> None:
        assert MD_LIGHT != MD_DARK
