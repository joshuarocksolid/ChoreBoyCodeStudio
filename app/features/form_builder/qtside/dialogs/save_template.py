"""The Save as template popover (UX-TMPL-001).

A level 2 popover under the tab toolbar: Name, Description, where to keep the
template, a caption, [Save template] and [Cancel]. Enter in either field saves;
Esc cancels. The popover only collects the answers: ``on_save`` receives
``(name, description, scope)`` after the popover has closed.
"""

from __future__ import annotations

from typing import Callable

from app.qt.QtCore import QPoint, Qt
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.features.form_builder.engine.project.user_templates import SCOPE_PROJECT, SCOPE_USER
from app.features.form_builder.qtside.theme.chrome import FormChrome, apply_level2_shadow, edge_on, popover_style

OBJECT_NAME = "formBuilder.saveTemplate"
DESCRIPTION_PLACEHOLDER = "What this form is for"
CAPTION = "Saves a copy of this form's design and pictures. Your code and data are not included."
SAVE_LABEL = "Save template"
WIDTH = 380


def _field_style(chrome: FormChrome) -> str:
    """Line edits and the two radio buttons, painted from the chrome (a style sheet drops the native look)."""
    frame = "QFrame#%s" % OBJECT_NAME.replace(".", "\\.")
    edge = edge_on(chrome, chrome.panel)
    focus = max(1, chrome.focus_width)
    return (
        "%(f)s QLineEdit { background: %(input)s; color: %(text)s; border: 1px solid %(border)s;"
        " border-radius: 4px; padding: 5px 6px; }"
        "%(f)s QLineEdit:focus { border: %(focus)dpx solid %(accent)s; }"
        "%(f)s QRadioButton { color: %(text)s; spacing: 6px; background: transparent; }"
        "%(f)s QRadioButton:disabled { color: %(muted)s; }"
        "%(f)s QRadioButton::indicator { width: 13px; height: 13px; border: 1px solid %(edge)s;"
        " border-radius: 7px; background: %(panel)s; }"
        "%(f)s QRadioButton::indicator:checked { border: 1px solid %(accent)s; background: qradialgradient("
        "cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 %(accent)s, stop:0.5 %(accent)s,"
        " stop:0.56 %(panel)s, stop:1 %(panel)s); }"
        "%(f)s QRadioButton::indicator:focus { border: %(focus)dpx solid %(accent)s; }"
        "%(f)s QRadioButton::indicator:disabled { border: 1px solid %(muted)s; }"
    ) % {
        "f": frame,
        "input": chrome.input,
        "text": chrome.text,
        "border": chrome.border,
        "focus": focus,
        "accent": chrome.accent,
        "muted": chrome.muted,
        "edge": edge,
        "panel": chrome.panel,
    }


class SaveTemplatePopover(QFrame):
    def __init__(
        self,
        parent: QWidget,
        chrome: FormChrome,
        *,
        name: str,
        description: str = "",
        scope: str = SCOPE_USER,
        project_available: bool = True,
        on_save: Callable[[str, str, str], None],
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName(OBJECT_NAME)
        self.setAccessibleName("Save as template")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(popover_style(OBJECT_NAME, chrome) + _field_style(chrome))
        self._on_save = on_save
        self._chrome = chrome
        column = QVBoxLayout(self)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(8)

        self.name_label = QLabel("Name", self)
        self.name = QLineEdit(name, self)
        self.name.setObjectName(OBJECT_NAME + ".name")
        self.name.setAccessibleName("Name")
        self.name_label.setBuddy(self.name)
        self.description_label = QLabel("Description", self)
        self.description = QLineEdit(description, self)
        self.description.setObjectName(OBJECT_NAME + ".description")
        self.description.setAccessibleName("Description")
        self.description.setPlaceholderText(DESCRIPTION_PLACEHOLDER)
        self.description_label.setBuddy(self.description)
        for widget in (self.name_label, self.name, self.description_label, self.description):
            column.addWidget(widget)

        keep = QLabel("Keep it for", self)
        column.addWidget(keep)
        self.all_projects = QRadioButton("All my projects", self)
        self.all_projects.setObjectName(OBJECT_NAME + ".allProjects")
        self.this_project = QRadioButton("This project only", self)
        self.this_project.setObjectName(OBJECT_NAME + ".thisProject")
        self.this_project.setEnabled(project_available)
        if not project_available:
            self.this_project.setToolTip("Open this form from a project to keep a template for that project only.")
        (self.this_project if scope == SCOPE_PROJECT and project_available else self.all_projects).setChecked(True)
        column.addWidget(self.all_projects)
        column.addWidget(self.this_project)

        self.caption = QLabel(CAPTION, self)
        self.caption.setProperty("note", True)
        self.caption.setWordWrap(True)
        column.addWidget(self.caption)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.save_button = QPushButton(SAVE_LABEL, self)
        self.save_button.setObjectName(OBJECT_NAME + ".save")
        self.save_button.setDefault(True)
        self.save_button.setAutoDefault(True)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName(OBJECT_NAME + ".cancel")
        self.cancel_button.setAutoDefault(False)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.cancel_button)
        column.addLayout(buttons)

        self.setFixedWidth(WIDTH)
        apply_level2_shadow(self, chrome)
        self.name.textChanged.connect(self._sync)
        self.name.returnPressed.connect(self.submit)
        self.description.returnPressed.connect(self.submit)
        self.save_button.clicked.connect(self.submit)
        self.cancel_button.clicked.connect(self.close)
        self._sync()

    def scope(self) -> str:
        return SCOPE_PROJECT if self.this_project.isChecked() else SCOPE_USER

    def open_at(self, point: QPoint) -> None:
        """Show with the top-left at ``point`` (global) and the Name selected."""
        self.adjustSize()
        self.move(point)
        self.show()
        self.name.setFocus()
        self.name.selectAll()

    def submit(self) -> None:
        name = self.name.text().strip()
        if not name:
            return
        description, scope = self.description.text().strip(), self.scope()
        self.close()
        self._on_save(name, description, scope)

    def _sync(self) -> None:
        self.save_button.setEnabled(bool(self.name.text().strip()))

