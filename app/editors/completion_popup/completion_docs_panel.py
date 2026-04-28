"""Documentation side panel for the completion popup.

Shows the signature, return type, documentation summary, provenance footer,
and an optional side-effect-risk pill for the currently highlighted item.
"""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtGui import QFont, QFontDatabase
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens


_PANEL_MIN_WIDTH = 260
_PANEL_MAX_WIDTH = 420
_DOC_BODY_MAX_HEIGHT = 220


class CompletionDocsPanel(QFrame):
    """Side panel rendering metadata for the highlighted completion item."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CompletionDocsPanel")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(_PANEL_MIN_WIDTH)
        self.setMaximumWidth(_PANEL_MAX_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self._signature_label = QLabel(self)
        self._signature_label.setObjectName("CompletionDocsSignature")
        self._signature_label.setWordWrap(True)
        self._signature_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._signature_label)

        self._return_type_label = QLabel(self)
        self._return_type_label.setObjectName("CompletionDocsReturnType")
        self._return_type_label.setWordWrap(True)
        layout.addWidget(self._return_type_label)

        self._separator = QFrame(self)
        self._separator.setObjectName("CompletionDocsSeparator")
        self._separator.setFrameShape(QFrame.HLine)
        self._separator.setFrameShadow(QFrame.Plain)
        self._separator.setFixedHeight(1)
        layout.addWidget(self._separator)

        self._doc_body = QTextBrowser(self)
        self._doc_body.setObjectName("CompletionDocsBody")
        self._doc_body.setOpenExternalLinks(False)
        self._doc_body.setOpenLinks(False)
        self._doc_body.setFrameShape(QFrame.NoFrame)
        self._doc_body.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._doc_body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._doc_body.setMaximumHeight(_DOC_BODY_MAX_HEIGHT)
        layout.addWidget(self._doc_body, 1)

        footer = QWidget(self)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)
        self._provenance_label = QLabel(footer)
        self._provenance_label.setObjectName("CompletionDocsProvenance")
        self._provenance_label.setWordWrap(False)
        footer_layout.addWidget(self._provenance_label, 1)
        self._risk_pill = QLabel(footer)
        self._risk_pill.setObjectName("CompletionDocsRiskPill")
        self._risk_pill.setVisible(False)
        footer_layout.addWidget(self._risk_pill, 0, Qt.AlignRight)
        layout.addWidget(footer)

        self._tokens: ShellThemeTokens | None = None
        self._mono_family = self._resolve_mono_family()
        self._apply_default_styles()
        self.set_item(None)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Refresh palette derived from theme tokens."""
        self._tokens = tokens
        bg = tokens.popup_bg or tokens.panel_bg or "#FFFFFF"
        text = tokens.text_primary or "#212529"
        muted = tokens.text_muted or "#6C757D"
        border = tokens.popup_border or tokens.border or "#DEE2E6"
        accent = tokens.accent or text
        self.setStyleSheet(
            f"""
            QFrame#CompletionDocsPanel {{
                background-color: {bg};
                color: {text};
            }}
            QLabel#CompletionDocsSignature {{
                color: {text};
                font-family: "{self._mono_family}";
            }}
            QLabel#CompletionDocsReturnType {{
                color: {accent};
            }}
            QFrame#CompletionDocsSeparator {{
                background-color: {border};
                border: none;
            }}
            QTextBrowser#CompletionDocsBody {{
                background-color: {bg};
                color: {text};
                border: none;
            }}
            QLabel#CompletionDocsProvenance {{
                color: {muted};
            }}
            """
        )
        # Risk pill colors are applied per-item because they depend on the
        # severity of the side-effect risk.
        self._refresh_risk_pill_colors()

    def set_item(self, item: CompletionItem | None) -> None:
        """Render metadata for ``item`` (or hide everything when ``None``)."""

        if item is None or not _has_visible_metadata(item):
            self._signature_label.setVisible(False)
            self._return_type_label.setVisible(False)
            self._separator.setVisible(False)
            self._doc_body.setVisible(False)
            self._provenance_label.setText("")
            self._risk_pill.setVisible(False)
            return

        signature_text = item.signature or item.label
        self._signature_label.setText(signature_text)
        self._signature_label.setVisible(bool(signature_text))

        return_type = (item.return_type or "").strip()
        if return_type:
            self._return_type_label.setText(f"\u2192 {return_type}")
            self._return_type_label.setVisible(True)
        else:
            self._return_type_label.setVisible(False)

        documentation = (item.documentation or "").strip()
        self._separator.setVisible(bool(documentation))
        if documentation:
            self._doc_body.setPlainText(documentation)
            self._doc_body.setVisible(True)
        else:
            self._doc_body.clear()
            self._doc_body.setVisible(False)

        self._provenance_label.setText(_format_provenance(item))
        self._update_risk_pill(item)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply_default_styles(self) -> None:
        font = self._signature_label.font()
        font.setFamily(self._mono_family)
        self._signature_label.setFont(font)
        return_font = self._return_type_label.font()
        return_font.setItalic(True)
        self._return_type_label.setFont(return_font)
        body_font = QFont(self._doc_body.font())
        body_font.setPointSizeF(max(8.0, body_font.pointSizeF() - 0.5))
        self._doc_body.setFont(body_font)
        provenance_font = QFont(self._provenance_label.font())
        provenance_font.setPointSizeF(max(7.5, provenance_font.pointSizeF() - 1.0))
        self._provenance_label.setFont(provenance_font)
        pill_font = QFont(self._risk_pill.font())
        pill_font.setPointSizeF(max(7.5, pill_font.pointSizeF() - 1.0))
        pill_font.setBold(True)
        self._risk_pill.setFont(pill_font)

    @staticmethod
    def _resolve_mono_family() -> str:
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        family = font.family() or "monospace"
        return family

    def _update_risk_pill(self, item: CompletionItem) -> None:
        risk = (item.side_effect_risk or "").strip()
        if not risk:
            self._risk_pill.setVisible(False)
            self._risk_pill.setText("")
            return
        self._risk_pill.setText(risk)
        self._risk_pill.setVisible(True)
        self._refresh_risk_pill_colors(risk)

    def _refresh_risk_pill_colors(self, risk: str | None = None) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        active_risk = risk if risk is not None else self._risk_pill.text()
        if not active_risk:
            return
        if active_risk.lower() == "inspection_only":
            bg = tokens.diag_warning_color or "#D97706"
        else:
            bg = tokens.diag_error_color or "#E03131"
        text_color = "#FFFFFF" if tokens.is_dark else "#FFFFFF"
        self._risk_pill.setStyleSheet(
            f"""
            QLabel#CompletionDocsRiskPill {{
                background-color: {bg};
                color: {text_color};
                padding: 1px 6px;
                border-radius: 6px;
            }}
            """
        )


def _has_visible_metadata(item: CompletionItem) -> bool:
    """Return ``True`` when at least one panel field has user-visible content."""
    return bool(
        (item.signature or "").strip()
        or (item.documentation or "").strip()
        or (item.return_type or "").strip()
        or (item.side_effect_risk or "").strip()
        or (item.engine or item.source or item.confidence)
    )


def _format_provenance(item: CompletionItem) -> str:
    parts = [
        value
        for value in (item.engine, item.source, item.confidence)
        if (value or "").strip()
    ]
    return " \u00b7 ".join(parts)
