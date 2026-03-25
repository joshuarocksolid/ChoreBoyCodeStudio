"""Integration performance checks for editor syntax highlighting."""

from __future__ import annotations

import math
import time

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtGui import QPalette, QTextDocument, QTextCursor  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.core import constants  # noqa: E402
from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity  # noqa: E402
from app.editors.syntax_python import PythonSyntaxHighlighter  # noqa: E402
from app.intelligence.semantic_tokens import SemanticTokenSpan, build_python_semantic_spans  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

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


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    rank = int(math.ceil(0.95 * len(ordered))) - 1
    rank = min(len(ordered) - 1, max(0, rank))
    return ordered[rank]


def test_python_rehighlight_2000_loc_under_250ms() -> None:
    source = _large_python_source(2000)
    document = QTextDocument()
    highlighter = PythonSyntaxHighlighter(document, is_dark=False)
    document.setPlainText(source)

    start = time.perf_counter()
    highlighter.rehighlight()
    elapsed = time.perf_counter() - start

    assert elapsed <= 0.25


def test_python_rehighlight_2000_loc_p95_under_300ms() -> None:
    source = _large_python_source(2000)
    samples: list[float] = []
    for _ in range(10):
        document = QTextDocument()
        highlighter = PythonSyntaxHighlighter(document, is_dark=False)
        document.setPlainText(source)
        start = time.perf_counter()
        highlighter.rehighlight()
        samples.append((time.perf_counter() - start) * 1000.0)
    assert _p95(samples) <= 300.0


def test_semantic_span_extraction_2000_loc_p95_under_120ms() -> None:
    source = _large_python_source(2000)
    samples: list[float] = []
    for _ in range(12):
        start = time.perf_counter()
        spans = build_python_semantic_spans(source)
        samples.append((time.perf_counter() - start) * 1000.0)
        assert spans
    assert _p95(samples) <= 120.0


def test_semantic_refresh_typing_burst_p95_under_140ms() -> None:
    base_source = _large_python_source(2000)
    samples: list[float] = []
    for iteration in range(18):
        source = base_source + f"# edit {iteration}\n"
        start = time.perf_counter()
        spans = build_python_semantic_spans(source)
        samples.append((time.perf_counter() - start) * 1000.0)
        assert spans
    assert _p95(samples) <= 140.0


def test_theme_apply_10_open_editors_p95_under_150ms_per_editor() -> None:
    tokens = tokens_from_palette(QPalette(), force_mode="dark")
    samples: list[float] = []
    for _ in range(6):
        editors = [CodeEditorWidget() for _ in range(10)]
        for editor in editors:
            editor.setPlainText(_large_python_source(600))
            editor.set_language_for_path("/tmp/test.py")
        start = time.perf_counter()
        for editor in editors:
            editor.apply_theme(tokens)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        samples.append(elapsed_ms / len(editors))
    assert _p95(samples) <= 150.0


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


def test_large_file_adaptive_mode_limits_overlay_volume() -> None:
    editor = CodeEditorWidget()
    editor.set_highlighting_policy(
        adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
        reduced_threshold_chars=100_000,
        lexical_only_threshold_chars=170_000,
    )
    editor.setPlainText("value = 1\n" * 30_000)
    assert editor._effective_highlighting_mode() in {
        constants.HIGHLIGHTING_MODE_REDUCED,
        constants.HIGHLIGHTING_MODE_LEXICAL_ONLY,
    }
    editor.set_semantic_token_spans([SemanticTokenSpan(start=0, end=5, token_type="function")])
    assert editor._semantic_selections == []
    diagnostics = [
        CodeDiagnostic(
            code="W001",
            severity=DiagnosticSeverity.WARNING,
            file_path="/tmp/main.py",
            line_number=index + 1,
            message="warning",
        )
        for index in range(3_000)
    ]
    editor.set_diagnostics(diagnostics)
    assert len(editor.extraSelections()) <= 701
