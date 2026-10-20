"""Frameless popup hosting the completion list, its footer and the docs pane."""

from __future__ import annotations

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QColor, QFont, QHideEvent
from PySide2.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.editors.completion_popup.completion_docs_panel import CompletionDocsPanel
from app.editors.completion_popup.completion_list_view import CompletionListView
from app.shell.theme_tokens import ShellThemeTokens

_SHADOW_BLUR = 18
_SHADOW_OFFSET_Y = 4
OUTER_MARGINS = (8, 4, 8, 12)


class CompletionPopupContainer(QFrame):
    """Top-level ``Qt.Popup`` window; the host widget keeps keyboard focus."""

    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CompletionPopupContainer")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self._chrome = QFrame(self)
        self._chrome.setObjectName("CompletionPopupChrome")
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(*OUTER_MARGINS)
        outer_layout.addWidget(self._chrome)

        chrome_layout = QHBoxLayout(self._chrome)
        chrome_layout.setContentsMargins(1, 1, 1, 1)
        chrome_layout.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(0, 2, 0, 0)
        left.setSpacing(0)
        self._list_view = CompletionListView(self._chrome)
        left.addWidget(self._list_view, 0)
        self._footer = QLabel(self._chrome)
        self._footer.setObjectName("CompletionPopupFooter")
        footer_font = QFont(self._footer.font())
        footer_font.setPointSizeF(max(7.5, footer_font.pointSizeF() - 1.0))
        self._footer.setFont(footer_font)
        left.addWidget(self._footer, 0)
        left.addStretch(1)
        chrome_layout.addLayout(left, 0)

        self._separator = QFrame(self._chrome)
        self._separator.setObjectName("CompletionPopupSeparator")
        self._separator.setFrameShape(QFrame.VLine)
        self._separator.setFrameShadow(QFrame.Plain)
        self._separator.setFixedWidth(1)
        chrome_layout.addWidget(self._separator)

        self._docs_panel = CompletionDocsPanel(self._chrome)
        chrome_layout.addWidget(self._docs_panel, 0)

        shadow = QGraphicsDropShadowEffect(self._chrome)
        shadow.setBlurRadius(_SHADOW_BLUR)
        shadow.setOffset(0, _SHADOW_OFFSET_Y)
        shadow.setColor(QColor(0, 0, 0, 80))
        self._chrome.setGraphicsEffect(shadow)
        self._shadow = shadow
        self._docs_visible = True
        self._list_view.current_item_changed.connect(self._docs_panel.set_item)

    def hideEvent(self, event: QHideEvent) -> None:  # type: ignore[override]
        super().hideEvent(event)
        self.closed.emit()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        bg = tokens.popup_bg or tokens.panel_bg
        border = tokens.popup_border or tokens.border
        shadow_color = QColor(tokens.popup_shadow) if tokens.popup_shadow else QColor(0, 0, 0)
        shadow_color.setAlpha(160 if tokens.is_dark else 64)
        self._shadow.setColor(shadow_color)
        self.setStyleSheet(
            f"""
            QFrame#CompletionPopupChrome {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
            QFrame#CompletionPopupSeparator {{
                background-color: {border};
                border: none;
            }}
            QLabel#CompletionPopupFooter {{
                color: {tokens.text_muted};
                background: transparent;
                padding: 2px 8px 4px 8px;
            }}
            """
        )
        self._list_view.apply_theme(tokens)
        self._docs_panel.apply_theme(tokens)

    def set_docs_visible(self, visible: bool) -> None:
        self._docs_visible = visible
        self._docs_panel.setVisible(visible)
        self._separator.setVisible(visible)

    def docs_visible(self) -> bool:
        return self._docs_visible

    def set_footer_text(self, text: str) -> None:
        self._footer.setText(text)

    def footer_text(self) -> str:
        return self._footer.text()

    def list_view(self) -> CompletionListView:
        return self._list_view

    def docs_panel(self) -> CompletionDocsPanel:
        return self._docs_panel
