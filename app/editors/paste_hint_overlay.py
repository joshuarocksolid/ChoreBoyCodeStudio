"""Transient inline hint shown after a flat-Python paste.

Modeled after VS Code's *Paste Options* widget and PyCharm's intention bulb.
The widget is intentionally pure UI — all heuristic logic lives in
``app.editors.text_editing`` and all wiring lives in :class:`CodeEditorWidget`.
"""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import QPoint, Qt, QTimer, Signal
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QWidget,
)

from app.shell.theme_tokens import ShellThemeTokens


AUTO_HIDE_INTERVAL_MS = 5000


class PasteHintOverlay(QFrame):
    """Frameless transient prompt offering a flat-Python re-indent on the just-pasted block."""

    reindentRequested: Any = Signal()
    enableAlwaysRequested: Any = Signal()
    dismissed: Any = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PasteHintOverlay")
        # Embedded child widget (no top-level Qt.ToolTip window flag): keeps
        # the overlay tied to the editor's lifetime under the offscreen
        # platform plugin, avoiding stale top-level windows in tests.
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.NoFocus)

        self._chrome = QFrame(self)
        self._chrome.setObjectName("PasteHintOverlayChrome")
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(2, 2, 2, 2)
        outer_layout.addWidget(self._chrome)

        chrome_layout = QHBoxLayout(self._chrome)
        chrome_layout.setContentsMargins(10, 6, 6, 6)
        chrome_layout.setSpacing(6)

        self._label = QPushButton("Looks like flat Python.", self._chrome)
        self._label.setObjectName("PasteHintOverlayLabel")
        self._label.setFlat(True)
        self._label.setEnabled(False)
        self._label.setFocusPolicy(Qt.NoFocus)
        chrome_layout.addWidget(self._label)

        self._reindent_button = QPushButton("Re-indent", self._chrome)
        self._reindent_button.setObjectName("PasteHintOverlayReindentButton")
        self._reindent_button.setFocusPolicy(Qt.NoFocus)
        self._reindent_button.clicked.connect(self._handle_reindent_clicked)
        chrome_layout.addWidget(self._reindent_button)

        self._always_button = QPushButton("Always", self._chrome)
        self._always_button.setObjectName("PasteHintOverlayAlwaysButton")
        self._always_button.setFlat(True)
        self._always_button.setFocusPolicy(Qt.NoFocus)
        self._always_button.setToolTip(
            "Always re-indent flat Python pastes (changes the Editor setting)."
        )
        self._always_button.clicked.connect(self._handle_always_clicked)
        chrome_layout.addWidget(self._always_button)

        self._dismiss_button = QToolButton(self._chrome)
        self._dismiss_button.setObjectName("PasteHintOverlayDismissButton")
        self._dismiss_button.setText("×")
        self._dismiss_button.setToolTip("Dismiss (do not show again this session)")
        self._dismiss_button.setFocusPolicy(Qt.NoFocus)
        self._dismiss_button.setAutoRaise(True)
        self._dismiss_button.clicked.connect(self._handle_dismiss_clicked)
        chrome_layout.addWidget(self._dismiss_button)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.setInterval(AUTO_HIDE_INTERVAL_MS)
        self._auto_hide_timer.timeout.connect(self._handle_auto_hide)

        self.hide()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Restyle for the current theme (light / dark)."""
        is_dark = tokens.is_dark
        bg = tokens.popup_bg or tokens.panel_bg
        border = tokens.popup_border or tokens.border
        text_primary = tokens.text_primary
        text_muted = tokens.text_muted
        accent = tokens.accent or ("#3B82F6" if is_dark else "#1D4ED8")
        accent_hover = "#60A5FA" if is_dark else "#1E40AF"
        accent_text = "#FFFFFF"
        always_hover_bg = "#2A3340" if is_dark else "#E5E7EB"
        dismiss_hover_bg = "#2A3340" if is_dark else "#E5E7EB"

        self._chrome.setStyleSheet(
            f"""
            QFrame#PasteHintOverlayChrome {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QPushButton#PasteHintOverlayLabel {{
                background-color: transparent;
                color: {text_muted};
                border: none;
                padding: 0px 4px;
                text-align: left;
            }}
            QPushButton#PasteHintOverlayReindentButton {{
                background-color: {accent};
                color: {accent_text};
                border: 1px solid {accent};
                border-radius: 4px;
                padding: 3px 10px;
                font-weight: 600;
            }}
            QPushButton#PasteHintOverlayReindentButton:hover {{
                background-color: {accent_hover};
                border-color: {accent_hover};
            }}
            QPushButton#PasteHintOverlayAlwaysButton {{
                color: {text_primary};
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 3px 8px;
            }}
            QPushButton#PasteHintOverlayAlwaysButton:hover {{
                background-color: {always_hover_bg};
                border-color: {border};
            }}
            QToolButton#PasteHintOverlayDismissButton {{
                color: {text_muted};
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 10px;
                padding: 1px 6px;
                font-size: 14px;
            }}
            QToolButton#PasteHintOverlayDismissButton:hover {{
                background-color: {dismiss_hover_bg};
                color: {text_primary};
            }}
            """
        )

    def show_at(self, viewport: QWidget, anchor: QPoint) -> None:
        """Show the hint anchored at ``anchor`` (viewport-local coordinates).

        ``anchor`` is interpreted in ``viewport`` coordinates; we reparent
        the overlay onto the viewport so the editor's resize / scroll events
        keep us positioned naturally.
        """
        if self.parent() is not viewport:
            self.setParent(viewport)
        self.adjustSize()
        x = max(0, anchor.x())
        y = max(0, anchor.y())
        x = min(x, max(0, viewport.width() - self.width() - 2))
        y = min(y, max(0, viewport.height() - self.height() - 2))
        self.move(x, y)
        self.show()
        self.raise_()
        self._auto_hide_timer.start()

    def hide_overlay(self) -> None:
        """Hide the overlay and stop the auto-hide timer without emitting any signal."""
        self._auto_hide_timer.stop()
        self.hide()

    def _handle_reindent_clicked(self) -> None:
        self._auto_hide_timer.stop()
        self.hide()
        self.reindentRequested.emit()

    def _handle_always_clicked(self) -> None:
        self._auto_hide_timer.stop()
        self.hide()
        self.enableAlwaysRequested.emit()

    def _handle_dismiss_clicked(self) -> None:
        self._auto_hide_timer.stop()
        self.hide()
        self.dismissed.emit()

    def _handle_auto_hide(self) -> None:
        self.hide()
        self.dismissed.emit()

