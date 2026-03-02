"""VS Code-style Problems panel widget.

Groups diagnostics by file, provides severity filter toggles, and
renders distinct severity icons (circle/triangle/info-dot).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide2.QtCore import QPoint, Qt, Signal
from PySide2.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygon
from PySide2.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QSizePolicy,
    QStackedLayout,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity
from app.run.problem_parser import ProblemEntry

if TYPE_CHECKING:
    from PySide2.QtCore import QPoint

ROLE_FILE_PATH = 320
ROLE_LINE_NUMBER = 321
ROLE_DIAGNOSTIC_CODE = 322


@dataclass(frozen=True)
class ResultItem:
    """Generic navigable result for references, outline, search, etc."""

    label: str
    file_path: str
    line_number: int
    detail: str = ""
    tooltip: str = ""


# ---------------------------------------------------------------------------
# Severity icon helpers
# ---------------------------------------------------------------------------

_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def _make_error_icon(color_hex: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 10, 10)
    p.end()
    return QIcon(pixmap)


def _make_warning_icon(color_hex: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.NoPen)
    triangle = QPolygon()
    triangle.append(QPoint(7, 1))
    triangle.append(QPoint(13, 13))
    triangle.append(QPoint(1, 13))
    p.drawPolygon(triangle)
    p.end()
    return QIcon(pixmap)


def _make_info_icon(color_hex: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor(color_hex)
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 10, 10)
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(6, 4, 2, 2)
    p.drawRect(6, 7, 2, 4)
    p.end()
    return QIcon(pixmap)


def severity_icon(severity: DiagnosticSeverity | str, color_hex: str) -> QIcon:
    key = (str(severity), color_hex)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    sev = str(severity)
    if sev == DiagnosticSeverity.WARNING or sev == "warning":
        icon = _make_warning_icon(color_hex)
    elif sev == DiagnosticSeverity.INFO or sev == "info":
        icon = _make_info_icon(color_hex)
    else:
        icon = _make_error_icon(color_hex)
    _ICON_CACHE[key] = icon
    return icon


_FILE_ICON_CACHE: dict[str, QIcon] = {}


def _file_group_icon(color_hex: str) -> QIcon:
    cached = _FILE_ICON_CACHE.get(color_hex)
    if cached is not None:
        return cached
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    c.setAlpha(180)
    p.setPen(c)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(1, 1, 12, 12, 2, 2)
    p.drawLine(1, 5, 13, 5)
    p.end()
    icon = QIcon(pixmap)
    _FILE_ICON_CACHE[color_hex] = icon
    return icon


# ---------------------------------------------------------------------------
# Filter toggle button
# ---------------------------------------------------------------------------


class _FilterToggle(QToolButton):
    """Small toggle button showing severity label + count badge."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_label = label
        self._count = 0
        self.setCheckable(True)
        self.setChecked(True)
        self.setAutoRaise(True)
        self._refresh_text()

    def set_count(self, count: int) -> None:
        self._count = count
        self._refresh_text()

    def count(self) -> int:
        return self._count

    def _refresh_text(self) -> None:
        self.setText(f"{self._base_label}: {self._count}")


# ---------------------------------------------------------------------------
# ProblemsPanel
# ---------------------------------------------------------------------------


class ProblemsPanel(QWidget):
    """VS Code-style problems panel with grouped tree and filter toolbar."""

    item_activated = Signal(str, int)
    context_menu_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.problemsPanel")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # -- filter toolbar --
        self._toolbar = QWidget(self)
        self._toolbar.setObjectName("shell.problemsPanel.toolbar")
        toolbar_layout = QHBoxLayout(self._toolbar)
        toolbar_layout.setContentsMargins(6, 2, 6, 2)
        toolbar_layout.setSpacing(6)

        self._source_label = QLabel("", self._toolbar)
        self._source_label.setObjectName("shell.problemsPanel.sourceLabel")
        toolbar_layout.addWidget(self._source_label)

        toolbar_layout.addStretch()

        self._error_toggle = _FilterToggle("Errors", self._toolbar)
        self._error_toggle.setObjectName("shell.problemsPanel.filterErrors")
        self._error_toggle.toggled.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self._error_toggle)

        self._warning_toggle = _FilterToggle("Warnings", self._toolbar)
        self._warning_toggle.setObjectName("shell.problemsPanel.filterWarnings")
        self._warning_toggle.toggled.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self._warning_toggle)

        self._info_toggle = _FilterToggle("Info", self._toolbar)
        self._info_toggle.setObjectName("shell.problemsPanel.filterInfo")
        self._info_toggle.toggled.connect(self._on_filter_changed)
        toolbar_layout.addWidget(self._info_toggle)

        root_layout.addWidget(self._toolbar)

        # -- stacked layout: tree or empty state --
        self._stack_container = QWidget(self)
        self._stack_layout = QStackedLayout(self._stack_container)
        self._stack_layout.setContentsMargins(0, 0, 0, 0)

        self._tree = QTreeWidget(self._stack_container)
        self._tree.setObjectName("shell.problemsPanel.tree")
        self._tree.setHeaderLabels(["", "Description", "Location", "Code"])
        self._tree.setColumnWidth(0, 24)
        self._tree.setColumnWidth(3, 60)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setAlternatingRowColors(False)
        self._tree.setExpandsOnDoubleClick(False)
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tree.itemActivated.connect(self._on_item_activated)
        self._tree.itemDoubleClicked.connect(self._on_item_activated)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._stack_layout.addWidget(self._tree)

        self._empty_label = QLabel("No problems detected.", self._stack_container)
        self._empty_label.setObjectName("shell.problemsPanel.emptyLabel")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._stack_layout.addWidget(self._empty_label)

        root_layout.addWidget(self._stack_container, 1)

        # -- internal state --
        self._current_mode = "diagnostics"
        self._diagnostics: list[CodeDiagnostic] = []
        self._runtime_problems: list[ProblemEntry] = []
        self._total_count = 0
        self._quick_fixes_enabled = False
        self._severity_colors = {
            DiagnosticSeverity.ERROR: "#E03131",
            DiagnosticSeverity.WARNING: "#D97706",
            DiagnosticSeverity.INFO: "#3366FF",
        }

    # -- public API --

    def set_severity_colors(
        self,
        error: str,
        warning: str,
        info: str,
    ) -> None:
        self._severity_colors = {
            DiagnosticSeverity.ERROR: error,
            DiagnosticSeverity.WARNING: warning,
            DiagnosticSeverity.INFO: info,
        }

    def set_quick_fixes_enabled(self, enabled: bool) -> None:
        self._quick_fixes_enabled = enabled

    def set_diagnostics(
        self,
        diagnostics: list[CodeDiagnostic],
        runtime_problems: list[ProblemEntry] | None = None,
    ) -> None:
        self._current_mode = "diagnostics"
        self._diagnostics = list(diagnostics)
        self._runtime_problems = list(runtime_problems) if runtime_problems else []
        self._source_label.setText("Problems")
        self._toolbar.setVisible(True)
        self._rebuild_diagnostics_tree()

    def set_results(self, title: str, items: list[ResultItem]) -> None:
        self._current_mode = "results"
        self._diagnostics = []
        self._runtime_problems = []
        self._source_label.setText(title)
        self._toolbar.setVisible(True)
        self._error_toggle.setVisible(False)
        self._warning_toggle.setVisible(False)
        self._info_toggle.setVisible(False)
        self._rebuild_results_tree(items)

    def clear(self) -> None:
        self._diagnostics = []
        self._runtime_problems = []
        self._total_count = 0
        self._tree.clear()
        self._error_toggle.set_count(0)
        self._warning_toggle.set_count(0)
        self._info_toggle.set_count(0)
        self._source_label.setText("")
        self._stack_layout.setCurrentWidget(self._empty_label)

    def problem_count(self) -> int:
        return self._total_count

    def tree_widget(self) -> QTreeWidget:
        return self._tree

    # -- internal rendering --

    def _rebuild_diagnostics_tree(self) -> None:
        self._tree.clear()
        self._error_toggle.setVisible(True)
        self._warning_toggle.setVisible(True)
        self._info_toggle.setVisible(True)

        show_errors = self._error_toggle.isChecked()
        show_warnings = self._warning_toggle.isChecked()
        show_info = self._info_toggle.isChecked()

        counts = {DiagnosticSeverity.ERROR: 0, DiagnosticSeverity.WARNING: 0, DiagnosticSeverity.INFO: 0}

        groups: dict[str, list[tuple[str, CodeDiagnostic | ProblemEntry]]] = {}

        for d in self._diagnostics:
            sev = d.severity
            if sev in counts:
                counts[sev] += 1
            visible = (
                (sev == DiagnosticSeverity.ERROR and show_errors)
                or (sev == DiagnosticSeverity.WARNING and show_warnings)
                or (sev == DiagnosticSeverity.INFO and show_info)
            )
            if visible:
                groups.setdefault(d.file_path, []).append(("lint", d))

        for rp in self._runtime_problems:
            counts[DiagnosticSeverity.ERROR] += 1
            if show_errors:
                groups.setdefault(rp.file_path, []).append(("runtime", rp))

        self._error_toggle.set_count(counts[DiagnosticSeverity.ERROR])
        self._warning_toggle.set_count(counts[DiagnosticSeverity.WARNING])
        self._info_toggle.set_count(counts[DiagnosticSeverity.INFO])

        total_visible = 0
        self._total_count = sum(counts.values())

        icon_color = self._severity_colors.get(DiagnosticSeverity.INFO, "#3366FF")
        for file_path in sorted(groups.keys()):
            items = groups[file_path]
            file_name = Path(file_path).name
            group_node = QTreeWidgetItem(self._tree)
            group_node.setText(1, f"{file_name}  ({len(items)})")
            group_node.setIcon(0, _file_group_icon(icon_color))
            group_node.setData(0, ROLE_FILE_PATH, file_path)
            group_node.setToolTip(1, file_path)
            group_node.setFlags(group_node.flags() & ~Qt.ItemIsSelectable)

            for kind, entry in items:
                child = QTreeWidgetItem(group_node)
                if kind == "lint":
                    assert isinstance(entry, CodeDiagnostic)
                    color_hex = self._severity_colors.get(entry.severity, "#3366FF")
                    child.setIcon(0, severity_icon(entry.severity, color_hex))
                    child.setText(1, entry.message)
                    child.setForeground(1, QColor(color_hex))
                    child.setText(2, f"Ln {entry.line_number}")
                    child.setText(3, entry.code)
                    child.setToolTip(1, entry.file_path)
                    child.setData(0, ROLE_FILE_PATH, entry.file_path)
                    child.setData(0, ROLE_LINE_NUMBER, entry.line_number)
                    child.setData(0, ROLE_DIAGNOSTIC_CODE, entry.code)
                else:
                    assert isinstance(entry, ProblemEntry)
                    color_hex = self._severity_colors.get(DiagnosticSeverity.ERROR, "#E03131")
                    child.setIcon(0, severity_icon(DiagnosticSeverity.ERROR, color_hex))
                    msg = f"{entry.context} | {entry.message}" if entry.context else entry.message
                    child.setText(1, msg)
                    child.setForeground(1, QColor(color_hex))
                    child.setText(2, f"Ln {entry.line_number}")
                    child.setText(3, "runtime")
                    child.setToolTip(1, entry.file_path)
                    child.setData(0, ROLE_FILE_PATH, entry.file_path)
                    child.setData(0, ROLE_LINE_NUMBER, entry.line_number)
                total_visible += 1

            group_node.setExpanded(True)

        if total_visible > 0:
            self._stack_layout.setCurrentWidget(self._tree)
        else:
            self._empty_label.setText("No problems detected.")
            self._stack_layout.setCurrentWidget(self._empty_label)

    def _rebuild_results_tree(self, items: list[ResultItem]) -> None:
        self._tree.clear()
        self._total_count = len(items)

        if not items:
            self._empty_label.setText(f"No results found.")
            self._stack_layout.setCurrentWidget(self._empty_label)
            return

        groups: dict[str, list[ResultItem]] = {}
        for item in items:
            groups.setdefault(item.file_path, []).append(item)

        for file_path in sorted(groups.keys()):
            result_items = groups[file_path]
            file_name = Path(file_path).name
            group_node = QTreeWidgetItem(self._tree)
            group_node.setText(1, f"{file_name}  ({len(result_items)})")
            group_node.setData(0, ROLE_FILE_PATH, file_path)
            group_node.setToolTip(1, file_path)
            group_node.setFlags(group_node.flags() & ~Qt.ItemIsSelectable)

            for ri in result_items:
                child = QTreeWidgetItem(group_node)
                child.setText(1, ri.label)
                child.setText(2, f"Ln {ri.line_number}")
                if ri.detail:
                    child.setText(3, ri.detail)
                if ri.tooltip:
                    child.setToolTip(1, ri.tooltip)
                else:
                    child.setToolTip(1, ri.file_path)
                child.setData(0, ROLE_FILE_PATH, ri.file_path)
                child.setData(0, ROLE_LINE_NUMBER, ri.line_number)

            group_node.setExpanded(True)

        self._stack_layout.setCurrentWidget(self._tree)

    # -- signals / slots --

    def _on_filter_changed(self) -> None:
        if self._current_mode == "diagnostics":
            self._rebuild_diagnostics_tree()

    def _on_item_activated(self, item: QTreeWidgetItem) -> None:
        file_path = item.data(0, ROLE_FILE_PATH)
        line_number = item.data(0, ROLE_LINE_NUMBER)
        if not file_path or line_number is None:
            return
        try:
            resolved_line = int(line_number)
        except (TypeError, ValueError):
            return
        self.item_activated.emit(str(file_path), resolved_line)

    def _on_context_menu(self, position: "QPoint") -> None:
        item = self._tree.itemAt(position)
        if item is None:
            return
        diag_code = item.data(0, ROLE_DIAGNOSTIC_CODE)
        file_path = item.data(0, ROLE_FILE_PATH)
        if not file_path:
            return
        if not self._quick_fixes_enabled:
            return
        if diag_code not in {"PY220", "PY221", "PY200"}:
            return
        menu = QMenu(self)
        action = menu.addAction("Apply Safe Fixes for File")
        chosen = menu.exec_(self._tree.viewport().mapToGlobal(position))
        if chosen == action:
            self.context_menu_requested.emit(str(file_path), str(diag_code))
