"""New form dialog for Designer workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class NewFormRequest:
    """User selections for creating a new form."""

    form_class_name: str
    root_widget_class: str
    root_object_name: str


_BASE_WIDGET_DESCRIPTIONS = {
    "QWidget": "A generic container widget. Use for custom forms, panels, or embedded widgets.",
    "QDialog": "A modal or modeless dialog window. Use for settings, prompts, or secondary windows.",
    "QMainWindow": "A top-level window with menu bar, toolbars, and status bar support.",
}


class NewFormDialog(QDialog):
    """Unified dialog for creating a new .ui form file."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("designer.newForm")
        self.setWindowTitle("Create New Form")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._result: Optional[NewFormRequest] = None
        self._build_ui()
        self._connect_signals()
        self._update_description()
        self._validate()

    @property
    def result(self) -> Optional[NewFormRequest]:
        """Return the accepted form request, or None if cancelled."""
        return self._result

    def form_file_name(self) -> str:
        """Return the normalized file name (always ends with .ui)."""
        name = self._file_name_edit.text().strip()
        if not name:
            return ""
        if not name.lower().endswith(".ui"):
            name = f"{name}.ui"
        return name

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(6)

        # Title
        title = QLabel("Create New Form", self)
        title.setObjectName("designer.newForm.title")
        layout.addWidget(title)
        layout.addSpacing(8)

        # Form class name
        class_label = QLabel("Form Class Name", self)
        class_label.setObjectName("designer.newForm.fieldLabel")
        layout.addWidget(class_label)
        self._class_name_edit = QLineEdit(self)
        self._class_name_edit.setObjectName("designer.newForm.className")
        self._class_name_edit.setPlaceholderText("e.g. MainForm")
        self._class_name_edit.setText("MainForm")
        layout.addWidget(self._class_name_edit)
        layout.addSpacing(4)

        # File name
        file_label = QLabel("File Name", self)
        file_label.setObjectName("designer.newForm.fieldLabel")
        layout.addWidget(file_label)
        self._file_name_edit = QLineEdit(self)
        self._file_name_edit.setObjectName("designer.newForm.fileName")
        self._file_name_edit.setPlaceholderText("e.g. main_form.ui")
        self._file_name_edit.setText("form.ui")
        layout.addWidget(self._file_name_edit)
        layout.addSpacing(4)

        # Base widget
        widget_label = QLabel("Base Widget", self)
        widget_label.setObjectName("designer.newForm.fieldLabel")
        layout.addWidget(widget_label)
        self._base_widget_combo = QComboBox(self)
        self._base_widget_combo.setObjectName("designer.newForm.baseWidget")
        self._base_widget_combo.addItems(["QWidget", "QDialog", "QMainWindow"])
        layout.addWidget(self._base_widget_combo)
        layout.addSpacing(4)

        # Description area
        self._description_label = QLabel("", self)
        self._description_label.setObjectName("designer.newForm.description")
        self._description_label.setWordWrap(True)
        layout.addWidget(self._description_label)
        layout.addSpacing(12)

        # Validation message
        self._validation_label = QLabel("", self)
        self._validation_label.setObjectName("designer.newForm.fieldLabel")
        self._validation_label.setVisible(False)
        layout.addWidget(self._validation_label)

        # Button row
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)
        self._cancel_button = QPushButton("Cancel", self)
        self._cancel_button.setObjectName("designer.newForm.btn.cancel")
        button_row.addWidget(self._cancel_button)
        self._create_button = QPushButton("Create", self)
        self._create_button.setObjectName("designer.newForm.btn.create")
        self._create_button.setDefault(True)
        button_row.addWidget(self._create_button)
        layout.addLayout(button_row)

    def _connect_signals(self) -> None:
        self._class_name_edit.textChanged.connect(self._on_class_name_changed)
        self._file_name_edit.textChanged.connect(self._validate)
        self._base_widget_combo.currentTextChanged.connect(self._update_description)
        self._cancel_button.clicked.connect(self.reject)
        self._create_button.clicked.connect(self._accept_form)

    def _on_class_name_changed(self, text: str) -> None:
        """Auto-suggest file name based on class name."""
        stripped = text.strip()
        if stripped:
            # Convert CamelCase to snake_case-ish file name
            chars: list[str] = []
            for i, char in enumerate(stripped):
                if char.isupper() and i > 0 and not stripped[i - 1].isupper():
                    chars.append("_")
                chars.append(char.lower())
            suggested = "".join(chars)
            if not suggested.endswith(".ui"):
                suggested = f"{suggested}.ui"
            self._file_name_edit.setText(suggested)
        self._validate()

    def _update_description(self) -> None:
        widget_class = self._base_widget_combo.currentText()
        desc = _BASE_WIDGET_DESCRIPTIONS.get(widget_class, "")
        self._description_label.setText(desc)

    def _validate(self) -> None:
        class_name = self._class_name_edit.text().strip()
        file_name = self._file_name_edit.text().strip()
        errors: list[str] = []
        if not class_name:
            errors.append("Class name is required.")
        elif not class_name[0].isalpha():
            errors.append("Class name must start with a letter.")
        if not file_name:
            errors.append("File name is required.")
        if errors:
            self._validation_label.setText(" \u2022 ".join(errors))
            self._validation_label.setVisible(True)
            self._create_button.setEnabled(False)
        else:
            self._validation_label.setVisible(False)
            self._create_button.setEnabled(True)

    def _accept_form(self) -> None:
        class_name = self._class_name_edit.text().strip()
        root_object_name = class_name
        if root_object_name and root_object_name[0].islower():
            root_object_name = root_object_name[0].upper() + root_object_name[1:]
        self._result = NewFormRequest(
            form_class_name=class_name,
            root_widget_class=self._base_widget_combo.currentText(),
            root_object_name=root_object_name or "Form",
        )
        self.accept()
