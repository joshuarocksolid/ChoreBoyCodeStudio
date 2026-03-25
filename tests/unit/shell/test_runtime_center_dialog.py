"""Unit tests for the Runtime Center dialog."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QTextBrowser

from app.core.models import RuntimeIssue, RuntimeIssueReport
from app.shell.runtime_center_dialog import RuntimeCenterDialog
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit


@pytest.fixture
def _ensure_qapp(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_runtime_center_dialog_updates_details_and_help_button(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    app = _ensure_qapp
    opened_topics: list[str] = []
    tokens = tokens_from_palette(app.palette(), force_mode="light")
    report = RuntimeIssueReport(
        workflow="runtime_center",
        issues=[
            RuntimeIssue(
                issue_id="runtime.apprun_missing",
                workflow="startup",
                severity="blocking",
                title="AppRun runtime is unavailable",
                summary="AppRun missing",
                why_it_happened="Missing runtime",
                next_steps=["Restore AppRun."],
                help_topic="getting_started",
                evidence={"check_id": "apprun_presence"},
            ),
            RuntimeIssue(
                issue_id="runtime.python_tooling_unavailable",
                workflow="startup",
                severity="advisory",
                title="Python tooling unavailable",
                summary="Python tooling missing",
                why_it_happened="Vendored tools missing",
            ),
        ],
    )

    dialog = RuntimeCenterDialog(
        title="Runtime Center",
        report=report,
        tokens=tokens,
        open_help_topic=opened_topics.append,
    )

    assert "1 blocking" in dialog.summary_label.text()
    assert dialog.issue_list.count() == 2
    assert dialog.help_button.isEnabled() is True
    detail_browser = dialog.findChild(QTextBrowser, "shell.runtimeCenterDialog.detailBrowser")
    assert detail_browser is not None
    assert "AppRun runtime is unavailable" in detail_browser.toPlainText()

    dialog.help_button.click()
    assert opened_topics == ["getting_started"]

    dialog.issue_list.setCurrentRow(1)
    app.processEvents()
    assert dialog.help_button.isEnabled() is False
    assert "Python tooling unavailable" in detail_browser.toPlainText()


def test_runtime_center_dialog_renders_clear_report(_ensure_qapp) -> None:  # type: ignore[no-untyped-def]
    app = _ensure_qapp
    tokens = tokens_from_palette(app.palette(), force_mode="dark")
    dialog = RuntimeCenterDialog(
        title="Runtime Center",
        report=RuntimeIssueReport(workflow="runtime_center", issues=[]),
        tokens=tokens,
    )

    assert dialog.help_button.isEnabled() is False
    assert "Runtime looks healthy" in dialog.summary_label.text()
