"""Integration performance checks for editor syntax highlighting."""

from __future__ import annotations

import math
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QPalette, QTextDocument, QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.editors.syntax_registry import default_syntax_highlighter_registry  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from app.treesitter.loader import initialize_tree_sitter_runtime  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.performance, pytest.mark.timeout(180)]
_TREE_SITTER_AVAILABLE = initialize_tree_sitter_runtime().is_available


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


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


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    rank = int(math.ceil(0.95 * len(ordered))) - 1
    rank = min(len(ordered) - 1, max(0, rank))
    return ordered[rank]


def _create_python_highlighter(document: QTextDocument) -> object:
    if not _TREE_SITTER_AVAILABLE:
        pytest.skip("Tree-sitter runtime unavailable in this environment.")
    registry = default_syntax_highlighter_registry()
    highlighter = registry.create_for_path(
        file_path="/tmp/main.py",
        document=document,
        is_dark=False,
        sample_text="def run():\n    return 1\n",
    )
    assert highlighter is not None
    return highlighter


def _dispose_highlighter(highlighter: object) -> None:
    set_document = getattr(highlighter, "setDocument", None)
    if callable(set_document):
        set_document(None)
    QApplication.processEvents()


def test_python_rehighlight_2000_loc_under_250ms() -> None:
    source = _large_python_source(2000)
    document = QTextDocument()
    highlighter = _create_python_highlighter(document)
    document.setPlainText(source)
    try:
        start = time.perf_counter()
        highlighter.rehighlight()
        elapsed = time.perf_counter() - start
    finally:
        _dispose_highlighter(highlighter)

    assert elapsed <= 0.25


def test_python_rehighlight_2000_loc_p95_under_300ms() -> None:
    source = _large_python_source(2000)
    samples: list[float] = []
    for _ in range(10):
        document = QTextDocument()
        highlighter = _create_python_highlighter(document)
        document.setPlainText(source)
        try:
            start = time.perf_counter()
            highlighter.rehighlight()
            samples.append((time.perf_counter() - start) * 1000.0)
        finally:
            _dispose_highlighter(highlighter)
    assert _p95(samples) <= 300.0


def test_tree_sitter_rehighlight_typing_burst_p95_under_140ms() -> None:
    source = _large_python_source(2000)
    document = QTextDocument()
    highlighter = _create_python_highlighter(document)
    document.setPlainText(source)
    try:
        highlighter.rehighlight()
        samples: list[float] = []
        for iteration in range(18):
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(f"# edit {iteration}\n")
            start = time.perf_counter()
            highlighter.rehighlight()
            samples.append((time.perf_counter() - start) * 1000.0)
    finally:
        _dispose_highlighter(highlighter)
    assert _p95(samples) <= 140.0


def test_theme_apply_10_open_editors_p95_under_150ms_per_editor() -> None:
    tokens = tokens_from_palette(QPalette(), force_mode="dark")
    samples: list[float] = []
    for _ in range(6):
        editors = [CodeEditorWidget() for _ in range(10)]
        try:
            for editor in editors:
                editor.setPlainText(_large_python_source(600))
                editor.set_language_for_path("/tmp/test.py")
            start = time.perf_counter()
            for editor in editors:
                editor.apply_theme(tokens)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            samples.append(elapsed_ms / len(editors))
        finally:
            for editor in editors:
                editor.deleteLater()
            QApplication.processEvents()
    assert _p95(samples) <= 150.0


