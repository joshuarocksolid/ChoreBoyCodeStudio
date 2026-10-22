"""Copyable before/after text for Adopt this form. User files stay untouched."""

from __future__ import annotations

from app.qt.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import exec_qt

from app.shell.theme_tokens import ShellThemeTokens


def adopt_dialog_style(tokens: ShellThemeTokens) -> str:
    """Stylesheet for the suggestion dialog. Colors come from the shell tokens."""
    width = tokens.focus_border_width
    return (
        "QDialog#formBuilder\\.adoptDialog {"
        f" background: {tokens.panel_bg}; color: {tokens.text_primary}; }}"
        "QLabel#formBuilder\\.adoptHint {"
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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.adoptDialog")
        self.setWindowTitle("Adopt this form")
        self.resize(720, 480)
        outer = QVBoxLayout(self)
        hint = QLabel(
            "Copy the setupUi lines into your window class. This does not change your files.",
            self,
        )
        hint.setObjectName("formBuilder.adoptHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        outer.addWidget(self._pane("Current call", before, "formBuilder.adoptBefore", "formBuilder.adopt.copyBefore"))
        outer.addWidget(self._pane("Paste this", after, "formBuilder.adoptAfter", "formBuilder.adopt.copyAfter"))
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        outer.addWidget(close)
        self.apply_theme(tokens)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self.setStyleSheet(adopt_dialog_style(tokens))

    def _pane(self, title: str, text: str, edit_name: str, button_name: str) -> QWidget:
        frame = QWidget(self)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        header.addWidget(QLabel(title, frame), 1)
        copy = QPushButton("Copy", frame)
        copy.setObjectName(button_name)
        header.addWidget(copy)
        layout.addLayout(header)
        edit = QPlainTextEdit(text, frame)
        edit.setObjectName(edit_name)
        edit.setReadOnly(True)
        layout.addWidget(edit)
        copy.clicked.connect(lambda: self._copy(edit.toPlainText()))
        return frame

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
) -> None:
    dialog = AdoptDialog(before=before, after=after, tokens=tokens, parent=parent)
    exec_qt(dialog)
