"""Copyable before/after text after Adopt this form. The dialog writes nothing."""

from __future__ import annotations

from app.qt.QtCore import QTimer
from app.qt.QtGui import QFont
from app.qt.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import exec_qt

from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT, UI_EDITOR_FONT_SIZE_DEFAULT
from app.shell.theme_tokens import ShellThemeTokens

_DEFAULT_HINT = "Your own Python is not changed. Copy these lines into your window class."


def adoption_hint(generated_relative: str, window_relative: str) -> str:
    """Status sentence for one adopt, using the paths Adopt actually wrote."""
    return (
        "Adopting wrote %s and %s. Your own Python is not changed. "
        "Copy these lines into your window class."
    ) % (generated_relative, window_relative)


def adopt_dialog_style(tokens: ShellThemeTokens) -> str:
    """Stylesheet for the suggestion dialog. Colors come from the shell tokens."""
    width = tokens.focus_border_width
    return (
        "QDialog#formBuilder\\.adoptDialog {"
        f" background: {tokens.panel_bg}; color: {tokens.text_primary}; }}"
        "QLabel#formBuilder\\.adoptHint, QLabel#formBuilder\\.adoptTitle {"
        f" color: {tokens.text_primary}; background: transparent; }}"
        "QPlainTextEdit#formBuilder\\.adoptBefore, QPlainTextEdit#formBuilder\\.adoptAfter {"
        f" background: {tokens.editor_bg}; color: {tokens.text_primary};"
        f" border: 1px solid {tokens.border}; }}"
        "QPlainTextEdit#formBuilder\\.adoptBefore:focus, QPlainTextEdit#formBuilder\\.adoptAfter:focus {"
        f" border: {width}px solid {tokens.accent}; }}"
        "QPushButton {"
        f" background: {tokens.input_bg}; color: {tokens.text_primary};"
        f" border: 1px solid {tokens.border}; padding: 2px 8px; }}"
        "QPushButton:focus {"
        f" border: {width}px solid {tokens.accent}; }}"
    )


class AdoptDialog(QDialog):
    """Shows the loader call and the setupUi text the user can paste."""

    def __init__(
        self,
        *,
        before: str,
        after: str,
        tokens: ShellThemeTokens,
        hint: str = _DEFAULT_HINT,
        editor_font: tuple[str, int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.adoptDialog")
        self.setWindowTitle("Adopt this form")
        self.resize(720, 480)
        family = UI_EDITOR_FONT_FAMILY_DEFAULT
        size = UI_EDITOR_FONT_SIZE_DEFAULT
        if editor_font is not None:
            family, size = editor_font
        self._editor_family = family or UI_EDITOR_FONT_FAMILY_DEFAULT
        self._editor_size = size or UI_EDITOR_FONT_SIZE_DEFAULT
        outer = QVBoxLayout(self)
        hint_label = QLabel(hint, self)
        hint_label.setObjectName("formBuilder.adoptHint")
        hint_label.setWordWrap(True)
        outer.addWidget(hint_label)
        _before_pane, self._before_edit = self._pane(
            "Current call",
            before,
            "formBuilder.adoptBefore",
            "formBuilder.adopt.copyBefore",
            "Copy current call",
            "Current call",
        )
        after_pane, self._after_edit = self._pane(
            "Paste this",
            after,
            "formBuilder.adoptAfter",
            "formBuilder.adopt.copyAfter",
            "Copy setupUi lines",
            "Paste this",
        )
        outer.addWidget(_before_pane)
        outer.addWidget(after_pane)
        self._paste_copy = self.findChild(QPushButton, "formBuilder.adopt.copyAfter")
        buttons = QDialogButtonBox(self)
        close = buttons.addButton(QDialogButtonBox.Close)
        close.clicked.connect(self.accept)
        if close is not None:
            close.setDefault(True)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        outer.addLayout(row)
        self.apply_theme(tokens)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(adopt_dialog_style(tokens))
        self._apply_editor_font()

    def showEvent(self, event):  # type: ignore[no-untyped-def]
        super().showEvent(event)
        QTimer.singleShot(0, self._focus_paste_copy)

    def _focus_paste_copy(self) -> None:
        if self._paste_copy is not None:
            self._paste_copy.setFocus()

    def _apply_editor_font(self) -> None:
        font = QFont(self._editor_family)
        font.setPointSize(max(8, int(self._editor_size)))
        for edit in (self._before_edit, self._after_edit):
            edit.setFont(font)

    def _pane(
        self,
        title: str,
        text: str,
        edit_name: str,
        button_name: str,
        accessible_name: str,
        editor_name: str,
    ) -> tuple[QWidget, QPlainTextEdit]:
        frame = QWidget(self)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        label = QLabel(title, frame)
        label.setObjectName("formBuilder.adoptTitle")
        header.addWidget(label, 1)
        copy = QPushButton("Copy", frame)
        copy.setObjectName(button_name)
        copy.setAccessibleName(accessible_name)
        header.addWidget(copy)
        layout.addLayout(header)
        edit = QPlainTextEdit(text, frame)
        edit.setObjectName(edit_name)
        edit.setAccessibleName(editor_name)
        edit.setReadOnly(True)
        label.setBuddy(edit)
        layout.addWidget(edit)
        copy.clicked.connect(lambda: self._copy(edit.toPlainText()))
        return frame, edit

    def _copy(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)


def show_adopt_dialog(
    parent: QWidget,
    *,
    before: str,
    after: str,
    tokens: ShellThemeTokens,
    hint: str = _DEFAULT_HINT,
    editor_font: tuple[str, int] | None = None,
) -> None:
    dialog = AdoptDialog(
        before=before,
        after=after,
        tokens=tokens,
        hint=hint,
        editor_font=editor_font,
        parent=parent,
    )
    exec_qt(dialog)
