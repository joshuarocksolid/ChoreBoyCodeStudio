"""Inline find/replace bar widget for the code editor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from PySide2.QtCore import Qt, Signal, QTimer
from PySide2.QtGui import QKeyEvent
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class FindOptions:
    """Encapsulates the current find option toggles."""

    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False


class FindReplaceBar(QWidget):
    """Inline find/replace bar that sits above the editor content."""

    find_requested: Any = Signal(str, FindOptions)
    find_next_requested: Any = Signal()
    find_previous_requested: Any = Signal()
    replace_requested: Any = Signal(str)
    replace_all_requested: Any = Signal(str)
    close_requested: Any = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.findBar")
        self._replace_visible = False
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(150)
        self._debounce_timer.timeout.connect(self._emit_find)
        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(8, 6, 8, 6)
        outer_layout.setSpacing(4)

        top_row = QWidget(self)
        top_row.setObjectName("shell.findBar.topRow")
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self._chevron_btn = QToolButton(top_row)
        self._chevron_btn.setObjectName("shell.findBar.chevronBtn")
        self._chevron_btn.setText("\u25B6")
        self._chevron_btn.setToolTip("Toggle Replace (Ctrl+H)")
        self._chevron_btn.setCheckable(True)
        self._chevron_btn.setFixedSize(20, 20)
        self._chevron_btn.toggled.connect(self._on_chevron_toggled)
        top_layout.addWidget(self._chevron_btn)
        top_layout.addSpacing(4)

        rows_container = QWidget(top_row)
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(4)

        find_row = QWidget(rows_container)
        find_row.setObjectName("shell.findBar.findRow")
        find_layout = QHBoxLayout(find_row)
        find_layout.setContentsMargins(0, 0, 0, 0)
        find_layout.setSpacing(2)

        self._find_input = QLineEdit(find_row)
        self._find_input.setObjectName("shell.findBar.findInput")
        self._find_input.setPlaceholderText("Find")
        self._find_input.setClearButtonEnabled(True)
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._find_input.returnPressed.connect(self._on_find_next)
        find_layout.addWidget(self._find_input, 1)

        self._match_count_label = QLabel("No results", find_row)
        self._match_count_label.setObjectName("shell.findBar.matchCount")
        self._match_count_label.setFixedHeight(22)
        self._match_count_label.setMinimumWidth(64)
        self._match_count_label.setAlignment(Qt.AlignCenter)
        find_layout.addWidget(self._match_count_label)

        find_layout.addSpacing(4)

        self._case_btn = QToolButton(find_row)
        self._case_btn.setObjectName("shell.findBar.caseBtn")
        self._case_btn.setText("Aa")
        self._case_btn.setToolTip("Match Case (Alt+C)")
        self._case_btn.setCheckable(True)
        self._case_btn.setFixedSize(24, 24)
        self._case_btn.toggled.connect(self._on_option_changed)
        find_layout.addWidget(self._case_btn)

        self._word_btn = QToolButton(find_row)
        self._word_btn.setObjectName("shell.findBar.wordBtn")
        self._word_btn.setText("W")
        self._word_btn.setToolTip("Whole Word (Alt+W)")
        self._word_btn.setCheckable(True)
        self._word_btn.setFixedSize(24, 24)
        self._word_btn.toggled.connect(self._on_option_changed)
        find_layout.addWidget(self._word_btn)

        self._regex_btn = QToolButton(find_row)
        self._regex_btn.setObjectName("shell.findBar.regexBtn")
        self._regex_btn.setText(".*")
        self._regex_btn.setToolTip("Use Regular Expression (Alt+R)")
        self._regex_btn.setCheckable(True)
        self._regex_btn.setFixedSize(24, 24)
        self._regex_btn.toggled.connect(self._on_option_changed)
        find_layout.addWidget(self._regex_btn)

        find_layout.addSpacing(6)

        nav_group = QWidget(find_row)
        nav_group.setObjectName("shell.findBar.navGroup")
        nav_layout = QHBoxLayout(nav_group)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(1)

        self._prev_btn = QToolButton(nav_group)
        self._prev_btn.setObjectName("shell.findBar.prevBtn")
        self._prev_btn.setText("\u2191")
        self._prev_btn.setToolTip("Previous Match (Shift+F3)")
        self._prev_btn.setFixedSize(24, 24)
        self._prev_btn.clicked.connect(self._on_find_prev)
        nav_layout.addWidget(self._prev_btn)

        self._next_btn = QToolButton(nav_group)
        self._next_btn.setObjectName("shell.findBar.nextBtn")
        self._next_btn.setText("\u2193")
        self._next_btn.setToolTip("Next Match (F3)")
        self._next_btn.setFixedSize(24, 24)
        self._next_btn.clicked.connect(self._on_find_next)
        nav_layout.addWidget(self._next_btn)

        find_layout.addWidget(nav_group)

        find_layout.addSpacing(4)

        self._close_btn = QToolButton(find_row)
        self._close_btn.setObjectName("shell.findBar.closeBtn")
        self._close_btn.setText("\u2715")
        self._close_btn.setToolTip("Close (Esc)")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.clicked.connect(self._on_close)
        find_layout.addWidget(self._close_btn)

        rows_layout.addWidget(find_row)

        self._replace_row = QWidget(rows_container)
        self._replace_row.setObjectName("shell.findBar.replaceRow")
        replace_layout = QHBoxLayout(self._replace_row)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.setSpacing(4)

        self._replace_input = QLineEdit(self._replace_row)
        self._replace_input.setObjectName("shell.findBar.replaceInput")
        self._replace_input.setPlaceholderText("Replace")
        self._replace_input.setClearButtonEnabled(True)
        replace_layout.addWidget(self._replace_input, 1)

        self._replace_btn = QPushButton("Replace", self._replace_row)
        self._replace_btn.setObjectName("shell.findBar.replaceBtn")
        self._replace_btn.setToolTip("Replace current match")
        self._replace_btn.clicked.connect(self._on_replace)
        replace_layout.addWidget(self._replace_btn)

        self._replace_all_btn = QPushButton("Replace All", self._replace_row)
        self._replace_all_btn.setObjectName("shell.findBar.replaceAllBtn")
        self._replace_all_btn.setToolTip("Replace all matches")
        self._replace_all_btn.clicked.connect(self._on_replace_all)
        replace_layout.addWidget(self._replace_all_btn)

        rows_layout.addWidget(self._replace_row)
        self._replace_row.setVisible(False)

        top_layout.addWidget(rows_container, 1)
        outer_layout.addWidget(top_row)

    def _on_chevron_toggled(self, checked: bool) -> None:
        self._replace_visible = checked
        self._replace_row.setVisible(checked)
        self._chevron_btn.setText("\u25BC" if checked else "\u25B6")

    def open_find(self, initial_text: str = "") -> None:
        """Show bar in find-only mode."""
        self._replace_visible = False
        self._replace_row.setVisible(False)
        self._chevron_btn.blockSignals(True)
        self._chevron_btn.setChecked(False)
        self._chevron_btn.setText("\u25B6")
        self._chevron_btn.blockSignals(False)
        self.show()
        if initial_text:
            self._find_input.setText(initial_text)
        self._find_input.setFocus()
        self._find_input.selectAll()

    def open_find_replace(self, initial_text: str = "") -> None:
        """Show bar in find-and-replace mode."""
        self._replace_visible = True
        self._replace_row.setVisible(True)
        self._chevron_btn.blockSignals(True)
        self._chevron_btn.setChecked(True)
        self._chevron_btn.setText("\u25BC")
        self._chevron_btn.blockSignals(False)
        self.show()
        if initial_text:
            self._find_input.setText(initial_text)
        self._find_input.setFocus()
        self._find_input.selectAll()

    def find_text(self) -> str:
        return self._find_input.text()

    def replace_text(self) -> str:
        return self._replace_input.text()

    def find_options(self) -> FindOptions:
        return FindOptions(
            case_sensitive=self._case_btn.isChecked(),
            whole_word=self._word_btn.isChecked(),
            regex=self._regex_btn.isChecked(),
        )

    def update_match_count(self, current: int, total: int) -> None:
        if total == 0:
            self._match_count_label.setText("No results")
        else:
            self._match_count_label.setText(f"{current}/{total}")

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self._on_close()
            event.accept()
            return
        if event.key() == Qt.Key_F3:
            if event.modifiers() & Qt.ShiftModifier:
                self._on_find_prev()
            else:
                self._on_find_next()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_find_text_changed(self, _text: str) -> None:
        self._debounce_timer.start()

    def _on_option_changed(self, _checked: bool) -> None:
        self._emit_find()

    def _emit_find(self) -> None:
        text = self._find_input.text()
        self.find_requested.emit(text, self.find_options())

    def _on_find_next(self) -> None:
        self.find_next_requested.emit()

    def _on_find_prev(self) -> None:
        self.find_previous_requested.emit()

    def _on_replace(self) -> None:
        self.replace_requested.emit(self._replace_input.text())

    def _on_replace_all(self) -> None:
        self.replace_all_requested.emit(self._replace_input.text())

    def _on_close(self) -> None:
        self.hide()
        self.close_requested.emit()
