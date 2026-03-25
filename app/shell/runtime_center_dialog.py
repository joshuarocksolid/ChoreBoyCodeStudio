"""Structured runtime/onboarding drill-down dialog."""
from __future__ import annotations

from html import escape
from typing import Callable

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.core.models import RuntimeIssue, RuntimeIssueReport
from app.shell.theme_tokens import ShellThemeTokens

_SEVERITY_LABELS = {
    "blocking": "Blocking",
    "degraded": "Degraded",
    "advisory": "Advisory",
    "clear": "Clear",
}


class RuntimeCenterDialog(QDialog):
    """Drill-down surface for startup/runtime/project explanation."""

    def __init__(
        self,
        *,
        title: str,
        report: RuntimeIssueReport,
        tokens: ShellThemeTokens,
        open_help_topic: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._open_help_topic = open_help_topic
        self._report = report
        self._issues_by_row: list[RuntimeIssue] = []

        self.setWindowTitle(title)
        self.setObjectName("shell.runtimeCenterDialog")
        self.setMinimumSize(680, 460)
        self.resize(880, 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("shell.runtimeCenterDialog.header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 12)
        header_layout.setSpacing(6)

        self._title_label = QLabel(title, header)
        self._title_label.setObjectName("shell.runtimeCenterDialog.title")
        header_layout.addWidget(self._title_label)

        self._summary_label = QLabel(header)
        self._summary_label.setObjectName("shell.runtimeCenterDialog.summary")
        self._summary_label.setWordWrap(True)
        header_layout.addWidget(self._summary_label)

        outer.addWidget(header)

        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(18, 14, 18, 10)
        body_layout.setSpacing(12)

        self._issue_list = QListWidget(body)
        self._issue_list.setObjectName("shell.runtimeCenterDialog.issueList")
        self._issue_list.setMinimumWidth(290)
        self._issue_list.setAlternatingRowColors(True)
        self._issue_list.currentRowChanged.connect(self._handle_issue_selection_changed)
        body_layout.addWidget(self._issue_list, 0)

        self._detail_browser = QTextBrowser(body)
        self._detail_browser.setObjectName("shell.runtimeCenterDialog.detailBrowser")
        self._detail_browser.setOpenExternalLinks(True)
        body_layout.addWidget(self._detail_browser, 1)

        outer.addWidget(body, 1)

        footer = QWidget(self)
        footer.setObjectName("shell.runtimeCenterDialog.footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 10, 18, 14)
        footer_layout.setSpacing(8)

        self._help_button = QPushButton("Open Related Help", footer)
        self._help_button.setObjectName("shell.runtimeCenterDialog.helpButton")
        self._help_button.clicked.connect(self._handle_open_help)
        footer_layout.addWidget(self._help_button, 0, Qt.AlignLeft)
        footer_layout.addStretch(1)

        close_button = QPushButton("Close", footer)
        close_button.setObjectName("shell.runtimeCenterDialog.closeButton")
        close_button.clicked.connect(self.accept)
        close_button.setDefault(True)
        footer_layout.addWidget(close_button)

        outer.addWidget(footer)
        self.set_report(report)

    def set_report(self, report: RuntimeIssueReport) -> None:
        """Refresh the dialog from a new report payload."""
        self._report = report
        self._issue_list.clear()
        self._issues_by_row = list(report.issues)
        self._summary_label.setText(_summarize_report(report))

        if not report.issues:
            self._detail_browser.setHtml(_render_clear_html(self._tokens))
            self._help_button.setEnabled(False)
            return

        for issue in report.issues:
            item = QListWidgetItem(
                f"{_SEVERITY_LABELS.get(issue.severity, issue.severity.title())} | {issue.title}"
            )
            item.setToolTip(issue.summary)
            self._issue_list.addItem(item)
        self._issue_list.setCurrentRow(0)

    @property
    def help_button(self) -> QPushButton:
        return self._help_button

    @property
    def issue_list(self) -> QListWidget:
        return self._issue_list

    @property
    def summary_label(self) -> QLabel:
        return self._summary_label

    def _handle_issue_selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._issues_by_row):
            self._detail_browser.setHtml(_render_clear_html(self._tokens))
            self._help_button.setEnabled(False)
            return
        issue = self._issues_by_row[row]
        self._detail_browser.setHtml(_render_issue_html(issue, self._tokens))
        self._help_button.setEnabled(bool(issue.help_topic and self._open_help_topic))

    def _handle_open_help(self) -> None:
        row = self._issue_list.currentRow()
        if row < 0 or row >= len(self._issues_by_row):
            return
        issue = self._issues_by_row[row]
        if not issue.help_topic or self._open_help_topic is None:
            return
        self._open_help_topic(issue.help_topic)


def _summarize_report(report: RuntimeIssueReport) -> str:
    if report.is_clear:
        return "Runtime looks healthy. No structured issues are currently active."
    parts: list[str] = []
    if report.blocking_count:
        parts.append(f"{report.blocking_count} blocking")
    if report.degraded_count:
        parts.append(f"{report.degraded_count} degraded")
    if report.advisory_count:
        parts.append(f"{report.advisory_count} advisory")
    joined = ", ".join(parts)
    return f"{joined}. Select an item on the left for explanation and next steps."


def _severity_color(severity: str, tokens: ShellThemeTokens) -> str:
    if severity == "blocking":
        return tokens.diag_error_color or tokens.accent
    if severity == "degraded":
        return tokens.diag_warning_color or tokens.accent
    if severity == "advisory":
        return tokens.diag_info_color or tokens.accent
    return tokens.text_muted


def _render_issue_html(issue: RuntimeIssue, tokens: ShellThemeTokens) -> str:
    next_steps_html = "".join(f"<li>{escape(step)}</li>" for step in issue.next_steps)
    evidence_items = "".join(
        f"<li><code>{escape(str(key))}</code>: {escape(str(value))}</li>"
        for key, value in sorted(issue.evidence.items(), key=lambda item: str(item[0]))
    )
    badge = _SEVERITY_LABELS.get(issue.severity, issue.severity.title())
    badge_color = _severity_color(issue.severity, tokens)
    return (
        f'<div style="font-family:sans-serif;color:{tokens.text_primary};font-size:13px;">'
        f'<div style="display:inline-block;background:{tokens.badge_bg};color:{badge_color};'
        'padding:4px 8px;border-radius:10px;font-weight:600;margin-bottom:10px;">'
        f"{escape(badge)}</div>"
        f"<h2 style=\"margin:0 0 8px 0;\">{escape(issue.title)}</h2>"
        f"<p style=\"margin:0 0 10px 0;line-height:1.5;\">{escape(issue.summary)}</p>"
        "<h3 style=\"margin:10px 0 4px 0;\">Why it happened</h3>"
        f"<p style=\"margin:0 0 10px 0;line-height:1.5;\">{escape(issue.why_it_happened)}</p>"
        "<h3 style=\"margin:10px 0 4px 0;\">Next steps</h3>"
        f"<ul style=\"margin:4px 0 10px 18px;\">{next_steps_html or '<li>No follow-up steps were provided.</li>'}</ul>"
        "<h3 style=\"margin:10px 0 4px 0;\">Evidence</h3>"
        f"<ul style=\"margin:4px 0 10px 18px;\">{evidence_items or '<li>No structured evidence was recorded.</li>'}</ul>"
        f"<p style=\"margin:10px 0 0 0;color:{tokens.text_muted};\">"
        f"Workflow: <code>{escape(issue.workflow)}</code>"
        + (
            f" | Help topic: <code>{escape(issue.help_topic)}</code>"
            if issue.help_topic
            else ""
        )
        + "</p>"
        "</div>"
    )


def _render_clear_html(tokens: ShellThemeTokens) -> str:
    return (
        f'<div style="font-family:sans-serif;color:{tokens.text_primary};font-size:13px;">'
        "<h2 style=\"margin:0 0 8px 0;\">No active runtime issues</h2>"
        "<p style=\"line-height:1.5;\">"
        "The currently loaded report did not contain blocking, degraded, or advisory issues."
        "</p>"
        f'<p style="color:{tokens.text_muted};line-height:1.5;">'
        "If you expected project-specific checks, run Project Health Check to gather them."
        "</p>"
        "</div>"
    )
