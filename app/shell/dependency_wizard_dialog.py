"""Add Dependency wizard dialog for terminal-free package management."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.project.dependency_ingest import (
    IngestResult,
    classify_package_path,
    ingest_folder,
    ingest_wheel,
    ingest_zip,
)
from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
)


class AddDependencyWizardDialog(QDialog):
    """Wizard dialog for adding a dependency from a local file or folder."""

    def __init__(self, project_root: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project_root = project_root
        self._selected_path: str = ""
        self._last_result: Optional[IngestResult] = None

        self.setWindowTitle("Add Dependency")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui()

    @property
    def last_result(self) -> Optional[IngestResult]:
        return self._last_result

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Instructions
        instructions = QLabel(
            "Select a Python package file (.whl, .zip) or folder to add as a project dependency.\n"
            "The package will be extracted into your project's vendor/ directory."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Source path row
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("No file or folder selected")
        path_row.addWidget(self._path_edit, stretch=1)

        browse_file_btn = QPushButton("Browse File…")
        browse_file_btn.clicked.connect(self._browse_file)
        path_row.addWidget(browse_file_btn)

        browse_folder_btn = QPushButton("Browse Folder…")
        browse_folder_btn.clicked.connect(self._browse_folder)
        path_row.addWidget(browse_folder_btn)
        layout.addLayout(path_row)

        # Name override row
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Package name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("(auto-detected from filename)")
        name_row.addWidget(self._name_edit, stretch=1)
        layout.addLayout(name_row)

        # Classification preview
        self._classification_label = QLabel("")
        self._classification_label.setWordWrap(True)
        layout.addWidget(self._classification_label)

        # Warning area for native extensions
        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #b85c00;")
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        self._add_btn = QPushButton("Add Dependency")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._do_ingest)
        button_row.addWidget(self._add_btn)
        layout.addLayout(button_row)

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Package File",
            str(Path.home()),
            "Python Packages (*.whl *.zip);;All Files (*)",
        )
        if path:
            self._set_selected_path(path)

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Package Folder",
            str(Path.home()),
        )
        if path:
            self._set_selected_path(path)

    def _set_selected_path(self, path: str) -> None:
        self._selected_path = path
        self._path_edit.setText(path)
        self._add_btn.setEnabled(True)
        self._update_classification_preview()

    def _update_classification_preview(self) -> None:
        source = Path(self._selected_path)
        classification = classify_package_path(source)

        if classification == CLASSIFICATION_NATIVE_EXTENSION:
            self._classification_label.setText(
                f"Classification: <b>Native Extension</b> — contains compiled files (.so/.pyd)"
            )
            self._warning_label.setText(
                "⚠ This package contains native extensions that may not be compatible with "
                "ChoreBoy's runtime. Proceed only if you have verified compatibility."
            )
            self._warning_label.setVisible(True)
        else:
            self._classification_label.setText(
                f"Classification: <b>Pure Python</b> — no compiled extensions detected"
            )
            self._warning_label.setVisible(False)

    def _do_ingest(self) -> None:
        source = Path(self._selected_path)
        name_override = self._name_edit.text().strip() or None

        if source.is_file() and source.suffix == ".whl":
            result = ingest_wheel(
                project_root=self._project_root,
                wheel_path=str(source),
                name=name_override,
            )
        elif source.is_file() and source.suffix == ".zip":
            if not name_override:
                QMessageBox.warning(self, "Add Dependency", "Please provide a package name for zip archives.")
                return
            result = ingest_zip(
                project_root=self._project_root,
                zip_path=str(source),
                name=name_override,
            )
        elif source.is_dir():
            result = ingest_folder(
                project_root=self._project_root,
                folder_path=str(source),
                name=name_override,
            )
        else:
            QMessageBox.warning(
                self,
                "Add Dependency",
                "Unsupported source type. Please select a .whl file, .zip file, or folder.",
            )
            return

        self._last_result = result
        if result.success:
            self.accept()
        else:
            QMessageBox.warning(self, "Add Dependency", f"Ingestion failed: {result.message}")
