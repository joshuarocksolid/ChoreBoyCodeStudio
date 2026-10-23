"""Save the form now clears a packaging issue from the runtime center."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QPushButton, QTextBrowser, QWidget

from app.core.models import RuntimeIssue, RuntimeIssueReport
from app.shell.runtime_center_dialog import RuntimeCenterDialog
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit


class _Host(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self._latest_package_issue_report: RuntimeIssueReport | None = None
        self.message = ""

    def _form_builder_save_form(self, ui_path: str) -> str:
        self.calls.append(ui_path)
        return self.message


def test_save_the_form_now_drops_the_stale_issue(qapp) -> None:  # type: ignore[no-untyped-def]
    host = _Host()
    tokens = tokens_from_palette(qapp.palette(), force_mode="light")
    ui_path = "/tmp/project/forms/invoice.ui"
    report = RuntimeIssueReport(
        workflow="package",
        issues=[
            RuntimeIssue(
                issue_id="package.form.stale",
                workflow="package",
                severity="blocking",
                title="Generated form file is out of date",
                summary="ui_invoice.py is older than invoice.ui.",
                why_it_happened="The generated file does not match the form.",
                next_steps=["Save the form now"],
                evidence={
                    "ui_path": ui_path,
                    "fix_action": "save_form",
                    "fix_label": "Save the form now",
                    "source_file": "forms/invoice.ui",
                    "report_row": "ui_invoice.py is older than invoice.ui.",
                },
            )
        ],
    )
    host._latest_package_issue_report = report
    dialog = RuntimeCenterDialog(
        title="Packaging problems",
        report=report,
        tokens=tokens,
        presentation="packaging",
        parent=host,
    )
    button = dialog.findChild(QPushButton, "shell.runtimeCenterDialog.saveFormButton")
    assert button is not None
    assert not button.isHidden()
    assert button.text() == "Save the form now"
    button.click()
    qapp.processEvents()
    assert host.calls == [ui_path]
    assert dialog.issue_list.count() == 0
    assert host._latest_package_issue_report is not None
    assert host._latest_package_issue_report.issues == []


def test_save_failure_stays_in_the_detail(qapp) -> None:  # type: ignore[no-untyped-def]
    host = _Host()
    host.message = 'The class name "QLabel" can\'t be used in the generated Python.'
    tokens = tokens_from_palette(qapp.palette(), force_mode="light")
    report = RuntimeIssueReport(
        workflow="package",
        issues=[
            RuntimeIssue(
                issue_id="package.form.stale",
                workflow="package",
                severity="blocking",
                title="Generated form file is out of date",
                summary="ui_invoice.py is older than invoice.ui.",
                why_it_happened="The generated file does not match the form.",
                next_steps=["Save the form now"],
                evidence={
                    "ui_path": "/tmp/project/forms/invoice.ui",
                    "fix_action": "save_form",
                    "fix_label": "Save the form now",
                    "report_row": "ui_invoice.py is older than invoice.ui.",
                },
            )
        ],
    )
    dialog = RuntimeCenterDialog(
        title="Packaging problems",
        report=report,
        tokens=tokens,
        presentation="packaging",
        parent=host,
    )
    button = dialog.findChild(QPushButton, "shell.runtimeCenterDialog.saveFormButton")
    assert button is not None
    button.click()
    qapp.processEvents()
    browser = dialog.findChild(QTextBrowser, "shell.runtimeCenterDialog.detailBrowser")
    assert browser is not None
    assert "QLabel" in browser.toPlainText()
    assert dialog.issue_list.count() == 1


def test_save_button_is_hidden_when_no_saver_is_bound(qapp) -> None:  # type: ignore[no-untyped-def]
    tokens = tokens_from_palette(qapp.palette(), force_mode="light")
    report = RuntimeIssueReport(
        workflow="package",
        issues=[
            RuntimeIssue(
                issue_id="package.form.stale",
                workflow="package",
                severity="blocking",
                title="Generated form file is out of date",
                summary="ui_invoice.py is older than invoice.ui.",
                why_it_happened="The generated file does not match the form.",
                next_steps=["Save the form now"],
                evidence={
                    "ui_path": "/tmp/project/forms/invoice.ui",
                    "fix_action": "save_form",
                    "fix_label": "Save the form now",
                    "report_row": "ui_invoice.py is older than invoice.ui.",
                },
            )
        ],
    )
    parent = QWidget()
    dialog = RuntimeCenterDialog(
        title="Packaging problems",
        report=report,
        tokens=tokens,
        presentation="packaging",
        parent=parent,
    )
    button = dialog.findChild(QPushButton, "shell.runtimeCenterDialog.saveFormButton")
    assert button is not None
    assert button.isHidden()
