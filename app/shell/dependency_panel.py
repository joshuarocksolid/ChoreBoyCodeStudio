"""Dependency inspector panel for viewing, removing, and re-auditing project dependencies."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, cast

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.project.dependency_ingest import remove_vendored_dependency
from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
    STATUS_ACTIVE,
    STATUS_REMOVED,
    DependencyEntry,
    DependencyManifest,
    load_dependency_manifest,
)


class _EmittableSignal(Protocol):
    def emit(self) -> None:
        ...


class DependencyInspectorDialog(QDialog):
    """Dialog showing project dependencies with remove and re-audit actions."""

    dependency_changed = Signal()

    def __init__(self, project_root: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project_root = project_root

        self.setWindowTitle("Project Dependencies")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.setModal(False)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel("Managed dependencies for this project:")
        header.setWordWrap(True)
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Version", "Classification", "Source", "Status"])
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QTreeWidget.SingleSelection)
        header_view = self._tree.header()
        header_view.setStretchLastSection(True)
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self._tree, stretch=1)

        button_row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove Selected")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._handle_remove)
        button_row.addWidget(self._remove_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        button_row.addWidget(refresh_btn)

        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        self._tree.itemSelectionChanged.connect(self._on_selection_changed)

    def refresh(self) -> None:
        """Reload manifest and update the tree."""
        self._tree.clear()
        manifest = load_dependency_manifest(self._project_root)
        for entry in manifest.entries:
            item = QTreeWidgetItem([
                entry.name,
                entry.version,
                _display_classification(entry.classification),
                entry.source,
                entry.status,
            ])
            item.setData(0, Qt.UserRole, entry.name)
            if entry.status == STATUS_REMOVED:
                for col in range(5):
                    item.setForeground(col, Qt.gray)
            elif entry.classification == CLASSIFICATION_NATIVE_EXTENSION:
                item.setForeground(2, Qt.darkYellow)
            self._tree.addTopLevelItem(item)
        self._remove_btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            self._remove_btn.setEnabled(False)
            return
        item = selected[0]
        status = item.text(4)
        self._remove_btn.setEnabled(status == STATUS_ACTIVE)

    def _handle_remove(self) -> None:
        selected = self._tree.selectedItems()
        if not selected:
            return
        item = selected[0]
        dep_name = item.data(0, Qt.UserRole)
        if not dep_name:
            return

        reply = QMessageBox.question(
            self,
            "Remove Dependency",
            f"Remove '{dep_name}' from the dependency manifest?\n\n"
            "Choose 'Yes' to also delete files from vendor/.\n"
            "Choose 'No' to keep vendor files but mark as removed.",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.No,
        )
        if reply == QMessageBox.Cancel:
            return

        delete_files = reply == QMessageBox.Yes
        success = remove_vendored_dependency(
            project_root=self._project_root,
            name=dep_name,
            delete_files=delete_files,
        )
        if success:
            cast(_EmittableSignal, self.dependency_changed).emit()
            self.refresh()
        else:
            QMessageBox.warning(self, "Remove Dependency", f"Could not remove '{dep_name}'.")


def _display_classification(classification: str) -> str:
    if classification == CLASSIFICATION_PURE_PYTHON:
        return "Pure Python"
    if classification == CLASSIFICATION_NATIVE_EXTENSION:
        return "Native Extension ⚠"
    return classification.replace("_", " ").title()
