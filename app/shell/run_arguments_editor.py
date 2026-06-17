"""Shared argv editor row (plain-text field, live preview, recent dropdown)."""

from __future__ import annotations

from typing import Sequence

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.shell.run_arguments_helpers import join_argv_for_display, try_parse_argv_text
from app.shell.theme_tokens import ShellThemeTokens

_ARGV_PLACEHOLDER = 'e.g. --config "/home/user/app.toml" --verbose'
_QUOTING_HINT = "Shell quoting supported"
_QUOTING_HINT_TOOLTIP = (
    'Shell-style quoting is supported.\n'
    'Example: --config "/tmp/a b/c.toml" --verbose'
)
_EMPTY_ARGV_HINT = "No arguments — runner receives an empty argv"
_RECENT_EMPTY_TOOLTIP = (
    "Recently used argument strings (global to all projects). "
    "History fills in after you run with custom arguments."
)


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
        argv_tooltip: str = "",
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setObjectName(f"{object_name_prefix}.row")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        toolbar_row = QWidget(self)
        toolbar_layout = QHBoxLayout(toolbar_row)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addStretch(1)

        self._recent_combo = QComboBox(toolbar_row)
        self._recent_combo.setObjectName(f"{object_name_prefix}.recent")
        self._recent_combo.setToolTip(_RECENT_EMPTY_TOOLTIP)
        self._recent_combo.setMaximumHeight(28)
        self._recent_combo.activated[int].connect(self._on_recent_argv_selected)
        self._populate_recent(recent_argv_history)
        self._recent_combo.setVisible(show_recent)
        toolbar_layout.addWidget(self._recent_combo, 0)
        if show_recent:
            layout.addWidget(toolbar_row)

        self._argv_edit = QPlainTextEdit(self)
        self._argv_edit.setObjectName(f"{object_name_prefix}.argv")
        self._argv_edit.setPlaceholderText(_ARGV_PLACEHOLDER)
        self._argv_edit.setTabChangesFocus(True)
        self._argv_edit.setMinimumHeight(72)
        self._argv_edit.setMaximumHeight(120)
        if argv_tooltip:
            self._argv_edit.setToolTip(argv_tooltip)
        self._argv_edit.textChanged.connect(self._emit_validation_changed)
        layout.addWidget(self._argv_edit, 0)

        hints_row = QWidget(self)
        hints_layout = QHBoxLayout(hints_row)
        hints_layout.setContentsMargins(0, 0, 0, 0)
        hints_layout.setSpacing(8)

        self._argv_preview_label = QLabel(hints_row)
        self._argv_preview_label.setObjectName(f"{object_name_prefix}.argvPreview")
        self._argv_preview_label.setWordWrap(True)
        self._argv_preview_label.setProperty("previewLabel", True)
        hints_layout.addWidget(self._argv_preview_label, 1)

        self._quoting_hint_label = QLabel(_QUOTING_HINT, hints_row)
        self._quoting_hint_label.setObjectName(f"{object_name_prefix}.quotingHint")
        self._quoting_hint_label.setProperty("quotingHint", True)
        self._quoting_hint_label.setToolTip(_QUOTING_HINT_TOOLTIP)
        self._quoting_hint_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hints_layout.addWidget(self._quoting_hint_label, 0)

        layout.addWidget(hints_row)

        self._argv_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._update_argv_preview()

    def argv_text(self) -> str:
        return self._argv_edit.toPlainText()

    def argv_parse_error(self) -> str | None:
        text = self.argv_text()
        if not text.strip():
            return None
        _tokens, error = try_parse_argv_text(text)
        return error

    def set_argv_text(self, text: str) -> None:
        self._argv_edit.setPlainText(text)
        self._update_argv_preview()

    def set_argv_from_tokens(self, argv: Sequence[str]) -> None:
        self.set_argv_text(join_argv_for_display(argv))

    def focus_argv_field(self) -> None:
        self._argv_edit.setFocus()

    def recent_combo_widget(self) -> QComboBox:
        return self._recent_combo

    def parsed_preview_line(self) -> str:
        return self._argv_preview_label.text()

    def set_argv_validation_error(self, *, error: bool) -> None:
        state = "error" if error else "ok"
        if self._argv_edit.property("validationState") != state:
            self._argv_edit.setProperty("validationState", state)
            self._argv_edit.style().unpolish(self._argv_edit)
            self._argv_edit.style().polish(self._argv_edit)

    def _populate_recent(self, recent_argv_history: Sequence[str]) -> None:
        self._recent_combo.clear()
        self._recent_combo.addItem("Recent\u2026", "")
        for entry in recent_argv_history:
            display = entry if len(entry) <= 80 else f"{entry[:77]}..."
            self._recent_combo.addItem(display, entry)
        self._recent_combo.setCurrentIndex(0)
        has_history = self._recent_combo.count() > 1
        self._recent_combo.setEnabled(has_history)
        if has_history:
            self._recent_combo.setToolTip(
                "Recently used argument strings (global to all projects)."
            )
        else:
            self._recent_combo.setToolTip(_RECENT_EMPTY_TOOLTIP)

    def _on_recent_argv_selected(self, _index: int) -> None:
        data = self._recent_combo.currentData()
        if isinstance(data, str) and data:
            self.set_argv_text(data)
        self._recent_combo.setCurrentIndex(0)

    def _emit_validation_changed(self) -> None:
        self._update_argv_preview()
        self.validation_changed.emit()

    def _set_preview_state(self, state: str) -> None:
        if self._argv_preview_label.property("previewState") != state:
            self._argv_preview_label.setProperty("previewState", state)
            self._argv_preview_label.style().unpolish(self._argv_preview_label)
            self._argv_preview_label.style().polish(self._argv_preview_label)

    def _update_argv_preview(self) -> None:
        text = self.argv_text()
        if not text.strip():
            self._argv_preview_label.setText(_EMPTY_ARGV_HINT)
            self._argv_preview_label.setToolTip("")
            self._set_preview_state("ok")
            self.set_argv_validation_error(error=False)
            return

        tokens, error = try_parse_argv_text(text)
        if error is not None:
            self._argv_preview_label.setText(f"Cannot parse — {error}")
            self._argv_preview_label.setToolTip("")
            self._set_preview_state("error")
            self.set_argv_validation_error(error=True)
            return

        count = len(tokens or [])
        suffix = "argument" if count == 1 else "arguments"
        self._argv_preview_label.setText(f"{count} {suffix}")
        preview = ", ".join(repr(token) for token in tokens or [])
        self._argv_preview_label.setToolTip(preview if preview else "")
        self._set_preview_state("ok")
        self.set_argv_validation_error(error=False)
