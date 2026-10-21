"""Docs pane for the highlighted completion row.

Shows the signature line(s), the first paragraph of the docstring and the
defining class. Nothing else: no badges, no provenance labels.
"""

from __future__ import annotations

from app.qt.QtCore import Qt
from app.qt.QtGui import QFont, QFontDatabase
from app.qt.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.intelligence.completion_docs import completion_docs
from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens

PANEL_WIDTH = 330
_LOADING_TEXT = "Loading…"


class CompletionDocsPanel(QFrame):
    """Signature, summary and owner line for one completion item."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CompletionDocsPanel")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self._signature_label = QLabel(self)
        self._signature_label.setObjectName("CompletionDocsSignature")
        self._signature_label.setFont(mono)
        self._signature_label.setWordWrap(True)
        self._signature_label.setTextFormat(Qt.PlainText)
        self._signature_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._summary_label = QLabel(self)
        self._summary_label.setObjectName("CompletionDocsSummary")
        self._summary_label.setWordWrap(True)
        self._summary_label.setTextFormat(Qt.PlainText)
        self._owner_label = QLabel(self)
        self._owner_label.setObjectName("CompletionDocsOwner")
        self._owner_label.setTextFormat(Qt.PlainText)
        small = QFont(self._owner_label.font())
        small.setPointSizeF(max(7.5, small.pointSizeF() - 1.0))
        self._owner_label.setFont(small)
        layout.addWidget(self._signature_label)
        layout.addWidget(self._summary_label)
        layout.addStretch(1)
        layout.addWidget(self._owner_label)
        self._item: CompletionItem | None = None
        self._resolving = False
        self.set_item(None)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        bg = tokens.popup_bg or tokens.panel_bg
        self.setStyleSheet(
            f"""
            QFrame#CompletionDocsPanel {{ background-color: {bg}; }}
            QLabel#CompletionDocsSignature {{ color: {tokens.text_primary}; }}
            QLabel#CompletionDocsSummary {{ color: {tokens.text_primary}; }}
            QLabel#CompletionDocsOwner {{ color: {tokens.text_muted}; }}
            """
        )

    def set_item(self, item: CompletionItem | None) -> None:
        self._item = item
        self._resolving = False
        self._render()

    def set_resolving(self, resolving: bool) -> None:
        self._resolving = resolving
        self._render()

    def signature_text(self) -> str:
        return self._signature_label.text()

    def summary_text(self) -> str:
        return self._summary_label.text() if self._summary_label.isVisibleTo(self) else ""

    def owner_text(self) -> str:
        return self._owner_label.text()

    def visible_text(self) -> str:
        """Everything the pane shows, for checks and screen readers."""

        return "\n".join(part for part in (self.signature_text(), self.summary_text(), self.owner_text()) if part)

    def _render(self) -> None:
        item = self._item
        if item is None:
            self._signature_label.setText("")
            self._summary_label.setText("")
            self._summary_label.setVisible(False)
            self._owner_label.setText("")
            return
        docs = completion_docs(item)
        self._signature_label.setText("\n".join(docs.signatures))
        summary = docs.summary
        if not summary and self._resolving:
            summary = _LOADING_TEXT
        self._summary_label.setText(summary)
        self._summary_label.setVisible(bool(summary))
        self._owner_label.setText(docs.owner_line)
