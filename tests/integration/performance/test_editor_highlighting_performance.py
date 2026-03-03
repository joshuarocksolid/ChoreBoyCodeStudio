"""Integration performance checks for editor syntax highlighting."""

from __future__ import annotations

import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QTextDocument, QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.editors.syntax_python import PythonSyntaxHighlighter  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _large_python_source(line_count: int = 2000) -> str:
    lines = [
        "from math import sqrt",
        "class Demo:",
        "    def __init__(self, value):",
        "        self.value = value",
        "    def compute(self):",
        "        return sqrt(self.value) if self.value > 0 else 0",
        "",
    ]
    for index in range(max(0, line_count - len(lines))):
        lines.append(f"value_{index} = {index} + 1  # generated line")
    return "\n".join(lines) + "\n"


def test_python_rehighlight_2000_loc_under_250ms() -> None:
    source = _large_python_source(2000)
    document = QTextDocument()
    highlighter = PythonSyntaxHighlighter(document, is_dark=False)
    document.setPlainText(source)

    start = time.perf_counter()
    highlighter.rehighlight()
    elapsed = time.perf_counter() - start

    assert elapsed <= 0.25


def test_large_document_bracket_match_path_is_bounded() -> None:
    editor = CodeEditorWidget()
    source = "(\n" + ("value = 1\n" * 30_000) + ")\n"
    editor.setPlainText(source)
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)

    start = time.perf_counter()
    selections = editor._build_bracket_match_selections()
    elapsed = time.perf_counter() - start

    assert selections == []
    assert elapsed <= 0.02
