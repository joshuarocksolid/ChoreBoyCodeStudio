"""Startup dialogs. Copy and behavior live here so the look can be restyled in one place.

The problems dialog is modeless. Fatal startup and the FreeCAD 1.0 explanation
are modal, because the user has to read them before the next step.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from PySide2.QtCore import Qt, QTimer
from PySide2.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QPlainTextEdit,
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
    add_footer_button,
    add_footer_stretch,
    build_dialog_chrome,
)
from app.shell.plugin_host_unavailable_dialog import (
    freecad_version_label,
    plugin_host_unavailable_message,
)


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
    dialog.setMinimumWidth(560)
    chrome = build_dialog_chrome(
        dialog,
        title=startup_dialog_title(problems),
        subtitle="You can keep working. The parts listed below are turned off until the problem is fixed.",
        object_name="shell.startupProblemsDialog",
    )
    dialog.setObjectName("shell.startupProblemsDialog")
    body_layout = chrome.body.layout()
    assert isinstance(body_layout, QVBoxLayout)
    boxes: list[tuple[QCheckBox, str]] = []
    for problem in problems:
        body_layout.addWidget(_problem_card(chrome.body, problem, boxes))
    body_layout.addWidget(_section_label(chrome.body, "STILL WORKING"))
    for line in STILL_WORKING:
        body_layout.addWidget(QLabel(line, chrome.body))
    body_layout.addWidget(_section_label(chrome.body, "STARTUP LOG"))
    log_label = QLabel(log_path or "unavailable", chrome.body)
    log_label.setObjectName("shell.startupProblems.logPath")
    log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    body_layout.addWidget(log_label)

    copy_text = startup_problem_copy_text(
        problems,
        log_path=log_path or "unavailable",
        app_version=constants.APP_VERSION,
        freecad_version=freecad_version_label(),
        python_version=_python_version(),
    )
    add_footer_stretch(chrome)
    copy_button = add_footer_button(chrome, "Copy Details", role=FOOTER_ROLE_SECONDARY)
    copy_button.setObjectName("shell.startupProblems.copyDetails")
    runtime_button = add_footer_button(chrome, "Open Runtime Center", role=FOOTER_ROLE_SECONDARY)
    runtime_button.setObjectName("shell.startupProblems.openRuntimeCenter")
    continue_button = add_footer_button(chrome, "Continue", role=FOOTER_ROLE_PRIMARY, default=True)
    continue_button.setObjectName("shell.startupProblems.continueButton")

    def copy_details() -> None:
        _copy_to_clipboard(copy_text)
        copy_button.setText("Copied")
        QTimer.singleShot(2000, lambda: copy_button.setText("Copy Details"))

    def continue_clicked() -> None:
        if on_dismiss is not None:
            on_dismiss([problem_id for box, problem_id in boxes if box.isChecked()])
        dialog.close()

    copy_button.clicked.connect(copy_details)
    runtime_button.clicked.connect(lambda: on_open_runtime_center() if on_open_runtime_center else None)
    continue_button.clicked.connect(continue_clicked)
    dialog._cbcs_dismiss_boxes = boxes  # type: ignore[attr-defined]
    return dialog


def checked_problem_ids(dialog: QDialog) -> list[str]:
    boxes = getattr(dialog, "_cbcs_dismiss_boxes", ())
    return [problem_id for box, problem_id in boxes if box.isChecked()]


def present_fatal_startup_dialog(summary: str, log_path: str, details: str) -> None:
    """Last-resort dialog when the window cannot be built."""
    app = QApplication.instance()
    if app is None:
        QApplication([])
    dialog = QDialog()
    dialog.setWindowTitle("ChoreBoy Code Studio")
    dialog.setMinimumWidth(520)
    chrome = build_dialog_chrome(
        dialog,
        title="CBCS could not start",
        subtitle="Something went wrong while CBCS was opening its window, so it has to close.",
        object_name="shell.startupFatalDialog",
    )
    dialog.setObjectName("shell.startupFatalDialog")
    body_layout = chrome.body.layout()
    assert isinstance(body_layout, QVBoxLayout)
    body_layout.addWidget(QLabel("Your project files were not changed.", chrome.body))
    body_layout.addWidget(QLabel(f"Error: {summary}", chrome.body))
    log_display = log_path or "unavailable"
    body_layout.addWidget(QLabel(f"Log file: {log_display}", chrome.body))
    body_layout.addWidget(QLabel(HELP_LINE, chrome.body))
    detail_box = QPlainTextEdit(chrome.body)
    detail_box.setPlainText(details)
    detail_box.setReadOnly(True)
    detail_box.setVisible(False)
    detail_box.setObjectName("shell.startupFatal.details")
    body_layout.addWidget(detail_box)

    copy_text = "\n".join(
        [
            "CBCS could not start",
            f"Error: {summary}",
            f"Log file: {log_display}",
            "",
            details,
            "",
            HELP_LINE,
        ]
    )
    add_footer_stretch(chrome)
    copy_button = add_footer_button(chrome, "Copy Details", role=FOOTER_ROLE_SECONDARY)
    copy_button.setObjectName("shell.startupFatal.copyDetails")
    details_button = add_footer_button(chrome, "Show Details...", role=FOOTER_ROLE_SECONDARY)
    details_button.setObjectName("shell.startupFatal.showDetails")
    close_button = add_footer_button(chrome, "Close", role=FOOTER_ROLE_PRIMARY, default=True)
    close_button.setObjectName("shell.startupFatal.closeButton")
    copy_button.clicked.connect(lambda: _copy_to_clipboard(copy_text))
    details_button.clicked.connect(lambda: detail_box.setVisible(not detail_box.isVisible()))
    close_button.clicked.connect(dialog.accept)
    dialog.exec_()


def present_freecad_requirement(parent: Optional[QWidget], detail: str) -> None:
    """Explain that plugins, run, debug, and the Python console need FreeCAD 1.0."""
    version = freecad_version_label()
    message = plugin_host_unavailable_message(detail, version)
    dialog = QDialog(parent)
    dialog.setWindowTitle("ChoreBoy Code Studio")
    dialog.setMinimumWidth(560)
    chrome = build_dialog_chrome(
        dialog,
        title="FreeCAD 1.0 is required",
        subtitle="Plugins, running, debugging, and the Python console need FreeCAD 1.0.",
        object_name="shell.freecadRequirementDialog",
    )
    dialog.setObjectName("shell.freecadRequirementDialog")
    body_layout = chrome.body.layout()
    assert isinstance(body_layout, QVBoxLayout)
    body = QLabel(message, chrome.body)
    body.setWordWrap(True)
    body.setObjectName("shell.freecadRequirement.message")
    body_layout.addWidget(body)
    add_footer_stretch(chrome)
    copy_button = add_footer_button(chrome, "Copy Details", role=FOOTER_ROLE_SECONDARY)
    copy_button.setObjectName("shell.freecadRequirement.copyDetails")
    ok_button = add_footer_button(chrome, "OK", role=FOOTER_ROLE_PRIMARY, default=True)
    ok_button.setObjectName("shell.freecadRequirement.okButton")
    copy_button.clicked.connect(lambda: _copy_to_clipboard(message))
    ok_button.clicked.connect(dialog.accept)
    dialog.exec_()


def _problem_card(
    parent: QWidget,
    problem: StartupProblem,
    boxes: list[tuple[QCheckBox, str]],
) -> QWidget:
    card = QWidget(parent)
    card.setObjectName("shell.startupProblems.card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 8, 0, 8)
    title = QLabel(problem.title, card)
    title.setObjectName("shell.startupProblems.cardTitle")
    layout.addWidget(title)
    summary = QLabel(problem.summary, card)
    summary.setWordWrap(True)
    layout.addWidget(summary)
    if problem.folder:
        folder = QLabel(f"Folder: {problem.folder}", card)
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(folder)
    if problem.error:
        error = QLabel(f"Error: {problem.error}", card)
        error.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(error)
    fix = QLabel(f"How to fix it: {problem.fix}", card)
    fix.setWordWrap(True)
    layout.addWidget(fix)
    box = QCheckBox("Don't show again for this problem", card)
    box.setObjectName("shell.startupProblems.dismiss")
    layout.addWidget(box)
    boxes.append((box, problem.problem_id))
    return card


def _section_label(parent: QWidget, text: str) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("shell.startupProblems.section")
    return label


def _copy_to_clipboard(text: str) -> None:
    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


def _python_version() -> str:
    import sys

    return sys.version.split()[0]
