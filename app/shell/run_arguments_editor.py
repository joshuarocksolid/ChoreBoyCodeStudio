"""Shared argv editor row (plain-text field, live preview, recent dropdown)."""

from __future__ import annotations

from typing import Sequence

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.shell.run_arguments_helpers import try_parse_argv_text
from app.shell.run_arguments_helpers import join_argv_for_display
from app.shell.theme_tokens import ShellThemeTokens


class RunArgumentsEditorRow(QWidget):
    """Arguments field with shlex preview and optional recent-argv picker."""

    validation_changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tokens: ShellThemeTokens,
        recent_argv_history: Sequence[str] = (),
        object_name_prefix: str = "shell.runArgumentsEditor",
        show_recent: bool = True,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setObjectName(f"{object_name_prefix}.row")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        argv_row = QWidget(self)
        argv_row_layout = QHBoxLayout(argv_row)
        argv_row_layout.setContentsMargins(0, 0, 0, 0)
        argv_row_layout.setSpacing(8)

        self._argv_edit = QPlainTextEdit(argv_row)
        self._argv_edit.setObjectName(f"{object_name_prefix}.argv")
        self._argv_edit.setPlaceholderText(
            'e.g. --config "/home/user/app.toml" --verbose'
        )
        self._argv_edit.setTabChangesFocus(True)
        self._argv_edit.setMaximumHeight(72)
        self._argv_edit.textChanged.connect(self._emit_validation_changed)
        argv_row_layout.addWidget(self._argv_edit, 1)

        self._recent_combo = QComboBox(argv_row)
        self._recent_combo.setObjectName(f"{object_name_prefix}.recent")
        self._recent_combo.setToolTip("Recently used argument strings (global to all projects).")
        self._recent_combo.activated[int].connect(self._on_recent_argv_selected)
        self._populate_recent(recent_argv_history)
        self._recent_combo.setVisible(show_recent)
        argv_row_layout.addWidget(self._recent_combo, 0)

        layout.addWidget(argv_row)

        self._argv_preview_label = QLabel(self)
        self._argv_preview_label.setObjectName(f"{object_name_prefix}.argvPreview")
        self._argv_preview_label.setWordWrap(True)
        muted_color = tokens.text_muted or tokens.text_primary
        self._argv_preview_label.setProperty("previewLabel", True)
        self._argv_preview_label.setStyleSheet(f"color: {muted_color};")
        layout.addWidget(self._argv_preview_label)

        self._update_argv_preview()

    def argv_text(self) -> str:
        return self._argv_edit.toPlainText()

    def set_argv_text(self, text: str) -> None:
        self._argv_edit.setPlainText(text)
        self._update_argv_preview()

    def set_argv_from_tokens(self, argv: Sequence[str]) -> None:
        self.set_argv_text(join_argv_for_display(argv))

    def focus_argv_field(self) -> None:
        self._argv_edit.setFocus()

    def parsed_preview_line(self) -> str:
        return self._argv_preview_label.text()

    def _populate_recent(self, recent_argv_history: Sequence[str]) -> None:
        self._recent_combo.clear()
        self._recent_combo.addItem("Pick recent…", "")
        for entry in recent_argv_history:
            display = entry if len(entry) <= 80 else f"{entry[:77]}..."
            self._recent_combo.addItem(display, entry)
        self._recent_combo.setCurrentIndex(0)
        self._recent_combo.setEnabled(self._recent_combo.count() > 1)

    def _on_recent_argv_selected(self, _index: int) -> None:
        data = self._recent_combo.currentData()
        if isinstance(data, str) and data:
            self.set_argv_text(data)
        self._recent_combo.setCurrentIndex(0)

    def _emit_validation_changed(self) -> None:
        self._update_argv_preview()
        self.validation_changed.emit()

    def _update_argv_preview(self) -> None:
        text = self.argv_text()
        if not text.strip():
            self._argv_preview_label.setText(
                "Parsed argv: (empty) — entry file will receive an empty argv list."
            )
            return
        tokens, error = try_parse_argv_text(text)
        if error is not None:
            self._argv_preview_label.setText(f"Parsed argv: (unable to parse — {error})")
            return
        preview = ", ".join(repr(token) for token in tokens or []) or "<empty>"
        self._argv_preview_label.setText(f"Parsed argv: [{preview}]")
