"""Orchestrator that replaces ``QCompleter`` for the editor and console.

Provides a near drop-in API for callers used to ``QCompleter``:

* :meth:`set_widget`
* :meth:`set_items` (replaces ``setStringList`` / ``setCompletionPrefix``)
* :meth:`complete` (positions the popup at the supplied rect)
* :meth:`popup` (returns the underlying :class:`CompletionPopupContainer`)
* :meth:`current_item` / :pyattr:`activated`
* :meth:`apply_theme`

Keyboard navigation continues to be driven by the host widget's
``keyPressEvent``; the controller exposes :meth:`forward_navigation_event` and
:meth:`accept_current` helpers so each surface can keep its existing
``_handle_completion_popup_navigation`` shape.
"""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide2.QtGui import QKeyEvent
from PySide2.QtWidgets import QApplication, QWidget

from app.editors.completion_popup.completion_item_model import CompletionItemModel
from app.editors.completion_popup.completion_popup_container import (
    CompletionPopupContainer,
)
from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens


_NAVIGATION_KEYS = {
    Qt.Key_Up,
    Qt.Key_Down,
    Qt.Key_PageUp,
    Qt.Key_PageDown,
    Qt.Key_Home,
    Qt.Key_End,
}
_ACCEPT_KEYS = {Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab}


class CompletionController(QObject):
    """High-level orchestrator owning the popup, model, and view."""

    activated: Any = Signal(object)
    selection_changed: Any = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._widget: QWidget | None = None
        self._model = CompletionItemModel(self)
        popup_parent = parent if isinstance(parent, QWidget) else None
        self._popup = CompletionPopupContainer(popup_parent)
        self._popup.list_view().setModel(self._model)
        self._popup.list_view().doubleClicked.connect(self._on_double_clicked)
        self._popup.list_view().clicked.connect(self._on_clicked)
        self._popup.list_view().current_item_changed.connect(self._on_current_item_changed)
        # Intercept keyboard events that Qt routes to the popup (because of
        # ``Qt.Popup``) and forward typed characters back to the host widget so
        # the user can keep typing to refine the visible completion list.
        self._popup.installEventFilter(self)
        self._tokens: ShellThemeTokens | None = None
        self._last_selection_identity = ""

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def set_widget(self, widget: QWidget | None) -> None:
        """Attach the host widget used as positioning anchor and focus proxy.

        The popup uses ``widget`` as its focus proxy so Qt does not visibly
        steal focus when the popup is shown. Typed characters that reach the
        popup (because of ``Qt.Popup`` keyboard grab) are forwarded back to
        ``widget`` from :meth:`eventFilter`.
        """
        self._widget = widget
        self._popup.setFocusProxy(widget)

    def widget(self) -> QWidget | None:
        return self._widget

    def model(self) -> CompletionItemModel:
        return self._model

    def popup(self) -> CompletionPopupContainer:
        return self._popup

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        """Apply theme tokens to all owned widgets and the model."""
        self._tokens = tokens
        self._model.set_theme_tokens(tokens)
        self._popup.apply_theme(tokens)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def set_items(self, items: list[CompletionItem], prefix: str) -> None:
        """Populate the model with new candidates."""
        self._model.set_items(items, prefix)
        self._last_selection_identity = ""
        self._popup.list_view().select_first_row()

    def replace_item(self, item: CompletionItem) -> bool:
        """Replace a displayed item with lazily resolved metadata."""

        replaced = self._model.replace_item(item)
        if replaced and self.current_item() == item:
            self._popup.docs_panel().set_item(item)
        return replaced

    def reuse_items_for_prefix(self, prefix: str) -> bool:
        """Filter visible results for a longer prefix while async work runs."""

        previous_prefix = self._model.prefix()
        if previous_prefix and not prefix.startswith(previous_prefix):
            return False
        items = [
            item
            for item in self._model.items()
            if not prefix or item.label.lower().startswith(prefix.lower())
        ]
        if not items:
            return False
        self.set_items(items, prefix)
        return True

    def clear(self) -> None:
        """Drop all rows and hide the popup."""
        self._model.clear()
        self._popup.hide()

    def complete(self, anchor_rect: QRect) -> None:
        """Show the popup near ``anchor_rect`` (host-widget coordinates)."""
        if self._model.rowCount() == 0:
            self._popup.hide()
            return
        widget = self._widget
        if widget is None:
            self._popup.show()
            return
        if not widget.isVisible():
            return

        list_view = self._popup.list_view()
        list_view.select_first_row()

        list_width = list_view.width_hint()
        list_height = list_view.height_hint()
        list_view.setFixedWidth(list_width)
        list_view.setFixedHeight(list_height)

        if self._popup.docs_visible():
            docs = self._popup.docs_panel()
            docs.setFixedHeight(list_height)

        self._popup.adjustSize()
        size = self._popup.sizeHint()
        popup_width = max(size.width(), list_width + 32)
        popup_height = max(size.height(), list_height + 16)
        self._popup.resize(popup_width, popup_height)

        global_anchor = widget.mapToGlobal(QPoint(anchor_rect.x(), anchor_rect.bottom() + 4))
        screen_geom = self._screen_geometry_for(widget, global_anchor)
        x = global_anchor.x()
        y = global_anchor.y()
        if x + popup_width > screen_geom.right():
            x = max(screen_geom.left(), screen_geom.right() - popup_width)
        if y + popup_height > screen_geom.bottom():
            y_above = widget.mapToGlobal(QPoint(anchor_rect.x(), anchor_rect.y())).y() - popup_height - 4
            y = max(screen_geom.top(), y_above)

        self._popup.move(x, y)
        if not self._popup.isVisible():
            self._popup.show()
        else:
            self._popup.raise_()

    def hide(self) -> None:
        self._popup.hide()

    def is_visible(self) -> bool:
        return self._popup.isVisible()

    def current_item(self) -> CompletionItem | None:
        return self._popup.list_view().current_item()

    # ------------------------------------------------------------------
    # Keyboard helpers
    # ------------------------------------------------------------------

    def handle_navigation_event(self, event: QKeyEvent) -> bool:
        """Forward navigation/accept/dismiss events to the popup.

        Returns ``True`` when the event has been handled by the controller and
        should not be processed further by the host widget.
        """
        if not self._popup.isVisible():
            return False
        key = event.key()
        if key == Qt.Key_Escape:
            self._popup.hide()
            event.accept()
            return True
        if key in _ACCEPT_KEYS:
            self.accept_current()
            event.accept()
            return True
        if key in _NAVIGATION_KEYS:
            QApplication.sendEvent(self._popup.list_view(), event)
            return True
        return False

    def accept_current(self) -> None:
        """Emit :pyattr:`activated` for the highlighted item, then hide."""
        item = self.current_item()
        self._popup.hide()
        if item is not None:
            self.activated.emit(item)

    # ------------------------------------------------------------------
    # Event filter (popup keyboard grab forwarding)
    # ------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        """Forward keyboard input that Qt grabbed for the popup.

        ``Qt.Popup`` causes Qt to route all keyboard events to the popup
        widget. We let the popup handle navigation/accept/dismiss keys, and
        forward every other key (typed characters, backspace, etc.) to the
        host widget so the user can continue editing while the popup stays
        open and refines its list.
        """
        popup = getattr(self, "_popup", None)
        if popup is None or watched is not popup or event.type() != QEvent.KeyPress:
            return super().eventFilter(watched, event)
        key_event = event  # QKeyEvent at this point
        key = key_event.key()
        if key == Qt.Key_Escape:
            self._popup.hide()
            key_event.accept()
            return True
        if key in _ACCEPT_KEYS:
            self.accept_current()
            key_event.accept()
            return True
        if key in _NAVIGATION_KEYS:
            QApplication.sendEvent(self._popup.list_view(), key_event)
            return True
        widget = self._widget
        if widget is None:
            return super().eventFilter(watched, event)
        # Forward everything else (printable characters, backspace, modifiers)
        # to the host widget. The widget's ``keyPressEvent`` will update the
        # buffer and re-trigger completion, which in turn calls
        # :meth:`set_items` / :meth:`complete` to refresh the popup.
        QApplication.sendEvent(widget, key_event)
        return True

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_double_clicked(self, _index: object) -> None:
        self.accept_current()

    def _on_clicked(self, _index: object) -> None:
        # Single-click only updates the docs panel (already wired via
        # currentRowChanged); accepting requires a double-click or Enter.
        return

    def _on_current_item_changed(self, item: object) -> None:
        identity = _selection_identity(item)
        if identity and identity == self._last_selection_identity:
            return
        self._last_selection_identity = identity
        self.selection_changed.emit(item)

    @staticmethod
    def _screen_geometry_for(widget: QWidget, point: QPoint) -> QRect:
        screen = widget.screen() if hasattr(widget, "screen") else None
        if screen is None:
            app = QApplication.instance()
            if app is None:
                return QRect(0, 0, 1920, 1080)
            screen = app.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1920, 1080)
        # Prefer screen at the anchor point when available.
        for candidate in QApplication.screens():
            if candidate.geometry().contains(point):
                return candidate.availableGeometry()
        return screen.availableGeometry()


def _selection_identity(item: object) -> str:
    if not isinstance(item, CompletionItem):
        return ""
    if item.item_id:
        return item.item_id
    return f"{item.label}|{item.insert_text}|{item.kind.value}|{item.source}"
