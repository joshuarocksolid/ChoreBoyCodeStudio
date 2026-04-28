"""Frameless container that hosts the completion list and docs panel."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor
from PySide2.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from app.editors.completion_popup.completion_docs_panel import CompletionDocsPanel
from app.editors.completion_popup.completion_list_view import CompletionListView
from app.shell.theme_tokens import ShellThemeTokens


_SHADOW_BLUR = 18
_SHADOW_OFFSET_Y = 4


class CompletionPopupContainer(QFrame):
    """Top-level frameless popup hosting the list view and docs panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CompletionPopupContainer")
        # ``Qt.Popup`` ensures focus-out hides the popup automatically.
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # Never accept keyboard focus ourselves; the host widget keeps it via
        # focus-proxy + event-filter forwarding from CompletionController.
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        # The visible chrome (background + border + radius) lives on an inner
        # frame so the outer translucent widget can hold the drop shadow.
        self._chrome = QFrame(self)
        self._chrome.setObjectName("CompletionPopupChrome")
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(8, 4, 8, 12)
        outer_layout.addWidget(self._chrome)

        chrome_layout = QHBoxLayout(self._chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)

        self._list_view = CompletionListView(self._chrome)
        chrome_layout.addWidget(self._list_view, 0)

        self._separator = QFrame(self._chrome)
        self._separator.setObjectName("CompletionPopupSeparator")
        self._separator.setFrameShape(QFrame.VLine)
        self._separator.setFrameShadow(QFrame.Plain)
        self._separator.setFixedWidth(1)
        chrome_layout.addWidget(self._separator)

        self._docs_panel = CompletionDocsPanel(self._chrome)
        chrome_layout.addWidget(self._docs_panel, 1)

        self._docs_visible = True
        self._tokens: ShellThemeTokens | None = None

        shadow = QGraphicsDropShadowEffect(self._chrome)
        shadow.setBlurRadius(_SHADOW_BLUR)
        shadow.setOffset(0, _SHADOW_OFFSET_Y)
        shadow.setColor(QColor(0, 0, 0, 80))
        self._chrome.setGraphicsEffect(shadow)
        self._shadow = shadow

        self._list_view.current_item_changed.connect(self._docs_panel.set_item)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Restyle container chrome and propagate to children."""
        self._tokens = tokens
        bg = tokens.popup_bg or tokens.panel_bg or "#FFFFFF"
        border = tokens.popup_border or tokens.border or "#DEE2E6"
        shadow_hex = tokens.popup_shadow or ""
        shadow_color = (
            QColor(shadow_hex)
            if shadow_hex
            else QColor(0, 0, 0, 160 if tokens.is_dark else 64)
        )
        if not shadow_hex:
            self._shadow.setColor(shadow_color)
        else:
            shadow_color.setAlpha(160 if tokens.is_dark else 64)
            self._shadow.setColor(shadow_color)

        self.setStyleSheet(
            f"""
            QFrame#CompletionPopupChrome {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QFrame#CompletionPopupSeparator {{
                background-color: {border};
                border: none;
            }}
            """
        )
        self._list_view.apply_theme(tokens)
        self._docs_panel.apply_theme(tokens)

    # ------------------------------------------------------------------
    # Docs panel toggle
    # ------------------------------------------------------------------

    def set_docs_visible(self, visible: bool) -> None:
        """Show or hide the docs panel; useful for narrow viewports."""
        self._docs_visible = visible
        self._docs_panel.setVisible(visible)
        self._separator.setVisible(visible)

    def docs_visible(self) -> bool:
        return self._docs_visible

    # ------------------------------------------------------------------
    # Children accessors
    # ------------------------------------------------------------------

    def list_view(self) -> CompletionListView:
        return self._list_view

    def docs_panel(self) -> CompletionDocsPanel:
        return self._docs_panel
