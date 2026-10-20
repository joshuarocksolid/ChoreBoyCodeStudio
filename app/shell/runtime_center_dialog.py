"""Structured runtime/onboarding drill-down dialog."""
from __future__ import annotations

from html import escape
import re
from typing import Callable

from PySide2.QtCore import QPoint, Qt, QTimer
from PySide2.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide2.QtWidgets import (
    QApplication,
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
from app.shell.unsaved_changes_dialog import _warning_icon

_SEVERITY_LABELS = {
    "blocking": "Blocking",
    "degraded": "Degraded",
    "advisory": "Advisory",
    "clear": "Clear",
}

_PACKAGING_SEVERITY_LABELS = {
    "blocking": "Stops export",
    "degraded": "Warning: export continues",
    "advisory": "Warning: export continues",
}

_PACKAGING_BADGES = {
    "blocking": "Stops export",
    "degraded": "Warning",
    "advisory": "Warning",
}

PACKAGING_HELP_TEXT = "Click Copy Details and post them to the LibrePy group."
APPRUN_NOTE = "Calls to /opt/freecad/AppRun are allowed and are not listed."


class RuntimeCenterDialog(QDialog):
    """Drill-down surface for startup/runtime/project explanation."""

    def __init__(
        self,
        *,
        title: str,
        report: RuntimeIssueReport,
        tokens: ShellThemeTokens,
        open_help_topic: Callable[[str], None] | None = None,
        open_location: Callable[[str, int], None] | None = None,
        presentation: str = "runtime",
        package_location: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._open_help_topic = open_help_topic
        self._open_location = open_location
        self._presentation = presentation
        self._package_location = package_location
        self._report = report
        self._issues_by_row: list[RuntimeIssue] = []

        self.setWindowTitle(title)
        self.setObjectName("shell.runtimeCenterDialog")
        self.setProperty("presentation", presentation)
        self.setMinimumSize(680, 460)
        self.resize(940 if presentation == "packaging" else 880, 600 if presentation == "packaging" else 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("shell.runtimeCenterDialog.header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 12)
        header_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        self._title_icon = QLabel(header)
        self._title_icon.setObjectName("shell.runtimeCenterDialog.titleIcon")
        self._title_icon.setFixedSize(22, 22)
        self._title_icon.setVisible(False)
        title_row.addWidget(self._title_icon, 0, Qt.AlignVCenter)
        self._title_label = QLabel(title, header)
        self._title_label.setObjectName("shell.runtimeCenterDialog.title")
        title_row.addWidget(self._title_label, 1, Qt.AlignVCenter)
        header_layout.addLayout(title_row)

        self._summary_label = QLabel(header)
        self._summary_label.setObjectName("shell.runtimeCenterDialog.summary")
        self._summary_label.setWordWrap(True)
        header_layout.addWidget(self._summary_label)

        outer.addWidget(header)

        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(18, 14, 18, 10)
        body_layout.setSpacing(12)

        list_column = QVBoxLayout()
        list_column.setContentsMargins(0, 0, 0, 0)
        list_column.setSpacing(8)
        self._issue_list = QListWidget(body)
        self._issue_list.setObjectName("shell.runtimeCenterDialog.issueList")
        self._issue_list.setMinimumWidth(290)
        self._issue_list.setAlternatingRowColors(presentation != "packaging")
        self._issue_list.setUniformItemSizes(False)
        self._issue_list.currentRowChanged.connect(self._handle_issue_selection_changed)
        list_column.addWidget(self._issue_list, 1)
        self._apprun_note = QLabel(APPRUN_NOTE, body)
        self._apprun_note.setObjectName("shell.runtimeCenterDialog.appRunNote")
        self._apprun_note.setWordWrap(True)
        self._apprun_note.setVisible(presentation == "packaging")
        list_column.addWidget(self._apprun_note)
        if presentation == "packaging":
            self._issue_list.setMinimumWidth(320)
            self._issue_list.setMaximumWidth(340)
        body_layout.addLayout(list_column, 0)

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

        self._copy_button = QPushButton("Copy Details", footer)
        self._copy_button.setObjectName("shell.runtimeCenterDialog.copyDetails")
        self._copy_button.clicked.connect(self._copy_details)
        self._copy_button.setVisible(presentation == "packaging")
        footer_layout.addWidget(self._copy_button, 0, Qt.AlignLeft)

        self._goto_button = QPushButton("Go to file", footer)
        self._goto_button.setObjectName("shell.runtimeCenterDialog.goToFile")
        self._goto_button.clicked.connect(self._go_to_file)
        self._goto_button.setVisible(presentation == "packaging")
        footer_layout.addWidget(self._goto_button, 0, Qt.AlignLeft)

        self._help_button = QPushButton(
            "Packaging Help" if presentation == "packaging" else "Open Related Help",
            footer,
        )
        self._help_button.setObjectName("shell.runtimeCenterDialog.helpButton")
        self._help_button.clicked.connect(self._handle_open_help)
        if presentation == "packaging":
            # Prototype p4: Copy Details / Go to ... on the left, Packaging Help as a link by Close.
            footer_layout.addStretch(1)
            footer_layout.addWidget(self._help_button)
        else:
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
        if self._presentation == "packaging":
            heading, summary = _summarize_packaging_report(report, self._package_location)
            self._title_label.setText(heading)
            self._summary_label.setText(summary)
            self._title_icon.setPixmap(_packaging_title_icon(report, self._tokens).pixmap(22, 22))
            self._title_icon.setVisible(True)
        else:
            self._summary_label.setText(_summarize_report(report))

        if not report.issues:
            self._detail_browser.setHtml(_render_clear_html(self._tokens))
            self._help_button.setEnabled(False)
            return

        for issue in report.issues:
            if self._presentation == "packaging":
                label = _PACKAGING_SEVERITY_LABELS.get(issue.severity, "Warning: export continues")
                row = str(issue.evidence.get("report_row") or issue.title)
                item = QListWidgetItem(_packaging_row_icon(issue.severity, self._tokens), f"{row}\n{label}")
                item.setToolTip(_packaging_where(issue) or issue.summary)
            else:
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
        if self._presentation == "packaging":
            self._detail_browser.setHtml(_render_packaging_issue_html(issue, self._tokens))
            source = issue.evidence.get("source_file")
            self._goto_button.setEnabled(bool(source))
            if source:
                line = issue.evidence.get("line_number", 1)
                self._goto_button.setText(f"Go to {source}:{line}")
            else:
                self._goto_button.setText("Go to file")
        else:
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

    def _copy_details(self) -> None:
        lines = [PACKAGING_HELP_TEXT, ""]
        for issue in self._issues_by_row:
            label = _PACKAGING_SEVERITY_LABELS.get(issue.severity, "Warning: export continues")
            where = issue.evidence.get("source_file", "")
            line = issue.evidence.get("line_number", "")
            lines.append(f"[{label}] {issue.title} ({where}:{line})")
            lines.append(issue.summary)
            lines.append(issue.why_it_happened)
        lines.append(APPRUN_NOTE)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("\n".join(lines))
        self._copy_button.setText("Copied")
        QTimer.singleShot(2000, lambda: self._copy_button.setText("Copy Details"))

    def _go_to_file(self) -> None:
        row = self._issue_list.currentRow()
        if row < 0 or row >= len(self._issues_by_row) or self._open_location is None:
            return
        issue = self._issues_by_row[row]
        source = issue.evidence.get("source_file")
        if not isinstance(source, str) or not source:
            return
        line_number = issue.evidence.get("line_number", 1)
        try:
            line = int(line_number)
        except (TypeError, ValueError):
            line = 1
        self._open_location(source, line)


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one}" if count == 1 else f"{count} {many}"


def _summarize_packaging_report(report: RuntimeIssueReport, package_location: str = "") -> tuple[str, str]:
    warnings = report.degraded_count + report.advisory_count
    if report.blocking_count:
        heading = "Packaging stopped"
        stops = "stops" if report.blocking_count == 1 else "stop"
        summary = (
            f"{_plural(report.blocking_count, 'problem', 'problems')} {stops} the export. "
            "Fix them, then run Package Project again."
        )
        if warnings:
            does = "does" if warnings == 1 else "do"
            summary += f" {_plural(warnings, 'warning', 'warnings')} {does} not stop the export."
        return heading, summary
    heading = f"Package created with {_plural(warnings, 'warning', 'warnings')}"
    read = "Read the warning before you share it." if warnings == 1 else "Read the warnings before you share it."
    if package_location:
        return heading, f"The package is in {package_location}. {read}"
    return heading, read


def _packaging_where(issue: RuntimeIssue) -> str:
    source = str(issue.evidence.get("source_file") or "")
    if not source:
        return ""
    line = issue.evidence.get("line_number")
    return f"{source}, line {line}" if line not in (None, "") else source


_BACKTICK_CODE = re.compile(r"`([^`]+)`")


def _prose(text: str) -> str:
    """Escape ``text`` and show `backticked` spans as code, like the prototype."""
    return _BACKTICK_CODE.sub(r"<code>\1</code>", escape(text))


def _render_packaging_issue_html(issue: RuntimeIssue, tokens: ShellThemeTokens) -> str:
    badge = _PACKAGING_BADGES.get(issue.severity, "Warning")
    badge_color = _severity_color("blocking" if issue.severity == "blocking" else "degraded", tokens)
    steps = "".join(f"<li>{_prose(step)}</li>" for step in issue.next_steps)
    where = escape(_packaging_where(issue))
    import_path = escape(str(issue.evidence.get("import_path", "")))
    parts = [
        f'<div style="font-family:sans-serif;color:{tokens.text_primary};font-size:13px;">',
        f'<span style="background:{tokens.badge_bg};color:{badge_color};font-weight:600;">'
        f"&nbsp;{escape(badge)}&nbsp;</span>",
        f'<h2 style="margin:8px 0 6px 0;">{escape(issue.title)}</h2>',
        f'<p style="margin:0 0 8px 0;line-height:1.45;">{_prose(issue.summary)}</p>',
    ]
    if issue.why_it_happened:
        parts.append('<h3 style="margin:10px 0 4px 0;">Why</h3>')
        parts.append(f'<p style="margin:0 0 8px 0;line-height:1.45;">{_prose(issue.why_it_happened)}</p>')
    if steps:
        parts.append('<h3 style="margin:10px 0 4px 0;">How to fix it</h3>')
        parts.append(f'<ul style="margin:2px 0 8px 18px;">{steps}</ul>')
    if where or import_path:
        parts.append('<h3 style="margin:10px 0 4px 0;">Where</h3>')
        if where:
            parts.append(f'<p style="margin:0;"><code>{where}</code></p>')
        if import_path:
            parts.append(f'<p style="margin:2px 0 0 0;color:{tokens.text_muted};">Import path: {import_path}</p>')
    parts.append("</div>")
    return "".join(parts)


def _packaging_title_icon(report: RuntimeIssueReport, tokens: ShellThemeTokens) -> QIcon:
    if report.blocking_count:
        return _error_icon(tokens.diag_error_color or "#E03131", 22)
    return _warning_icon(tokens.diag_warning_color or "#D97706", size=22)


def _packaging_row_icon(severity: str, tokens: ShellThemeTokens) -> QIcon:
    if severity == "blocking":
        return _error_icon(tokens.diag_error_color or "#E03131", 14)
    return _warning_icon(tokens.diag_warning_color or "#D97706", size=14)


def _error_icon(color_hex: str, size: int) -> QIcon:
    """Filled circle with a white cross."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(max(1.6, size / 10.0))
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    center = size / 2.0
    reach = size * 0.22
    low, high = int(center - reach), int(center + reach)
    painter.drawLine(QPoint(low, low), QPoint(high, high))
    painter.drawLine(QPoint(high, low), QPoint(low, high))
    painter.end()
    return QIcon(pixmap)


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
