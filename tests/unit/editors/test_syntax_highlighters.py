"""Unit tests for syntax highlighter theme switching."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide2.QtGui", exc_type=ImportError)

from app.editors.syntax_python import PythonSyntaxHighlighter  # noqa: E402
from app.editors.syntax_python import _LIGHT_COLORS, _DARK_COLORS  # noqa: E402
from app.editors.syntax_json import JsonSyntaxHighlighter  # noqa: E402
from app.editors.syntax_json import _LIGHT_COLORS as JSON_LIGHT  # noqa: E402
from app.editors.syntax_json import _DARK_COLORS as JSON_DARK  # noqa: E402
from app.editors.syntax_markdown import MarkdownSyntaxHighlighter  # noqa: E402
from app.editors.syntax_markdown import _LIGHT_COLORS as MD_LIGHT  # noqa: E402
from app.editors.syntax_markdown import _DARK_COLORS as MD_DARK  # noqa: E402

pytestmark = pytest.mark.unit


def _mock_document() -> MagicMock:
    doc = MagicMock()
    doc.isEmpty.return_value = True
    doc.blockCount.return_value = 0
    doc.findBlockByNumber.return_value = MagicMock()
    return doc


class TestPythonSyntaxHighlighter:
    def test_starts_in_light_mode_by_default(self) -> None:
        h = PythonSyntaxHighlighter(_mock_document())
        assert h._is_dark is False
        assert len(h._rules) > 0

    def test_starts_in_dark_mode_when_requested(self) -> None:
        h = PythonSyntaxHighlighter(_mock_document(), is_dark=True)
        assert h._is_dark is True

    def test_set_dark_mode_rebuilds_rules(self) -> None:
        h = PythonSyntaxHighlighter(_mock_document(), is_dark=False)
        rules_before = list(h._rules)
        h.set_dark_mode(True)
        assert h._is_dark is True
        assert h._rules != rules_before

    def test_set_dark_mode_no_op_when_same(self) -> None:
        h = PythonSyntaxHighlighter(_mock_document(), is_dark=True)
        rules_before = list(h._rules)
        h.set_dark_mode(True)
        assert h._rules == rules_before

    def test_light_and_dark_color_tables_differ(self) -> None:
        assert _LIGHT_COLORS != _DARK_COLORS
        for key in _LIGHT_COLORS:
            assert key in _DARK_COLORS


class TestJsonSyntaxHighlighter:
    def test_starts_in_light_mode_by_default(self) -> None:
        h = JsonSyntaxHighlighter(_mock_document())
        assert h._is_dark is False

    def test_set_dark_mode_toggles(self) -> None:
        h = JsonSyntaxHighlighter(_mock_document())
        h.set_dark_mode(True)
        assert h._is_dark is True

    def test_light_and_dark_color_tables_differ(self) -> None:
        assert JSON_LIGHT != JSON_DARK


class TestMarkdownSyntaxHighlighter:
    def test_starts_in_light_mode_by_default(self) -> None:
        h = MarkdownSyntaxHighlighter(_mock_document())
        assert h._is_dark is False

    def test_set_dark_mode_toggles(self) -> None:
        h = MarkdownSyntaxHighlighter(_mock_document())
        h.set_dark_mode(True)
        assert h._is_dark is True

    def test_light_and_dark_color_tables_differ(self) -> None:
        assert MD_LIGHT != MD_DARK
