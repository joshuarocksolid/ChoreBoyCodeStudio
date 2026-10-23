"""Unit tests for the VS Code-style ProblemsPanel widget."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication  # noqa: E402

from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity  # noqa: E402
from app.run.problem_parser import ProblemEntry  # noqa: E402
from app.shell.problems_panel import ProblemsPanel, ResultItem  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def _ensure_qapp(qapp):  # type: ignore[no-untyped-def]
    yield qapp


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


_FORM_DETAIL = {"fb_key": "FB012|nameLabel|buddy|[]", "fb_object": "nameLabel", "fb_property": "buddy"}


def _make_form_row(location_label: str = "nameLabel") -> CodeDiagnostic:
    return CodeDiagnostic(
        code="FB012",
        severity=DiagnosticSeverity.WARNING,
        file_path="/project/invoice.ui",
        line_number=12,
        message="The buddy names a widget that is not on this form.",
        detail=_FORM_DETAIL,
        source="Form",
        location_label=location_label,
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


def test_item_activated_signal_emits_file_line_and_detail(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    panel.set_diagnostics([_make_form_row()])

    received: list[tuple[str, int, object]] = []
    panel.item_activated.connect(lambda fp, ln, detail: received.append((fp, ln, detail)))

    tree = panel.tree_widget()
    child = tree.topLevelItem(0).child(0)
    tree.itemActivated.emit(child, 0)

    assert received == [("/project/invoice.ui", 12, _FORM_DETAIL)]


def test_item_preview_signal_emits_file_line_and_detail_on_click(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    panel.set_diagnostics([_make_form_row()])

    received: list[tuple[str, int, object]] = []
    panel.item_preview_requested.connect(lambda fp, ln, detail: received.append((fp, ln, detail)))

    tree = panel.tree_widget()
    child = tree.topLevelItem(0).child(0)
    tree.itemClicked.emit(child, 0)

    assert received == [("/project/invoice.ui", 12, _FORM_DETAIL)]


@pytest.mark.parametrize(
    ("diagnostic", "location"),
    [
        (_make_diagnostic(line_number=10), "Ln 10"),
        (_make_form_row(), "nameLabel"),
        (_make_form_row(location_label=""), "Ln 12"),
    ],
)
def test_location_column_names_the_widget_or_the_line(  # type: ignore[no-untyped-def]
    _ensure_qapp, diagnostic: CodeDiagnostic, location: str
) -> None:
    panel = ProblemsPanel()
    panel.set_diagnostics([diagnostic])

    assert panel.tree_widget().topLevelItem(0).child(0).text(2) == location


@pytest.mark.parametrize(
    ("diagnostic", "code"),
    [
        (_make_diagnostic(code="PY200"), "PY200"),
        (_make_form_row(), "Form FB012"),
    ],
)
def test_code_column_shows_the_source_before_the_code(  # type: ignore[no-untyped-def]
    _ensure_qapp, diagnostic: CodeDiagnostic, code: str
) -> None:
    panel = ProblemsPanel()
    panel.set_diagnostics([diagnostic])

    assert panel.tree_widget().topLevelItem(0).child(0).text(3) == code


def test_problem_count_reflects_total_across_severities(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    panel = ProblemsPanel()
    diagnostics = [
        _make_diagnostic(severity=DiagnosticSeverity.ERROR),
        _make_diagnostic(severity=DiagnosticSeverity.WARNING, code="PY210"),
        _make_diagnostic(severity=DiagnosticSeverity.INFO, code="PY230"),
    ]
    panel.set_diagnostics(diagnostics)

    assert panel.problem_count() == 3
