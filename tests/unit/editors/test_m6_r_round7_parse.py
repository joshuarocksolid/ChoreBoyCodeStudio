"""The first edit after an idle turn parses with the tree the tab open built."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtGui import QTextCursor, QTextDocument  # noqa: E402
from app.qt.QtWidgets import QApplication  # noqa: E402
from app.treesitter.highlighter_core import TreeSitterHighlighter  # noqa: E402
from app.treesitter.language_registry import default_tree_sitter_language_registry  # noqa: E402

pytestmark = pytest.mark.unit


def _source() -> str:
    lines = ["class Window:"]
    for index in range(1998):
        lines.append("    value_%d = %d" % (index, index))
    lines.append("")
    return "\n".join(lines)


def test_first_edit_after_idle_reuses_the_tree(qapp: QApplication) -> None:
    source = _source()
    resolved = default_tree_sitter_language_registry().resolve_for_path(
        file_path="/tmp/customer_window.py",
        sample_text=source,
    )
    if resolved is None:
        pytest.skip("tree-sitter python grammar is unavailable")
    document = QTextDocument()
    document.setPlainText(source)
    highlighter = TreeSitterHighlighter(document, resolved_language=resolved)
    qapp.processEvents()
    assert highlighter._tree is not None  # noqa: SLF001

    parses: list[bool] = []
    queried: list[list[tuple[int, int]]] = []
    real_parse = highlighter._parse_with_optional_tree
    real_query = highlighter._query_capture_ranges

    def wrapped_parse(old_tree: Any) -> Any:
        parses.append(old_tree is not None)
        return real_parse(old_tree)

    def wrapped_query(line_ranges: list[tuple[int, int]]) -> Any:
        queried.append(list(line_ranges))
        return real_query(line_ranges)

    highlighter._parse_with_optional_tree = wrapped_parse  # type: ignore[method-assign]
    highlighter._query_capture_ranges = wrapped_query  # type: ignore[method-assign]
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.End)
    cursor.insertText("\n    def probe_inserted(self):\n        return 1\n")
    assert parses == [True]
    assert queried
    for ranges in queried:
        for start, end in ranges:
            assert end - start < 40
