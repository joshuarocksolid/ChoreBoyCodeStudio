"""Startup dialogs. Copy and behavior live here so the look can be restyled in one place.

The problems dialog is modeless. Fatal startup and the FreeCAD 1.0 explanation
are modal, because the user has to read them before the next step.

The look follows the owner-approved v0.4.13 prototypes (``p1_*``). The problems
and FreeCAD dialogs use the shell theme tokens, so light and dark both work.
The fatal dialog is a plain ``QMessageBox`` with a fixed light stylesheet: it
runs when the themed window could not be built, so it depends on as little as
possible.
"""

from __future__ import annotations

from html import escape
from typing import Callable, Optional, Sequence

from app.qt.QtCore import QPoint, Qt, QTimer
from app.qt.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.startup_problems import (
    HELP_LINE,
    STILL_WORKING,
    StartupProblem,
    startup_dialog_title,
    startup_problem_copy_text,
)
from app.core import constants
from app.shell.dialog_chrome import (
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    DialogChrome,
    add_footer_button,
    add_footer_stretch,
    add_meta_chip,
    build_dialog_chrome,
)
from app.shell.plugin_host_unavailable_dialog import (
    freecad_version_label,
    plugin_host_unavailable_message,
)
from app.shell.style_sheet_sections_controls import shell_section_checkbox_indicators
from app.shell.style_sheet_sections_dialogs import shell_section_dialog_chrome
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from app.shell.unsaved_changes_dialog import _warning_icon
from app.qt.qt_compat import exec_qt

PROBLEMS_SUBTITLE = "You can keep working. The parts listed below are turned off until the problem is fixed."
RUNTIME_CENTER_TOOLTIP = "Tools > Runtime Center shows every startup check and what to do next."

FATAL_TITLE = "CBCS could not start"
FATAL_BODY = "Something went wrong while CBCS was opening its window, so it has to close."
FATAL_UNCHANGED = "Your project files were not changed."

FREECAD_TITLE = "FreeCAD 1.0 is required"
FREECAD_SUBTITLE = "Plugins, running, debugging, and the Python console need FreeCAD 1.0."
FREECAD_WORKS = "Opening, editing, and saving files work normally."
FREECAD_CARD_TITLE = "How to turn them on"
FREECAD_CARD_BODY = (
    "To use plugins, running, debugging, and the Python console, this ChoreBoy needs FreeCAD 1.0. "
    + HELP_LINE
)

COPIED_TEXT = "Copied"
COPIED_RESET_MS = 2000

_PROBLEMS_DIALOG = "shell.startupProblemsDialog"
_FREECAD_DIALOG = "shell.freecadRequirementDialog"
_FATAL_DIALOG = "shell.startupFatalDialog"

_SCOPES = ("QDialog#shell\\.startupProblemsDialog", "QDialog#shell\\.freecadRequirementDialog")

_FATAL_QSS = """
QMessageBox { background: #F8F9FA; }
QMessageBox QLabel { color: #212529; font-size: 12px; background: transparent; }
QMessageBox QLabel#qt_msgbox_informativelabel { min-width: 470px; }
QMessageBox QPushButton {
    background: #FFFFFF; color: #212529; border: 1px solid #DEE2E6;
    border-radius: 5px; padding: 6px 12px; font-weight: 600; min-width: 96px;
}
QMessageBox QPushButton:default { background: #3366FF; color: #FFFFFF; border: none; }
QMessageBox QTextEdit { background: #FFFFFF; color: #212529; border: 1px solid #DEE2E6; font-family: monospace; }
"""


def present_startup_problems(
    parent: QWidget,
    problems: Sequence[StartupProblem],
    *,
    log_path: str,
    on_open_runtime_center: Optional[Callable[[], None]] = None,
    on_dismiss: Optional[Callable[[Sequence[str]], None]] = None,
) -> QDialog:
    """Show one card per problem. Continue saves the checked dismissal ids."""
    dialog = build_startup_problems_dialog(
        parent,
        problems,
        log_path=log_path,
        on_open_runtime_center=on_open_runtime_center,
        on_dismiss=on_dismiss,
    )
    dialog.show()
    dialog.raise_()
    return dialog


def build_startup_problems_dialog(
    parent: Optional[QWidget],
    problems: Sequence[StartupProblem],
    *,
    log_path: str,
    on_open_runtime_center: Optional[Callable[[], None]] = None,
    on_dismiss: Optional[Callable[[Sequence[str]], None]] = None,
) -> QDialog:
    dialog = QDialog(parent)
    dialog.setWindowTitle("ChoreBoy Code Studio")
    tokens = _resolve_tokens(parent, dialog)
    chrome = build_dialog_chrome(
        dialog,
        title=startup_dialog_title(problems),
        subtitle=PROBLEMS_SUBTITLE,
        object_name=_PROBLEMS_DIALOG,
        icon=_warning_icon(_warning_color(tokens), size=22),
    )
    dialog.setObjectName(_PROBLEMS_DIALOG)
    chrome.title_label.setWordWrap(True)
    dialog.setStyleSheet(_style_sheet(tokens))
    body_layout = _body_layout(chrome)
    boxes: list[tuple[QCheckBox, str]] = []
    for problem in problems:
        body_layout.addWidget(_problem_card(chrome.body, problem, boxes))
    body_layout.addSpacing(2)
    still_working_label = _section_label(chrome.body, "STILL WORKING")
    still_working_label.setObjectName("shell.startupProblems.section")
    body_layout.addWidget(still_working_label)
    still_working = _bullet_list(chrome.body, STILL_WORKING)
    still_working.setObjectName("shell.startupProblems.stillWorking")
    body_layout.addWidget(still_working)
    log_label = _section_label(chrome.body, "STARTUP LOG")
    log_label.setObjectName("shell.startupProblems.section")
    body_layout.addWidget(log_label)
    log_field = _mono(chrome.body, log_path or "unavailable")
    log_field.setObjectName("shell.startupProblems.logPath")
    body_layout.addWidget(log_field)

    copy_text = startup_problem_copy_text(
        problems,
        log_path=log_path or "unavailable",
        app_version=constants.APP_VERSION,
        freecad_version=freecad_version_label(),
        python_version=_python_version(),
    )
    copy_button = add_footer_button(chrome, "Copy Details", role=FOOTER_ROLE_SECONDARY)
    copy_button.setObjectName("shell.startupProblems.copyDetails")
    add_footer_stretch(chrome)
    runtime_button = add_footer_button(chrome, "Open Runtime Center", role=FOOTER_ROLE_SECONDARY)
    runtime_button.setObjectName("shell.startupProblems.openRuntimeCenter")
    runtime_button.setToolTip(RUNTIME_CENTER_TOOLTIP)
    continue_button = add_footer_button(chrome, "Continue", role=FOOTER_ROLE_PRIMARY, default=True)
    continue_button.setObjectName("shell.startupProblems.continueButton")

    def continue_clicked() -> None:
        if on_dismiss is not None:
            on_dismiss([problem_id for box, problem_id in boxes if box.isChecked()])
        dialog.close()

    _wire_copy(copy_button, copy_text)
    runtime_button.clicked.connect(lambda: on_open_runtime_center() if on_open_runtime_center else None)
    continue_button.clicked.connect(continue_clicked)
    dialog._cbcs_dismiss_boxes = boxes  # type: ignore[attr-defined]
    _fit(dialog, chrome, 600)
    return dialog


def checked_problem_ids(dialog: QDialog) -> list[str]:
    boxes = getattr(dialog, "_cbcs_dismiss_boxes", ())
    return [problem_id for box, problem_id in boxes if box.isChecked()]


def build_fatal_startup_dialog(summary: str, log_path: str, details: str) -> QMessageBox:
    """Plain message box for the last-resort path. Show Details... reveals the traceback."""
    log_display = log_path or "unavailable"
    box = QMessageBox()
    box.setObjectName(_FATAL_DIALOG)
    box.setStyleSheet(_FATAL_QSS)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle("ChoreBoy Code Studio")
    box.setTextFormat(Qt.RichText)
    box.setText(f"<b style='font-size:14px'>{escape(FATAL_TITLE)}</b>")
    box.setInformativeText(
        f"{escape(FATAL_BODY)}<br>{escape(FATAL_UNCHANGED)}<br><br>"
        f"<b>Error:</b> <code>{escape(summary)}</code><br><br>"
        f"<b>Log file:</b> <code>{escape(log_display)}</code><br><br>"
        f"{escape(HELP_LINE)}"
    )
    box.setDetailedText(details)
    copy_text = "\n".join(
        [
            FATAL_TITLE,
            f"ChoreBoy Code Studio {constants.APP_VERSION}",
            f"FreeCAD {freecad_version_label()} | Python {_python_version()}",
            f"Error: {summary}",
            f"Log file: {log_display}",
            "",
            details,
            "",
            HELP_LINE,
        ]
    )
    copy_button = box.addButton("Copy Details", QMessageBox.ActionRole)
    copy_button.setObjectName("shell.startupFatal.copyDetails")
    # QMessageBox closes on any button; Copy Details must leave the box open.
    copy_button.clicked.disconnect()
    _wire_copy(copy_button, copy_text)
    close_button = box.addButton("Close", QMessageBox.RejectRole)
    close_button.setObjectName("shell.startupFatal.closeButton")
    box.setDefaultButton(close_button)
    box.setEscapeButton(close_button)
    for button in box.findChildren(QPushButton):
        if button.text().startswith("Show Details"):
            button.setObjectName("shell.startupFatal.showDetails")
    for detail_box in box.findChildren(QTextEdit):
        detail_box.setObjectName("shell.startupFatal.details")
    return box


def present_fatal_startup_dialog(summary: str, log_path: str, details: str) -> None:
    """Last-resort dialog when the window cannot be built."""
    app = QApplication.instance()
    if app is None:
        QApplication([])
    exec_qt(build_fatal_startup_dialog(summary, log_path, details))


def build_freecad_requirement_dialog(parent: Optional[QWidget], detail: str) -> QDialog:
    version = freecad_version_label()
    message = plugin_host_unavailable_message(detail, version)
    log_path = _log_path_for(parent)
    dialog = QDialog(parent)
    dialog.setWindowTitle("ChoreBoy Code Studio")
    tokens = _resolve_tokens(parent, dialog)
    chrome = build_dialog_chrome(
        dialog,
        title=FREECAD_TITLE,
        subtitle=FREECAD_SUBTITLE,
        object_name=_FREECAD_DIALOG,
        icon=_info_icon(tokens.diag_info_color or tokens.accent, size=22),
    )
    dialog.setObjectName(_FREECAD_DIALOG)
    chrome.title_label.setWordWrap(True)
    dialog.setStyleSheet(_style_sheet(tokens))
    add_meta_chip(chrome.meta_row, _freecad_chip(version))
    needs_chip = add_meta_chip(chrome.meta_row, "Needs FreeCAD 1.0")
    needs_chip.setProperty("metaChip", "warning")
    body_layout = _body_layout(chrome)
    message_label = _text(chrome.body, _freecad_body(version))
    message_label.setObjectName("shell.freecadRequirement.message")
    body_layout.addWidget(message_label)
    works_label = _text(chrome.body, FREECAD_WORKS)
    works_label.setObjectName("shell.freecadRequirement.works")
    body_layout.addWidget(works_label)
    card, card_layout = _card(chrome.body, "info")
    card.setObjectName("shell.freecadRequirement.card")
    card_title = _text(card, FREECAD_CARD_TITLE)
    card_title.setObjectName("shell.freecadRequirement.cardTitle")
    card_layout.addWidget(card_title)
    card_body = _text(card, FREECAD_CARD_BODY)
    card_body.setObjectName("shell.freecadRequirement.cardBody")
    card_layout.addWidget(card_body)
    body_layout.addWidget(card)
    seen_label = _section_label(chrome.body, "WHAT CBCS SAW")
    seen_label.setObjectName("shell.freecadRequirement.section")
    body_layout.addWidget(seen_label)
    seen = detail.strip() or "No error text was recorded."
    seen_field = _mono(chrome.body, seen)
    seen_field.setObjectName("shell.freecadRequirement.detail")
    body_layout.addWidget(seen_field)
    log_line = _text(chrome.body, f"Log: {log_path}")
    log_line.setObjectName("shell.freecadRequirement.logPath")
    body_layout.addWidget(log_line)

    copy_text = "\n".join(
        [
            f"ChoreBoy Code Studio {constants.APP_VERSION}",
            f"FreeCAD {version} | Python {_python_version()}",
            message,
            f"Log: {log_path}",
        ]
    )
    copy_button = add_footer_button(chrome, "Copy Details", role=FOOTER_ROLE_SECONDARY)
    copy_button.setObjectName("shell.freecadRequirement.copyDetails")
    add_footer_stretch(chrome)
    ok_button = add_footer_button(chrome, "OK", role=FOOTER_ROLE_PRIMARY, default=True)
    ok_button.setObjectName("shell.freecadRequirement.okButton")
    _wire_copy(copy_button, copy_text)
    ok_button.clicked.connect(dialog.accept)
    _fit(dialog, chrome, 560)
    return dialog


def present_freecad_requirement(parent: Optional[QWidget], detail: str) -> None:
    """Explain that plugins, run, debug, and the Python console need FreeCAD 1.0."""
    exec_qt(build_freecad_requirement_dialog(parent, detail))


def _freecad_body(version: str) -> str:
    known = version and version != "unknown"
    opening = f"This ChoreBoy has FreeCAD {version}." if known else "CBCS could not read this ChoreBoy's FreeCAD version."
    return (
        f"{opening} Plugins, running, debugging, and the Python console "
        "all start /opt/freecad/AppRun. FreeCAD 0.21 does not let CBCS start it, "
        "so CBCS turned them off."
    )


def _freecad_chip(version: str) -> str:
    return f"FreeCAD {version}" if version and version != "unknown" else "FreeCAD version unknown"


def _problem_card(
    parent: QWidget,
    problem: StartupProblem,
    boxes: list[tuple[QCheckBox, str]],
) -> QWidget:
    severity = "info" if problem.kind == "notice" else "warning"
    card, layout = _card(parent, severity)
    card.setObjectName("shell.startupProblems.card")
    title_label = _text(card, problem.title)
    title_label.setObjectName("shell.startupProblems.cardTitle")
    layout.addWidget(title_label)
    summary_label = _text(card, problem.summary)
    summary_label.setObjectName("shell.startupProblems.cardSummary")
    layout.addWidget(summary_label)
    if problem.folder or problem.error:
        layout.addSpacing(2)
    if problem.folder:
        folder_value = _mono(card, problem.folder)
        folder_value.setObjectName("shell.startupProblems.folder")
        layout.addWidget(_field_row(card, "Folder", folder_value))
    if problem.error:
        error_value = _mono(card, problem.error)
        error_value.setObjectName("shell.startupProblems.error")
        layout.addWidget(_field_row(card, "Error", error_value))
    layout.addSpacing(2)
    fix = QLabel(f"<b>How to fix it:</b> {escape(problem.fix)}", card)
    fix.setObjectName("shell.startupProblems.fix")
    fix.setTextFormat(Qt.RichText)
    fix.setWordWrap(True)
    layout.addWidget(fix)
    box = QCheckBox("Don't show again for this problem", card)
    box.setObjectName("shell.startupProblems.dismiss")
    layout.addWidget(box)
    boxes.append((box, problem.problem_id))
    return card


def _card(parent: QWidget, severity: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(parent)
    card.setProperty("severity", severity)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)
    return card, layout


def _field_row(parent: QWidget, key: str, value: QWidget) -> QWidget:
    row = QWidget(parent)
    row.setObjectName("shell.startupProblems.field")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    key_label = QLabel(key, row)
    key_label.setObjectName("shell.startupProblems.fieldKey")
    key_label.setFixedWidth(64)
    key_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
    key_label.setContentsMargins(0, 5, 0, 0)
    layout.addWidget(key_label, 0, Qt.AlignTop)
    value.setParent(row)
    layout.addWidget(value, 1)
    return row


def _text(parent: QWidget, text: str) -> QLabel:
    label = QLabel(text, parent)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    return label


def _mono(parent: QWidget, text: str) -> QLabel:
    """Read-only, selectable, monospaced field (path or error)."""
    label = QLabel(text, parent)
    label.setProperty("startupMono", True)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setFont(_mono_font())
    return label


def _mono_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(9)
    return font


def _bullet_list(parent: QWidget, items: Sequence[str]) -> QLabel:
    html = "<br>".join(f"&bull;&nbsp;&nbsp;{escape(item)}" for item in items)
    label = QLabel(html, parent)
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setContentsMargins(4, 0, 0, 0)
    return label


def _section_label(parent: QWidget, text: str) -> QLabel:
    label = QLabel(text, parent)
    label.setProperty("startupSection", True)
    return label


def _body_layout(chrome: DialogChrome) -> QVBoxLayout:
    layout = chrome.body.layout()
    assert isinstance(layout, QVBoxLayout)
    return layout


def _fit(dialog: QDialog, chrome: DialogChrome, width: int) -> None:
    """Size the dialog to its content at ``width`` so there are no stretched gaps."""
    _body_layout(chrome).addStretch(1)
    dialog.setMinimumWidth(width)
    layout = dialog.layout()
    layout.activate()
    height = layout.totalHeightForWidth(width)
    dialog.resize(width, max(height, layout.totalMinimumSize().height()))


def _wire_copy(button: QPushButton, text: str) -> None:
    """Copy ``text``; the button reads ``Copied`` for two seconds."""
    original = button.text()

    def copy() -> None:
        _copy_to_clipboard(text)
        button.setText(COPIED_TEXT)
        QTimer.singleShot(COPIED_RESET_MS, lambda: button.setText(original))

    button.clicked.connect(copy)


def _resolve_tokens(parent: Optional[QWidget], dialog: QDialog) -> ShellThemeTokens:
    """Shell tokens from the main window, so the dialog follows light and dark."""
    candidates: list[object] = [parent]
    app = QApplication.instance()
    if parent is None and isinstance(app, QApplication):
        candidates.append(app.activeWindow())
        candidates.extend(app.topLevelWidgets())
    for candidate in candidates:
        accessor = getattr(candidate, "current_theme_tokens", None)
        if not callable(accessor):
            continue
        try:
            resolved = accessor()
        except (AttributeError, RuntimeError):
            continue
        if isinstance(resolved, ShellThemeTokens):
            return resolved
    return tokens_from_palette(dialog.palette())


def _log_path_for(parent: Optional[QWidget]) -> str:
    try:
        from app.bootstrap.logging_setup import get_active_log_path

        path = get_active_log_path(getattr(parent, "_state_root", None))
    except Exception:
        return "unavailable"
    return str(path) if path is not None else "unavailable"


def _warning_color(tokens: ShellThemeTokens) -> str:
    return tokens.diag_warning_color or ("#E5A100" if tokens.is_dark else "#D97706")


def _info_icon(color_hex: str, size: int = 22) -> QIcon:
    """Filled circle with a white ``i``, sized for the dialog header."""
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
    radius = size * 0.22
    painter.drawLine(int(center), int(center - radius * 0.2), int(center), int(center + radius * 1.2))
    painter.drawPoint(QPoint(int(center), int(center - radius * 1.1)))
    painter.end()
    return QIcon(pixmap)


def _rule(selectors: Sequence[str], body: str) -> str:
    """One QSS rule, with each selector scoped to both startup dialogs."""
    scoped = ",\n".join(f"{scope} {selector}" for selector in selectors for scope in _SCOPES)
    return f"{scoped} {{\n{body}}}\n"


def _style_sheet(tokens: ShellThemeTokens) -> str:
    """Chrome plus the startup cards. Set on the dialog so it works without a themed parent."""
    warning = _warning_color(tokens)
    info = tokens.diag_info_color or tokens.accent
    accent_hover = tokens.accent_hover or tokens.accent
    accent_pressed = tokens.accent_pressed or tokens.accent
    chip = (
        f"    padding: 3px 9px;\n    border-radius: 9px;\n    font-size: 11px;\n    font-weight: 600;\n"
        f"    background: {tokens.badge_bg};\n"
    )
    card = f"    background: {tokens.panel_bg};\n    border: 1px solid {tokens.border};\n    border-radius: 6px;\n"
    rules = [
        f"{', '.join(_SCOPES)} {{\n    background: {tokens.window_bg};\n    color: {tokens.text_primary};\n}}\n",
        _rule(["QLabel"], f"    color: {tokens.text_primary};\n    background: transparent;\n    font-size: 12px;\n"),
        _rule(
            ["QCheckBox"],
            f"    color: {tokens.text_primary};\n    background: transparent;\n    font-size: 12px;\n    spacing: 6px;\n",
        ),
        _rule(["QLabel#shell\\.dialogChrome\\.title"], "    font-size: 17px;\n    font-weight: 700;\n"),
        _rule(["QLabel#shell\\.dialogChrome\\.subtitle"], f"    color: {tokens.text_muted};\n"),
        _rule(
            ['QWidget#shell\\.dialogChrome\\.metaRow QLabel[metaChip="true"]'],
            chip + f"    color: {tokens.text_muted};\n",
        ),
        _rule(
            ['QWidget#shell\\.dialogChrome\\.metaRow QLabel[metaChip="warning"]'],
            chip + f"    color: {warning};\n",
        ),
        _rule(['QFrame[severity="warning"]'], card + f"    border-left: 3px solid {warning};\n"),
        _rule(['QFrame[severity="info"]'], card + f"    border-left: 3px solid {info};\n"),
        _rule(
            ["QLabel#shell\\.startupProblems\\.cardTitle", "QLabel#shell\\.freecadRequirement\\.cardTitle"],
            "    font-size: 13px;\n    font-weight: 700;\n",
        ),
        _rule(["QLabel#shell\\.startupProblems\\.fieldKey"], f"    color: {tokens.text_muted};\n    font-weight: 600;\n"),
        _rule(
            ["QLabel#shell\\.startupProblems\\.fix", "QLabel#shell\\.freecadRequirement\\.logPath"],
            f"    color: {tokens.text_muted};\n",
        ),
        _rule(
            ['QLabel[startupSection="true"]'],
            f"    color: {tokens.text_muted};\n    font-size: 11px;\n    font-weight: 700;\n",
        ),
        _rule(
            ['QLabel[startupMono="true"]'],
            f"    background: {tokens.editor_bg};\n    color: {tokens.text_primary};\n"
            f"    border: 1px solid {tokens.border};\n    border-radius: 4px;\n    padding: 4px 7px;\n",
        ),
        _rule(
            ['QPushButton[buttonRole="primary"]'],
            f"    background: {tokens.accent};\n    color: #FFFFFF;\n    border: none;\n    border-radius: 5px;\n"
            "    padding: 7px 16px;\n    font-size: 13px;\n    font-weight: 600;\n",
        ),
        _rule(['QPushButton[buttonRole="primary"]:hover'], f"    background: {accent_hover};\n"),
        _rule(['QPushButton[buttonRole="primary"]:pressed'], f"    background: {accent_pressed};\n"),
        _rule(
            ['QPushButton[buttonRole="secondary"]'],
            f"    background: {tokens.input_bg};\n    color: {tokens.text_primary};\n"
            f"    border: 1px solid {tokens.border};\n    border-radius: 5px;\n"
            "    padding: 7px 14px;\n    font-size: 12px;\n    font-weight: 600;\n",
        ),
        _rule(
            ['QPushButton[buttonRole="secondary"]:hover'],
            f"    background: {tokens.tree_hover_bg};\n    border-color: {tokens.accent};\n",
        ),
        _rule(['QPushButton[buttonRole="secondary"]:pressed'], f"    background: {tokens.tree_selected_bg};\n"),
    ]
    return (
        shell_section_dialog_chrome(tokens)
        + shell_section_checkbox_indicators(tokens)
        + "/* -- Startup dialogs (v0.4.13 p1 prototypes) ----------------------------- */\n"
        + "".join(rules)
    )


def _copy_to_clipboard(text: str) -> None:
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


def _python_version() -> str:
    import sys

    return sys.version.split()[0]
