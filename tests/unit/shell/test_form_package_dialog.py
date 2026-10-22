"""Save the form now clears a packaging issue from the runtime center."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QPushButton, QWidget

from app.core.models import RuntimeIssue, RuntimeIssueReport
from app.shell.runtime_center_dialog import RuntimeCenterDialog
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit


class _Host(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def _form_builder_save_form(self, ui_path: str) -> bool:
        self.calls.append(ui_path)
        return True


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
    dialog = RuntimeCenterDialog(
        title="Packaging problems",
        report=report,
        tokens=tokens,
        presentation="packaging",
        parent=host,
    )
    button = next(
        candidate
        for candidate in dialog.findChildren(QPushButton)
        if candidate.text() == "Save the form now"
    )
    assert not button.isHidden()
    assert button.text() == "Save the form now"
    button.click()
    qapp.processEvents()
    assert host.calls == [ui_path]
    assert dialog.issue_list.count() == 0
