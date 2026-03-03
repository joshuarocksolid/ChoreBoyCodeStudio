"""Main window for the CRUD Showcase example project.

Demonstrates a range of PySide2 / Qt widgets that ChoreBoy users can reuse:
  - QTableWidget with status-badge delegate and alternating rows
  - QStyledItemDelegate for custom cell painting
  - QLineEdit, QComboBox, QTextEdit for form input
  - QToolBar with QPainter icons
  - QStatusBar for live feedback
  - QTabWidget for multi-panel layout
  - QDialog for create/edit forms
  - QMessageBox for confirmations
  - QSplitter for resizable panels
  - Token-driven light/dark theming via QSS
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PySide2.QtCore import QRect, QSize, Qt
from PySide2.QtGui import QColor, QFont, QPainter, QPen
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
    QStyledItemDelegate,
    QStyleOptionViewItem,
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
from app.icons import (
    icon_add,
    icon_app,
    icon_delete,
    icon_edit,
    icon_gear,
    icon_info,
    icon_refresh,
    icon_tasks,
)
from app.repository import Task, TaskRepository
from app.theme import ThemeTokens, get_tokens


def _project_root() -> Path:
    """Resolve project root from the entry-point location."""
    if "__file__" in dir(sys.modules["__main__"]):
        return Path(sys.modules["__main__"].__file__).resolve().parent
    return Path(os.getcwd())


# ── Status badge colours ────────────────────────────────────────────

_STATUS_DISPLAY = {
    "done": "Done",
    "in_progress": "In Progress",
    "pending": "Pending",
}


def _status_colors(tokens: ThemeTokens, status: str) -> tuple:
    """Return (fg, bg) hex colours for a task status."""
    if status == "done":
        return tokens.status_done, tokens.status_done_bg
    if status == "in_progress":
        return tokens.status_in_progress, tokens.status_in_progress_bg
    return tokens.status_pending, tokens.status_pending_bg


# ── Custom delegate for status badge ────────────────────────────────


class StatusBadgeDelegate(QStyledItemDelegate):
    """Paints the status column as a rounded pill badge."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tokens = tokens

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        raw = index.data(Qt.DisplayRole) or ""
        label = _STATUS_DISPLAY.get(raw, raw)
        fg_hex, bg_hex = _status_colors(self._tokens, raw)

        font = painter.font()
        font.setPointSize(9)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(label) if hasattr(fm, "horizontalAdvance") else fm.width(label)
        text_height = fm.height()

        pill_h = text_height + 6
        pill_w = text_width + 18
        x = option.rect.x() + (option.rect.width() - pill_w) // 2
        y = option.rect.y() + (option.rect.height() - pill_h) // 2
        pill_rect = QRect(x, y, pill_w, pill_h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg_hex))
        painter.drawRoundedRect(pill_rect, pill_h // 2, pill_h // 2)

        painter.setPen(QColor(fg_hex))
        painter.drawText(pill_rect, Qt.AlignCenter, label)

        # Selection highlight overlay
        if option.state & 0x00000008:  # QStyle.State_Selected
            painter.setPen(Qt.NoPen)
            sel = QColor(self._tokens.row_selected)
            sel.setAlpha(80)
            painter.setBrush(sel)
            painter.drawRect(option.rect)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(110, 36)


# ── Empty state overlay ─────────────────────────────────────────────


class EmptyStateOverlay(QWidget):
    """Centered message shown when the task table is empty."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tokens = tokens
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Large plus icon
        center_x = self.width() // 2
        center_y = self.height() // 2 - 20
        icon_color = QColor(self._tokens.text_muted)
        icon_color.setAlpha(100)
        pen = QPen(icon_color, 2.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawEllipse(center_x - 20, center_y - 20, 40, 40)
        p.drawLine(center_x, center_y - 10, center_x, center_y + 10)
        p.drawLine(center_x - 10, center_y, center_x + 10, center_y)

        # Text below
        p.setPen(QColor(self._tokens.text_muted))
        font = p.font()
        font.setPointSize(12)
        p.setFont(font)
        text_rect = QRect(0, center_y + 30, self.width(), 30)
        p.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, "No tasks yet")

        font.setPointSize(10)
        p.setFont(font)
        hint_rect = QRect(0, center_y + 55, self.width(), 24)
        p.drawText(
            hint_rect,
            Qt.AlignHCenter | Qt.AlignTop,
            "Click  + New Task  to get started",
        )
        p.end()


# ── Detail card HTML builder ────────────────────────────────────────


def _detail_html(task: Task, tokens: ThemeTokens) -> str:
    """Build themed HTML for the detail browser."""
    fg, bg = _status_colors(tokens, task.status)
    label = _STATUS_DISPLAY.get(task.status, task.status)
    desc = task.description or "<span style='color:{m}'>No description</span>".format(
        m=tokens.text_muted,
    )
    return (
        f"<div style='font-family:sans-serif;'>"
        f"<h2 style='margin:0 0 8px 0; color:{tokens.text_primary};'>{task.title}</h2>"
        f"<span style='background:{bg}; color:{fg}; padding:3px 12px; "
        f"border-radius:10px; font-size:11px; font-weight:600;'>{label}</span>"
        f"<p style='margin-top:16px; color:{tokens.text_secondary}; "
        f"font-size:13px; line-height:1.6;'>{desc}</p>"
        f"<hr style='border:none; border-top:1px solid {tokens.border_light}; "
        f"margin-top:16px;'/>"
        f"<span style='color:{tokens.text_muted}; font-size:11px;'>"
        f"Task #{task.task_id}</span>"
        f"</div>"
    )


# ── Markdown-to-HTML for About tab ──────────────────────────────────


def _readme_html(text: str, tokens: ThemeTokens) -> str:
    """Very lightweight Markdown-ish to themed HTML conversion."""
    import re

    lines = text.split("\n")
    html_lines: list[str] = []
    in_code_block = False

    for line in lines:
        if line.startswith("```"):
            if in_code_block:
                html_lines.append("</pre>")
                in_code_block = False
            else:
                html_lines.append(
                    f"<pre style='background:{tokens.card_bg}; border:1px solid "
                    f"{tokens.border}; border-radius:6px; padding:12px; "
                    f"font-size:12px; color:{tokens.text_secondary}; "
                    f"overflow-x:auto;'>"
                )
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(line)
            continue

        if line.startswith("### "):
            html_lines.append(
                f"<h3 style='color:{tokens.text_primary}; margin:18px 0 6px 0; "
                f"font-size:14px;'>{line[4:]}</h3>"
            )
        elif line.startswith("## "):
            html_lines.append(
                f"<h2 style='color:{tokens.text_primary}; margin:22px 0 8px 0; "
                f"font-size:16px;'>{line[3:]}</h2>"
            )
        elif line.startswith("# "):
            html_lines.append(
                f"<h1 style='color:{tokens.accent}; margin:0 0 12px 0; "
                f"font-size:20px;'>{line[2:]}</h1>"
            )
        elif line.startswith("- "):
            content = line[2:]
            content = re.sub(
                r"`([^`]+)`",
                rf"<code style='background:{tokens.card_bg}; padding:1px 5px; "
                rf"border-radius:3px; font-size:12px; color:{tokens.accent};'>"
                r"\1</code>",
                content,
            )
            content = re.sub(
                r"\*\*([^*]+)\*\*",
                r"<b>\1</b>",
                content,
            )
            html_lines.append(
                f"<div style='margin:3px 0 3px 16px; color:{tokens.text_secondary}; "
                f"font-size:13px;'>&#8226; {content}</div>"
            )
        elif line.strip() == "":
            html_lines.append("<br/>")
        else:
            processed = re.sub(
                r"`([^`]+)`",
                rf"<code style='background:{tokens.card_bg}; padding:1px 5px; "
                rf"border-radius:3px; font-size:12px; color:{tokens.accent};'>"
                r"\1</code>",
                line,
            )
            processed = re.sub(
                r"\*\*([^*]+)\*\*",
                r"<b>\1</b>",
                processed,
            )
            html_lines.append(
                f"<span style='color:{tokens.text_secondary}; font-size:13px; "
                f"line-height:1.6;'>{processed}</span><br/>"
            )

    if in_code_block:
        html_lines.append("</pre>")

    body = "\n".join(html_lines)
    return (
        f"<div style='font-family:sans-serif; padding:8px; "
        f"max-width:680px;'>{body}</div>"
    )


# ── Probe results card ──────────────────────────────────────────────


def _probe_html(results: dict, tokens: ThemeTokens) -> str:
    rows = ""
    for key, value in results.items():
        is_positive = "Yes" in str(value) or "Created" in str(value)
        val_color = tokens.status_done if is_positive else tokens.text_secondary
        rows += (
            f"<tr>"
            f"<td style='padding:8px 12px; color:{tokens.text_muted}; "
            f"font-size:12px; font-weight:600; white-space:nowrap;'>{key}</td>"
            f"<td style='padding:8px 12px; color:{val_color}; "
            f"font-size:13px;'>{value}</td>"
            f"</tr>"
        )
    return (
        f"<div style='font-family:sans-serif;'>"
        f"<table style='border-collapse:collapse; width:100%; "
        f"background:{tokens.card_bg}; border:1px solid {tokens.border}; "
        f"border-radius:8px;'>"
        f"{rows}</table></div>"
    )


# ═══════════════════════════════════════════════════════════════════
# TaskDialog
# ═══════════════════════════════════════════════════════════════════


class TaskDialog(QDialog):
    """Modal dialog for creating or editing a task."""

    def __init__(
        self,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
        title: str = "New Task",
        task: Optional[Task] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self._tokens = tokens
        self._validation_failed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        # Header
        header = QLabel(title)
        header.setObjectName("dialogTitle")
        outer.addWidget(header)

        # Form
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("What needs to be done?")
        self.title_edit.textChanged.connect(self._clear_validation)
        form.addRow("Title:", self.title_edit)

        self.description_edit = QTextEdit(self)
        self.description_edit.setPlaceholderText("Optional details...")
        self.description_edit.setMaximumHeight(100)
        form.addRow("Description:", self.description_edit)

        self.status_combo = QComboBox(self)
        self.status_combo.addItems(["pending", "in_progress", "done"])
        form.addRow("Status:", self.status_combo)

        if task is not None:
            self.title_edit.setText(task.title)
            self.description_edit.setPlainText(task.description)
            idx = self.status_combo.findText(task.status)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

        outer.addLayout(form)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryBtn")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)

    def _on_save(self) -> None:
        if not self.title_edit.text().strip():
            self._validation_failed = True
            self.title_edit.setStyleSheet(
                f"border-color: {self._tokens.danger};"
            )
            self.title_edit.setPlaceholderText("Title cannot be empty")
            self.title_edit.setFocus()
            return
        self.accept()

    def _clear_validation(self) -> None:
        if self._validation_failed:
            self._validation_failed = False
            self.title_edit.setStyleSheet("")
            self.title_edit.setPlaceholderText("What needs to be done?")

    def task_title(self) -> str:
        return self.title_edit.text().strip()

    def task_description(self) -> str:
        return self.description_edit.toPlainText().strip()

    def task_status(self) -> str:
        return self.status_combo.currentText()


# ═══════════════════════════════════════════════════════════════════
# MainWindow
# ═══════════════════════════════════════════════════════════════════


class MainWindow(QMainWindow):
    """Primary application window showcasing Qt widgets + SQLite CRUD."""

    def __init__(self, tokens: Optional[ThemeTokens] = None):
        super().__init__()
        self._tokens = tokens or get_tokens(False)
        self.setWindowTitle("CRUD Showcase — ChoreBoy Example Project")
        self.setWindowIcon(icon_app(self._tokens.accent))
        self.resize(920, 640)
        self.setMinimumSize(720, 480)

        self._repo = TaskRepository(_project_root())

        self._build_toolbar()
        self._build_central_area()
        self._build_status_bar()

        self._refresh_table()

    # ── Toolbar ─────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Actions", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        t = self._tokens

        add_action = toolbar.addAction(icon_add(t.status_done), " New Task")
        add_action.triggered.connect(self._on_new_task)
        add_action.setToolTip("Create a new task  (Ctrl+N)")

        edit_action = toolbar.addAction(icon_edit(t.accent), " Edit")
        edit_action.triggered.connect(self._on_edit_task)
        edit_action.setToolTip("Edit the selected task")

        delete_action = toolbar.addAction(icon_delete(t.danger), " Delete")
        delete_action.triggered.connect(self._on_delete_task)
        delete_action.setToolTip("Delete the selected task")

        toolbar.addSeparator()

        refresh_action = toolbar.addAction(
            icon_refresh(t.text_muted), " Refresh"
        )
        refresh_action.triggered.connect(self._refresh_table)

        toolbar.addSeparator()

        self._search_box = QLineEdit()
        self._search_box.setObjectName("searchBox")
        self._search_box.setPlaceholderText("Search tasks...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setMaximumWidth(220)
        self._search_box.textChanged.connect(self._refresh_table)
        toolbar.addWidget(self._search_box)

        spacer = QWidget()
        spacer.setFixedWidth(6)
        toolbar.addWidget(spacer)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "pending", "in_progress", "done"])
        self._filter_combo.currentIndexChanged.connect(self._refresh_table)
        toolbar.addWidget(self._filter_combo)

    # ── Central area ────────────────────────────────────────────────

    def _build_central_area(self) -> None:
        t = self._tokens
        tabs = QTabWidget(self)

        # ─── Tab 1: Tasks ───
        task_page = QWidget()
        task_layout = QVBoxLayout(task_page)
        task_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # Table container (for overlay positioning)
        table_container = QWidget()
        table_vbox = QVBoxLayout(table_container)
        table_vbox.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Title", "Status", "Description"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Fixed
        )
        self._table.horizontalHeader().resizeSection(1, 120)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self._table.doubleClicked.connect(self._on_edit_task)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self._status_delegate = StatusBadgeDelegate(t, self._table)
        self._table.setItemDelegateForColumn(1, self._status_delegate)

        table_vbox.addWidget(self._table)

        self._empty_overlay = EmptyStateOverlay(t, self._table)

        splitter.addWidget(table_container)

        self._detail_browser = QTextBrowser()
        self._detail_browser.setOpenExternalLinks(True)
        splitter.addWidget(self._detail_browser)
        splitter.setStretchFactor(0, 65)
        splitter.setStretchFactor(1, 35)

        task_layout.addWidget(splitter)
        tabs.addTab(task_page, icon_tasks(t.accent), "  Tasks")

        # ─── Tab 2: FreeCAD Probe ───
        probe_page = QWidget()
        probe_layout = QVBoxLayout(probe_page)
        probe_layout.setContentsMargins(20, 20, 20, 20)
        probe_layout.setSpacing(16)

        probe_header = QLabel("FreeCAD Capability Probe")
        probe_header.setObjectName("dialogTitle")
        probe_layout.addWidget(probe_header)

        probe_desc = QLabel(
            "This tab demonstrates safe FreeCAD capability detection.\n"
            "The probe checks whether FreeCAD is available in the current\n"
            "runtime and attempts a headless Part::Box creation."
        )
        probe_desc.setWordWrap(True)
        probe_layout.addWidget(probe_desc)

        self._probe_output = QTextBrowser()
        self._probe_output.setPlaceholderText(
            "Press the button below to run the probe..."
        )
        probe_layout.addWidget(self._probe_output, 1)

        probe_btn_row = QHBoxLayout()
        probe_btn = QPushButton("Run FreeCAD Probe")
        probe_btn.setObjectName("probeBtn")
        probe_btn.clicked.connect(self._on_run_probe)
        probe_btn_row.addStretch()
        probe_btn_row.addWidget(probe_btn)
        probe_btn_row.addStretch()
        probe_layout.addLayout(probe_btn_row)

        tabs.addTab(probe_page, icon_gear(t.text_muted), "  FreeCAD Probe")

        # ─── Tab 3: About ───
        self._about_browser = QTextBrowser()
        self._about_browser.setOpenExternalLinks(True)
        readme_path = _project_root() / "README.md"
        if readme_path.exists():
            raw = readme_path.read_text(encoding="utf-8")
            self._about_browser.setHtml(_readme_html(raw, t))
        else:
            self._about_browser.setPlainText(
                "CRUD Showcase — ChoreBoy Example Project"
            )
        tabs.addTab(self._about_browser, icon_info(t.accent), "  About")

        self.setCentralWidget(tabs)

    # ── Status bar ──────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        self._status = QStatusBar(self)
        self.setStatusBar(self._status)
        self._status_label = QLabel("")
        self._status.addPermanentWidget(self._status_label)
        self._update_status_counts()

    def _update_status_counts(self) -> None:
        t = self._tokens
        counts = self._repo.count_by_status()
        parts = []
        color_map = {
            "done": t.status_done,
            "in_progress": t.status_in_progress,
            "pending": t.status_pending,
        }
        for status_key in ("pending", "in_progress", "done"):
            color = color_map.get(status_key, t.text_muted)
            display = _STATUS_DISPLAY.get(status_key, status_key)
            count = counts.get(status_key, 0)
            parts.append(
                f"<span style='color:{color}; font-weight:600;'>"
                f"{display}: {count}</span>"
            )
        self._status_label.setText(
            "  &middot;  ".join(parts)
        )

    # ── Table helpers ───────────────────────────────────────────────

    def _refresh_table(self) -> None:
        status_filter = (
            self._filter_combo.currentText()
            if hasattr(self, "_filter_combo")
            else "All"
        )
        if status_filter == "All":
            status_filter = ""
        search = self._search_box.text() if hasattr(self, "_search_box") else ""

        tasks = self._repo.read_all(
            status_filter=status_filter or None, search=search
        )
        self._table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            title_item = QTableWidgetItem(task.title)
            title_item.setData(Qt.UserRole, task.task_id)
            self._table.setItem(row, 0, title_item)

            status_item = QTableWidgetItem(task.status)
            self._table.setItem(row, 1, status_item)

            desc_item = QTableWidgetItem(task.description)
            self._table.setItem(row, 2, desc_item)

        self._update_status_counts()
        self._detail_browser.clear()
        self._sync_empty_overlay()

    def _sync_empty_overlay(self) -> None:
        if self._table.rowCount() == 0:
            self._empty_overlay.setGeometry(self._table.rect())
            self._empty_overlay.show()
        else:
            self._empty_overlay.hide()

    def _selected_task(self) -> Optional[Task]:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        task_id = self._table.item(row, 0).data(Qt.UserRole)
        return Task(
            task_id=int(task_id),
            title=self._table.item(row, 0).text(),
            status=self._table.item(row, 1).text(),
            description=self._table.item(row, 2).text(),
        )

    # ── Slots ───────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        task = self._selected_task()
        if task is None:
            self._detail_browser.clear()
            return
        self._detail_browser.setHtml(_detail_html(task, self._tokens))

    def _on_new_task(self) -> None:
        dlg = TaskDialog(self._tokens, self, title="New Task")
        if dlg.exec_() != QDialog.Accepted:
            return
        if not dlg.task_title():
            return
        self._repo.create(
            dlg.task_title(), dlg.task_description(), dlg.task_status()
        )
        self._status.showMessage("Task created.", 3000)
        self._refresh_table()

    def _on_edit_task(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Edit", "Select a task first.")
            return
        dlg = TaskDialog(self._tokens, self, title="Edit Task", task=task)
        if dlg.exec_() != QDialog.Accepted:
            return
        if not dlg.task_title():
            return
        self._repo.update(
            task.task_id,
            dlg.task_title(),
            dlg.task_description(),
            dlg.task_status(),
        )
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
            f"Delete task \u2014 \u201c{task.title}\u201d?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._repo.delete(task.task_id)
        self._status.showMessage("Task deleted.", 3000)
        self._refresh_table()

    def _on_run_probe(self) -> None:
        results = probe_freecad()
        self._probe_output.setHtml(_probe_html(results, self._tokens))
        self._status.showMessage("FreeCAD probe complete.", 3000)

    # ── Events ──────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_empty_overlay()

    def closeEvent(self, event) -> None:
        self._repo.close()
        super().closeEvent(event)
