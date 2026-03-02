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

    find_requested = Signal(str, FindOptions)
    find_next_requested = Signal()
    find_previous_requested = Signal()
    replace_requested = Signal(str)
    replace_all_requested = Signal(str)
    close_requested = Signal()

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
        outer_layout.setContentsMargins(8, 4, 8, 4)
        outer_layout.setSpacing(2)

        find_row = QWidget(self)
        find_row.setObjectName("shell.findBar.findRow")
        find_layout = QHBoxLayout(find_row)
        find_layout.setContentsMargins(0, 0, 0, 0)
        find_layout.setSpacing(4)

        self._find_input = QLineEdit(find_row)
        self._find_input.setObjectName("shell.findBar.findInput")
        self._find_input.setPlaceholderText("Find")
        self._find_input.setClearButtonEnabled(True)
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._find_input.returnPressed.connect(self._on_find_next)
        find_layout.addWidget(self._find_input, 1)

        self._match_count_label = QLabel("No results", find_row)
        self._match_count_label.setObjectName("shell.findBar.matchCount")
        self._match_count_label.setMinimumWidth(60)
        self._match_count_label.setAlignment(Qt.AlignCenter)
        find_layout.addWidget(self._match_count_label)

        self._prev_btn = QToolButton(find_row)
        self._prev_btn.setObjectName("shell.findBar.prevBtn")
        self._prev_btn.setText("\u25B2")
        self._prev_btn.setToolTip("Previous Match (Shift+F3)")
        self._prev_btn.clicked.connect(self._on_find_prev)
        find_layout.addWidget(self._prev_btn)

        self._next_btn = QToolButton(find_row)
        self._next_btn.setObjectName("shell.findBar.nextBtn")
        self._next_btn.setText("\u25BC")
        self._next_btn.setToolTip("Next Match (F3)")
        self._next_btn.clicked.connect(self._on_find_next)
        find_layout.addWidget(self._next_btn)

        self._case_btn = QToolButton(find_row)
        self._case_btn.setObjectName("shell.findBar.caseBtn")
        self._case_btn.setText("Aa")
        self._case_btn.setToolTip("Match Case")
        self._case_btn.setCheckable(True)
        self._case_btn.toggled.connect(self._on_option_changed)
        find_layout.addWidget(self._case_btn)

        self._word_btn = QToolButton(find_row)
        self._word_btn.setObjectName("shell.findBar.wordBtn")
        self._word_btn.setText("W")
        self._word_btn.setToolTip("Whole Word")
        self._word_btn.setCheckable(True)
        self._word_btn.toggled.connect(self._on_option_changed)
        find_layout.addWidget(self._word_btn)

        self._regex_btn = QToolButton(find_row)
        self._regex_btn.setObjectName("shell.findBar.regexBtn")
        self._regex_btn.setText(".*")
        self._regex_btn.setToolTip("Use Regular Expression")
        self._regex_btn.setCheckable(True)
        self._regex_btn.toggled.connect(self._on_option_changed)
        find_layout.addWidget(self._regex_btn)

        self._close_btn = QToolButton(find_row)
        self._close_btn.setObjectName("shell.findBar.closeBtn")
        self._close_btn.setText("\u2715")
        self._close_btn.setToolTip("Close (Esc)")
        self._close_btn.clicked.connect(self._on_close)
        find_layout.addWidget(self._close_btn)

        outer_layout.addWidget(find_row)

        self._replace_row = QWidget(self)
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

        outer_layout.addWidget(self._replace_row)
        self._replace_row.setVisible(False)

    def open_find(self, initial_text: str = "") -> None:
        """Show bar in find-only mode."""
        self._replace_visible = False
        self._replace_row.setVisible(False)
        self.show()
        if initial_text:
            self._find_input.setText(initial_text)
        self._find_input.setFocus()
        self._find_input.selectAll()

    def open_find_replace(self, initial_text: str = "") -> None:
        """Show bar in find-and-replace mode."""
        self._replace_visible = True
        self._replace_row.setVisible(True)
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
