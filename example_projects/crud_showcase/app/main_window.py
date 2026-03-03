"""Main window for the CRUD Showcase example project.

Demonstrates a range of PySide2 / Qt widgets that ChoreBoy users can reuse:
  - QTableWidget for data display
  - QLineEdit, QComboBox, QTextEdit for form input
  - QToolBar with actions
  - QStatusBar for live feedback
  - QTabWidget for multi-panel layout
  - QDialog for create/edit forms
  - QMessageBox for confirmations
  - QSplitter for resizable panels
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.freecad_probe import probe_freecad
from app.repository import Task, TaskRepository


def _project_root() -> Path:
    """Resolve project root from the entry-point location."""
    if "__file__" in dir(sys.modules["__main__"]):
        return Path(sys.modules["__main__"].__file__).resolve().parent
    return Path(os.getcwd())


class TaskDialog(QDialog):
    """Reusable dialog for creating or editing a task."""

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "New Task",
        task: Task | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)

        layout = QFormLayout(self)

        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("Task title")
        layout.addRow("Title:", self.title_edit)

        self.description_edit = QTextEdit(self)
        self.description_edit.setPlaceholderText("Optional description")
        self.description_edit.setMaximumHeight(100)
        layout.addRow("Description:", self.description_edit)

        self.status_combo = QComboBox(self)
        self.status_combo.addItems(["pending", "in_progress", "done"])
        layout.addRow("Status:", self.status_combo)

        if task is not None:
            self.title_edit.setText(task.title)
            self.description_edit.setPlainText(task.description)
            idx = self.status_combo.findText(task.status)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addRow(btn_row)

    def task_title(self) -> str:
        return self.title_edit.text().strip()

    def task_description(self) -> str:
        return self.description_edit.toPlainText().strip()

    def task_status(self) -> str:
        return self.status_combo.currentText()


class MainWindow(QMainWindow):
    """Primary application window showcasing Qt widgets + SQLite CRUD."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CRUD Showcase — ChoreBoy Example Project")
        self.resize(820, 560)

        self._repo = TaskRepository(_project_root())

        self._build_toolbar()
        self._build_central_area()
        self._build_status_bar()

        self._refresh_table()

    # ---- toolbar ----

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction("+ New Task", self._on_new_task)
        toolbar.addAction("Edit", self._on_edit_task)
        toolbar.addAction("Delete", self._on_delete_task)
        toolbar.addSeparator()
        toolbar.addAction("Refresh", self._refresh_table)
        toolbar.addSeparator()

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search tasks...")
        self._search_box.setMaximumWidth(200)
        self._search_box.textChanged.connect(self._refresh_table)
        toolbar.addWidget(self._search_box)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "pending", "in_progress", "done"])
        self._filter_combo.currentIndexChanged.connect(self._refresh_table)
        toolbar.addWidget(self._filter_combo)

    # ---- central area ----

    def _build_central_area(self) -> None:
        tabs = QTabWidget(self)

        # Tab 1: task table + detail splitter
        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Horizontal)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ID", "Title", "Status", "Description"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_edit_task)
        splitter.addWidget(self._table)

        self._detail_browser = QTextBrowser()
        self._detail_browser.setPlaceholderText("Select a task to see details.")
        splitter.addWidget(self._detail_browser)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        task_layout.addWidget(splitter)
        tabs.addTab(task_page, "Tasks")

        # Tab 2: FreeCAD probe results
        probe_page = QWidget()
        probe_layout = QVBoxLayout(probe_page)
        probe_layout.setContentsMargins(8, 8, 8, 8)

        probe_layout.addWidget(QLabel(
            "This tab demonstrates safe FreeCAD capability detection.\n"
            "Press the button below to run the probe."
        ))

        self._probe_output = QTextBrowser()
        self._probe_output.setPlaceholderText("Probe results will appear here.")
        probe_layout.addWidget(self._probe_output, 1)

        probe_btn = QPushButton("Run FreeCAD Probe")
        probe_btn.clicked.connect(self._on_run_probe)
        probe_layout.addWidget(probe_btn)

        tabs.addTab(probe_page, "FreeCAD Probe")

        # Tab 3: about / readme
        about_page = QTextBrowser()
        readme_path = _project_root() / "README.md"
        if readme_path.exists():
            about_page.setPlainText(readme_path.read_text(encoding="utf-8"))
        else:
            about_page.setPlainText("CRUD Showcase — ChoreBoy Example Project")
        tabs.addTab(about_page, "About")

        self.setCentralWidget(tabs)

    # ---- status bar ----

    def _build_status_bar(self) -> None:
        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._status_label = QLabel("")
        self._status.addPermanentWidget(self._status_label)
        self._update_status_counts()

    def _update_status_counts(self) -> None:
        counts = self._repo.count_by_status()
        text = "  |  ".join(f"{k}: {v}" for k, v in counts.items())
        self._status_label.setText(text)

    # ---- table helpers ----

    def _refresh_table(self) -> None:
        status_filter = self._filter_combo.currentText() if hasattr(self, "_filter_combo") else "All"
        if status_filter == "All":
            status_filter = ""
        search = self._search_box.text() if hasattr(self, "_search_box") else ""

        tasks = self._repo.read_all(status_filter=status_filter or None, search=search)
        self._table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            self._table.setItem(row, 0, QTableWidgetItem(str(task.task_id)))
            self._table.setItem(row, 1, QTableWidgetItem(task.title))
            self._table.setItem(row, 2, QTableWidgetItem(task.status))
            self._table.setItem(row, 3, QTableWidgetItem(task.description))

        self._update_status_counts()
        self._detail_browser.clear()

    def _selected_task(self) -> Task | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        return Task(
            task_id=int(self._table.item(row, 0).text()),
            title=self._table.item(row, 1).text(),
            status=self._table.item(row, 2).text(),
            description=self._table.item(row, 3).text(),
        )

    # ---- slots ----

    def _on_selection_changed(self) -> None:
        task = self._selected_task()
        if task is None:
            self._detail_browser.clear()
            return
        self._detail_browser.setHtml(
            f"<b>{task.title}</b><br/>"
            f"<i>Status:</i> {task.status}<br/><br/>"
            f"{task.description or '(no description)'}"
        )

    def _on_new_task(self) -> None:
        dlg = TaskDialog(self, title="New Task")
        if dlg.exec_() != QDialog.Accepted:
            return
        if not dlg.task_title():
            QMessageBox.warning(self, "Validation", "Title cannot be empty.")
            return
        self._repo.create(dlg.task_title(), dlg.task_description(), dlg.task_status())
        self._status.showMessage("Task created.", 3000)
        self._refresh_table()

    def _on_edit_task(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Edit", "Select a task first.")
            return
        dlg = TaskDialog(self, title="Edit Task", task=task)
        if dlg.exec_() != QDialog.Accepted:
            return
        if not dlg.task_title():
            QMessageBox.warning(self, "Validation", "Title cannot be empty.")
            return
        self._repo.update(task.task_id, dlg.task_title(), dlg.task_description(), dlg.task_status())
        self._status.showMessage("Task updated.", 3000)
        self._refresh_table()

    def _on_delete_task(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Delete", "Select a task first.")
            return
        answer = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete task #{task.task_id} — {task.title!r}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._repo.delete(task.task_id)
        self._status.showMessage("Task deleted.", 3000)
        self._refresh_table()

    def _on_run_probe(self) -> None:
        results = probe_freecad()
        lines = [f"<b>{key}:</b> {value}" for key, value in results.items()]
        self._probe_output.setHtml("<br/>".join(lines))
        self._status.showMessage("FreeCAD probe complete.", 3000)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._repo.close()
        super().closeEvent(event)
