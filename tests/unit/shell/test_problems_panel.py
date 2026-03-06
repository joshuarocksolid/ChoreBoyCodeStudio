"""Unit tests for the VS Code-style ProblemsPanel widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication  # noqa: E402

from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity  # noqa: E402
from app.run.problem_parser import ProblemEntry  # noqa: E402
from app.shell.problems_panel import ProblemsPanel, ResultItem  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_diagnostic(
    file_path: str = "/project/module.py",
    line_number: int = 10,
    message: str = "Unresolved import: foo",
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
    code: str = "PY200",
) -> CodeDiagnostic:
    return CodeDiagnostic(
        code=code,
        severity=severity,
        file_path=file_path,
        line_number=line_number,
        message=message,
    )


def _make_runtime_problem(
    file_path: str = "/project/run.py",
    line_number: int = 5,
    message: str = "RuntimeError: boom",
    context: str = "<module>",
) -> ProblemEntry:
    return ProblemEntry(
        file_path=file_path,
        line_number=line_number,
        message=message,
        context=context,
    )


def test_set_diagnostics_groups_by_file(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    diagnostics = [
        _make_diagnostic(file_path="/project/a.py", line_number=1, message="err a1"),
        _make_diagnostic(file_path="/project/a.py", line_number=5, message="err a2"),
        _make_diagnostic(file_path="/project/b.py", line_number=2, message="err b1"),
    ]
    panel.set_diagnostics(diagnostics)

    tree = panel.tree_widget()
    assert tree.topLevelItemCount() == 2

    group_a = tree.topLevelItem(0)
    assert "a.py" in group_a.text(1)
    assert group_a.childCount() == 2

    group_b = tree.topLevelItem(1)
    assert "b.py" in group_b.text(1)
    assert group_b.childCount() == 1


def test_set_diagnostics_includes_runtime_problems(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    lint_diags = [_make_diagnostic(file_path="/project/a.py")]
    runtime = [_make_runtime_problem(file_path="/project/a.py")]
    panel.set_diagnostics(lint_diags, runtime)

    tree = panel.tree_widget()
    assert tree.topLevelItemCount() == 1
    group = tree.topLevelItem(0)
    assert group.childCount() == 2
    assert panel.problem_count() == 2


def test_severity_filter_hides_errors(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    diagnostics = [
        _make_diagnostic(severity=DiagnosticSeverity.ERROR, message="err"),
        _make_diagnostic(severity=DiagnosticSeverity.WARNING, message="warn", code="PY210"),
    ]
    panel.set_diagnostics(diagnostics)

    tree = panel.tree_widget()
    initial_children = tree.topLevelItem(0).childCount()
    assert initial_children == 2

    panel._error_toggle.setChecked(False)

    assert tree.topLevelItem(0).childCount() == 1
    child = tree.topLevelItem(0).child(0)
    assert "warn" in child.text(1)


def test_severity_filter_hides_warnings(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    diagnostics = [
        _make_diagnostic(severity=DiagnosticSeverity.ERROR, message="err"),
        _make_diagnostic(severity=DiagnosticSeverity.WARNING, message="warn", code="PY210"),
    ]
    panel.set_diagnostics(diagnostics)

    panel._warning_toggle.setChecked(False)

    tree = panel.tree_widget()
    assert tree.topLevelItem(0).childCount() == 1
    child = tree.topLevelItem(0).child(0)
    assert "err" in child.text(1)


def test_empty_state_shown_when_no_diagnostics(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    panel.set_diagnostics([])

    assert panel.problem_count() == 0
    assert panel._stack_layout.currentWidget() == panel._empty_label


def test_empty_state_shown_after_clear(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    panel.set_diagnostics([_make_diagnostic()])
    assert panel.problem_count() == 1

    panel.clear()
    assert panel.problem_count() == 0
    assert panel._stack_layout.currentWidget() == panel._empty_label


def test_set_results_groups_by_file(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    items = [
        ResultItem(label="[def] foo", file_path="/project/a.py", line_number=1),
        ResultItem(label="[ref] foo", file_path="/project/a.py", line_number=10),
        ResultItem(label="[ref] foo", file_path="/project/b.py", line_number=5),
    ]
    panel.set_results("References: foo", items)

    tree = panel.tree_widget()
    assert tree.topLevelItemCount() == 2
    assert panel.problem_count() == 3
    assert panel._source_label.text() == "References: foo"


def test_set_results_empty_shows_empty_state(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    panel.set_results("Outline", [])

    assert panel.problem_count() == 0
    assert panel._stack_layout.currentWidget() == panel._empty_label


def test_item_activated_signal_emits_file_and_line(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    diagnostics = [_make_diagnostic(file_path="/project/mod.py", line_number=42)]
    panel.set_diagnostics(diagnostics)

    received: list[tuple[str, int]] = []
    panel.item_activated.connect(lambda fp, ln: received.append((fp, ln)))

    tree = panel.tree_widget()
    group = tree.topLevelItem(0)
    child = group.child(0)
    tree.itemActivated.emit(child, 0)

    assert len(received) == 1
    assert received[0] == ("/project/mod.py", 42)


def test_item_preview_signal_emits_file_and_line_on_click(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    diagnostics = [_make_diagnostic(file_path="/project/mod.py", line_number=7)]
    panel.set_diagnostics(diagnostics)

    received: list[tuple[str, int]] = []
    panel.item_preview_requested.connect(lambda fp, ln: received.append((fp, ln)))

    tree = panel.tree_widget()
    group = tree.topLevelItem(0)
    child = group.child(0)
    tree.itemClicked.emit(child, 0)

    assert received == [("/project/mod.py", 7)]


def test_problem_count_reflects_total_across_severities(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    diagnostics = [
        _make_diagnostic(severity=DiagnosticSeverity.ERROR),
        _make_diagnostic(severity=DiagnosticSeverity.WARNING, code="PY210"),
        _make_diagnostic(severity=DiagnosticSeverity.INFO, code="PY230"),
    ]
    panel.set_diagnostics(diagnostics)

    assert panel.problem_count() == 3
