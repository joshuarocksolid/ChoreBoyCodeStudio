"""Documentation side panel for the completion popup.

Shows a structured symbol header, signature, documentation body, provenance
footer, and an optional side-effect-risk pill for the highlighted item.
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

from app.core.completion_tier import is_tier_header_item
from app.editors.completion_popup.completion_kind_style import kind_style_for
from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.shell.theme_tokens import ShellThemeTokens


_PANEL_MIN_WIDTH = 260
_PANEL_MAX_WIDTH = 420
_PANEL_MIN_HEIGHT = 120
_DOC_BODY_MIN_HEIGHT = 64
_DOC_BODY_MAX_HEIGHT = 220

_LOADING_TEXT = "Loading documentation\u2026"
_EMPTY_DOC_TEXT = "No documentation available."

_PROVENANCE_LABELS = {
    "static_api_index": "Indexed API",
    "api_index": "Indexed API",
    "semantic": "Python analysis",
    "jedi": "Python analysis",
    "runtime_introspection": "Runtime introspection",
}


class CompletionDocsPanel(QFrame):
    """Side panel rendering metadata for the highlighted completion item."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CompletionDocsPanel")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(_PANEL_MIN_WIDTH)
        self.setMaximumWidth(_PANEL_MAX_WIDTH)
        self.setMinimumHeight(_PANEL_MIN_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self._kind_chip = QLabel(header)
        self._kind_chip.setObjectName("CompletionDocsKindChip")
        self._kind_chip.setAlignment(Qt.AlignCenter)
        self._kind_chip.setFixedSize(22, 22)
        header_layout.addWidget(self._kind_chip, 0, Qt.AlignTop)
        self._name_label = QLabel(header)
        self._name_label.setObjectName("CompletionDocsName")
        self._name_label.setWordWrap(True)
        self._name_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header_layout.addWidget(self._name_label, 1)
        self._type_label = QLabel(header)
        self._type_label.setObjectName("CompletionDocsType")
        self._type_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self._type_label, 0)
        layout.addWidget(header)

        self._detail_label = QLabel(self)
        self._detail_label.setObjectName("CompletionDocsDetail")
        self._detail_label.setWordWrap(True)
        layout.addWidget(self._detail_label)

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
        self._doc_body.setMinimumHeight(_DOC_BODY_MIN_HEIGHT)
        self._doc_body.setMaximumHeight(_DOC_BODY_MAX_HEIGHT)
        layout.addWidget(self._doc_body, 1)

        self._footer_separator = QFrame(self)
        self._footer_separator.setObjectName("CompletionDocsFooterSeparator")
        self._footer_separator.setFrameShape(QFrame.HLine)
        self._footer_separator.setFrameShadow(QFrame.Plain)
        self._footer_separator.setFixedHeight(1)
        layout.addWidget(self._footer_separator)

        footer_row = QWidget(self)
        footer_row_layout = QHBoxLayout(footer_row)
        footer_row_layout.setContentsMargins(0, 0, 0, 0)
        footer_row_layout.setSpacing(8)
        self._provenance_label = QLabel(footer_row)
        self._provenance_label.setObjectName("CompletionDocsProvenance")
        self._provenance_label.setWordWrap(False)
        footer_row_layout.addWidget(self._provenance_label, 1)
        self._risk_pill = QLabel(footer_row)
        self._risk_pill.setObjectName("CompletionDocsRiskPill")
        self._risk_pill.setVisible(False)
        footer_row_layout.addWidget(self._risk_pill, 0, Qt.AlignRight)
        layout.addWidget(footer_row)

        self._tokens: ShellThemeTokens | None = None
        self._mono_family = self._resolve_mono_family()
        self._current_item: CompletionItem | None = None
        self._resolving = False
        self._apply_default_styles()
        self.set_item(None)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Refresh palette derived from theme tokens."""
        self._tokens = tokens
        bg = tokens.popup_bg or tokens.panel_bg
        text = tokens.text_primary
        muted = tokens.text_muted
        border = tokens.popup_border or tokens.border
        accent = tokens.accent
        self.setStyleSheet(
            f"""
            QFrame#CompletionDocsPanel {{
                background-color: {bg};
                color: {text};
            }}
            QLabel#CompletionDocsName {{
                color: {text};
                font-weight: 600;
            }}
            QLabel#CompletionDocsType {{
                color: {muted};
            }}
            QLabel#CompletionDocsDetail {{
                color: {muted};
            }}
            QLabel#CompletionDocsSignature {{
                color: {text};
                font-family: "{self._mono_family}";
            }}
            QLabel#CompletionDocsReturnType {{
                color: {accent};
            }}
            QFrame#CompletionDocsSeparator,
            QFrame#CompletionDocsFooterSeparator {{
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
        self._refresh_risk_pill_colors()
        if self._current_item is not None:
            self._render_item(self._current_item)

    def set_item(self, item: CompletionItem | None) -> None:
        """Render metadata for ``item`` (or hide everything when ``None``)."""

        if item is not None and is_tier_header_item(item):
            return
        # Selection / list refresh always owns the loading flag. Leaving
        # ``_resolving`` sticky from a prior item leaves "Loading documentation…"
        # when the new item has no docs and no resolve request is issued.
        self._resolving = False
        self._current_item = item
        self._render_item(item)

    def set_resolving(self, resolving: bool) -> None:
        """Toggle the loading state for the current item."""

        self._resolving = resolving
        if self._current_item is not None:
            self._render_item(self._current_item)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _render_item(self, item: CompletionItem | None) -> None:
        if item is None or not _has_visible_metadata(item):
            self._hide_all_content()
            return

        self._update_header(item)
        self._update_signature_block(item)
        self._update_body(item)
        provenance = _format_provenance(item)
        self._provenance_label.setText(provenance)
        self._provenance_label.setVisible(bool(provenance))
        self._footer_separator.setVisible(bool(provenance))
        self._update_risk_pill(item)

    def _hide_all_content(self) -> None:
        for widget in (
            self._kind_chip,
            self._name_label,
            self._type_label,
            self._detail_label,
            self._signature_label,
            self._return_type_label,
            self._separator,
            self._doc_body,
            self._footer_separator,
            self._provenance_label,
        ):
            widget.setVisible(False)
        self._doc_body.clear()
        self._provenance_label.setText("")
        self._risk_pill.setVisible(False)

    def _update_header(self, item: CompletionItem) -> None:
        tokens = self._tokens
        if tokens is not None:
            style = kind_style_for(item.kind, tokens)
            self._kind_chip.setText(style.glyph)
            self._kind_chip.setStyleSheet(
                f"""
                QLabel#CompletionDocsKindChip {{
                    background-color: {style.accent_color};
                    color: {tokens.text_primary if tokens.is_high_contrast else tokens.panel_bg or tokens.popup_bg};
                    border-radius: 4px;
                    font-weight: 700;
                    font-size: 11px;
                }}
                """
            )
        else:
            self._kind_chip.setText("?")
        self._kind_chip.setVisible(True)
        self._name_label.setText(item.label)
        self._name_label.setVisible(True)
        type_label = _kind_label(item.kind)
        self._type_label.setText(type_label)
        self._type_label.setVisible(bool(type_label))

        detail = (item.detail or "").strip()
        show_detail_subtitle = bool(detail) and not (item.signature or "").strip()
        if show_detail_subtitle:
            self._detail_label.setText(detail)
            self._detail_label.setVisible(True)
        else:
            self._detail_label.setVisible(False)

    def _update_signature_block(self, item: CompletionItem) -> None:
        signature_text = (item.signature or "").strip()
        if signature_text:
            self._signature_label.setText(signature_text)
            self._signature_label.setVisible(True)
        else:
            self._signature_label.setVisible(False)

        return_type = (item.return_type or "").strip()
        if return_type:
            self._return_type_label.setText(f"\u2192 {return_type}")
            self._return_type_label.setVisible(True)
        else:
            self._return_type_label.setVisible(False)

    def _update_body(self, item: CompletionItem) -> None:
        documentation = (item.documentation or "").strip()
        detail = (item.detail or "").strip()
        signature_text = (item.signature or "").strip()

        if self._resolving and not documentation:
            self._show_body_text(_LOADING_TEXT, italic=True, muted=True)
            self._separator.setVisible(bool(signature_text))
            return

        if documentation:
            self._doc_body.setPlainText(documentation)
            self._doc_body.setVisible(True)
            self._separator.setVisible(True)
            return

        if detail and signature_text:
            self._show_body_text(detail, italic=False, muted=True)
            self._separator.setVisible(True)
            return

        if detail:
            self._show_body_text(detail, italic=False, muted=False)
            self._separator.setVisible(False)
            return

        self._show_body_text(_EMPTY_DOC_TEXT, italic=True, muted=True)
        self._separator.setVisible(bool(signature_text))

    def _show_body_text(self, text: str, *, italic: bool, muted: bool) -> None:
        self._doc_body.setPlainText(text)
        self._doc_body.setVisible(True)
        font = QFont(self._doc_body.font())
        font.setItalic(italic)
        self._doc_body.setFont(font)
        tokens = self._tokens
        if tokens is not None and muted:
            self._doc_body.setStyleSheet(
                f"""
                QTextBrowser#CompletionDocsBody {{
                    background-color: {tokens.popup_bg or tokens.panel_bg};
                    color: {tokens.text_muted};
                    border: none;
                }}
                """
            )
        elif tokens is not None:
            self._doc_body.setStyleSheet(
                f"""
                QTextBrowser#CompletionDocsBody {{
                    background-color: {tokens.popup_bg or tokens.panel_bg};
                    color: {tokens.text_primary};
                    border: none;
                }}
                """
            )

    def _apply_default_styles(self) -> None:
        font = self._signature_label.font()
        font.setFamily(self._mono_family)
        font.setPointSizeF(font.pointSizeF() + 0.5)
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
            bg = tokens.diag_warning_color
        else:
            bg = tokens.diag_error_color
        text_color = tokens.text_primary if tokens.is_high_contrast else "#FFFFFF"
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
    if is_tier_header_item(item):
        return False
    return bool(
        (item.label or "").strip()
        or (item.signature or "").strip()
        or (item.documentation or "").strip()
        or (item.return_type or "").strip()
        or (item.detail or "").strip()
        or (item.side_effect_risk or "").strip()
        or _format_provenance(item)
    )


def _kind_label(kind: CompletionKind) -> str:
    if kind == CompletionKind.TEXT:
        return ""
    return kind.value


def _format_provenance(item: CompletionItem) -> str:
    if is_tier_header_item(item):
        return ""
    labels: list[str] = []
    source_label = _PROVENANCE_LABELS.get((item.source or "").strip(), "")
    if source_label:
        labels.append(source_label)
    elif (item.engine or "").strip():
        engine_label = _PROVENANCE_LABELS.get((item.engine or "").strip(), "")
        labels.append(engine_label or item.engine)
    confidence = (item.confidence or "").strip()
    if confidence and confidence not in {"exact", "approximate", "static", "unsupported"}:
        labels.append(confidence)
    return " \u00b7 ".join(labels)
