"""The row popover shell and the summary button (UX-PED-003, UX-PED-004).

Helper module: underscore, not registered. Editors open a ``RowPopover`` from
their row's ``SummaryButton``. Nothing here knows a property; the editor writes
through ``host.commit(value, session=popover.session)`` or ``popover.session.run``.

Session rules (see ``_services``): the popover's session is opened when the
popover is built. ``done()`` (Done, Enter in a one-line field, a click outside,
a selection change, a structural command) closes it and keeps the writes.
``revert()`` (Esc) undoes everything the session wrote, so the document and the
undo stack are as they were before the popover opened. Ctrl+Z outside a text
field closes it, keeps the writes and undoes them as one step.

Focus: while open, focus stays in the popover; when it closes, focus goes to
the summary button, whatever closed it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List, Optional

from app.qt.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from app.qt.QtGui import QColor, QFontMetrics, QKeySequence
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QAbstractSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import wrapper_is_valid

if TYPE_CHECKING:
    from app.features.form_builder.qtside.inspector.api import EditorHost, EditSession

#: UX-PED-003 widths: the inspector content width, clamped; large editors 320-480 and grow left.
MIN_WIDTH = 236
MAX_WIDTH = 320
LARGE_MIN_WIDTH = 320
LARGE_MAX_WIDTH = 480
GAP = 4
PADDING = 12
ARROW = "▾"
_ELEVATION_BLUR = 24
_ELEVATION_OFFSET_Y = 8
_ELEVATION_ALPHA = 41  # 16 % of black


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _modifier(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _mouse(name: str) -> object:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _event(name: str) -> object:
    return getattr(getattr(QEvent, "Type", QEvent), name)


def _window_flag_popup() -> object:
    return getattr(getattr(Qt, "WindowType", Qt), "Popup")


def _no_focus() -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")


def _strong_focus() -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")


def _elide_right() -> object:
    return getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")


class SummaryButton(QPushButton):
    """The row's summary: elided text, full text in the tooltip, ▾, opens the popover.

    Enter, Space, Alt+Down and a click open it. Its accessible name is
    "{Row label}: {summary}" (UX-PED-003).
    """

    def __init__(self, row_label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.summary")
        self.setFocusPolicy(_strong_focus())  # type: ignore[arg-type]
        self.setAutoDefault(False)
        self.setDefault(False)
        self._row_label = row_label
        self._full = ""
        self._opener: Optional[Callable[[], None]] = None
        self.setMinimumWidth(0)
        self.clicked.connect(self._open)
        self.set_summary("")

    @property
    def summary(self) -> str:
        return self._full

    def set_row_label(self, row_label: str) -> None:
        self._row_label = row_label
        self._name()

    def set_summary(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()
        self._name()

    def set_opener(self, opener: Optional[Callable[[], None]]) -> None:
        self._opener = opener

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        modifiers = event.modifiers()  # type: ignore[attr-defined]
        alt = bool(modifiers & _modifier("AltModifier"))
        if key in (_key("Key_Return"), _key("Key_Enter")) or (alt and key == _key("Key_Down")):
            self._open()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)

    def _open(self) -> None:
        opener = self._opener
        if opener is not None:
            opener()

    def _elide(self) -> None:
        available = max(0, self.width() - 28)
        shown = QFontMetrics(self.font()).elidedText(self._full, _elide_right(), available) if self._full else ""
        self.setText(("%s %s" % (shown, ARROW)).strip() if self._full else ARROW)

    def _name(self) -> None:
        summary = self._full or "Default"
        self.setAccessibleName("%s: %s" % (self._row_label, summary))


class _Guard(QObject):
    """App-level filter for an open popover: keys, outside clicks and the Ctrl+Z hand-off."""

    def __init__(self, popover: "RowPopover") -> None:
        super().__init__(popover)
        self._popover = popover

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        return self._popover.filter_event(watched, event)


_TEXT_KINDS = (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox)


class RowPopover(QFrame):
    """A popover over a row. ``body`` takes the editor's fields; the footer has Reset and Done."""

    def __init__(
        self,
        row: QWidget,
        host: "EditorHost",
        *,
        row_label: str,
        session_label: str,
        qt_name: str = "",
        anchor: Optional[QWidget] = None,
        large: bool = False,
    ) -> None:
        super().__init__(row.window())
        self.setObjectName("formBuilder.rowPopover")
        self.setAccessibleName("%s editor" % row_label)
        self._row = row
        self._anchor = anchor
        self._large = large
        self._chrome = host.chrome
        self._session: "EditSession" = host.begin_session(session_label)
        self._closed = False
        self._guard = _Guard(self)
        self._subscription: Optional[Callable[[], None]] = None
        self._reset_callback: Optional[Callable[[], None]] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        outer.setSpacing(8)
        title = QLabel(row_label, self)
        title.setObjectName("formBuilder.popoverTitle")
        outer.addWidget(title)
        if qt_name:
            qt = QLabel(qt_name, self)
            qt.setObjectName("formBuilder.popoverQtName")
            outer.addWidget(qt)
        self._body = QWidget(self)
        self._body.setObjectName("formBuilder.popoverBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(6)
        outer.addWidget(self._body)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        self._reset = QPushButton("Reset", self)
        self._reset.setObjectName("formBuilder.popoverReset")
        self._reset.clicked.connect(self._on_reset)
        self._reset.hide()
        self._done = QPushButton("Done", self)
        self._done.setObjectName("formBuilder.popoverDone")
        self._done.setDefault(True)
        self._done.clicked.connect(self.done)
        footer.addWidget(self._reset, 0)
        footer.addStretch(1)
        footer.addWidget(self._done, 0)
        outer.addLayout(footer)
        self._apply_style()
        if not large:
            self.setMaximumWidth(MAX_WIDTH)
        self.hide()

    # -- content ---------------------------------------------------------

    def body(self) -> QVBoxLayout:
        return self._body_layout

    @property
    def session(self) -> "EditSession":
        return self._session

    @property
    def closed(self) -> bool:
        return self._closed

    def set_reset(self, callback: Optional[Callable[[], None]]) -> None:
        """Reset appears only when there is a value to reset (UX-PED-003). Its click closes the popover."""
        self._reset_callback = callback
        self._reset.setVisible(callback is not None)

    def focusables(self) -> List[QWidget]:
        found: List[QWidget] = []
        for widget in self.findChildren(QWidget):
            if widget.isVisibleTo(self) and widget.isEnabled() and widget.focusPolicy() != _no_focus():
                found.append(widget)
        return found

    # -- opening and placement ------------------------------------------

    def open_popover(self) -> None:
        """Place, show, take focus, and start listening for the closing events."""
        if self._closed:
            return
        self.place()
        self.show()
        self.raise_()
        QApplication.instance().installEventFilter(self._guard)  # type: ignore[union-attr]
        self._subscription = self._session.watch(self.close_for_structure)
        first = self.focusables()
        if first:
            first[0].setFocus()

    def place(self) -> None:
        window = self.parentWidget()
        if window is None:
            return
        width = _width_for(self._row.width(), self._large)
        self.setFixedWidth(width)
        self.adjustSize()
        height = self.height()
        rect = QRect(self._row.mapTo(window, QPoint(0, 0)), self._row.size())
        if self._large:
            x = rect.right() - width + 1
        else:
            x = rect.left()
        x = max(0, min(x, window.width() - width))
        below = rect.bottom() + GAP + 1
        above = rect.top() - GAP - height
        if below + height <= window.height():
            y = below
        elif above >= 0:
            y = above
        else:
            y = max(0, min(below, window.height() - height))
        self.move(x, y)

    def apply_chrome_shadow(self) -> None:
        """UX-ELEV-001 level 2: a soft shadow. High contrast has none (a 2 px border instead)."""
        if self._chrome.is_high_contrast:
            self.setGraphicsEffect(None)
            return
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(_ELEVATION_BLUR)
        shadow.setOffset(0, _ELEVATION_OFFSET_Y)
        shadow.setColor(QColor(0, 0, 0, _ELEVATION_ALPHA))
        self.setGraphicsEffect(shadow)

    def _apply_style(self) -> None:
        tokens = self._chrome.fb
        border = 2 if self._chrome.is_high_contrast else 1
        edge = self._chrome.text if self._chrome.is_high_contrast else tokens.popup_border
        self.setStyleSheet(
            "QFrame#formBuilder\\.rowPopover { background: %(fill)s; border: %(border)dpx solid %(edge)s;"
            " border-radius: 6px; }"
            "QFrame#formBuilder\\.rowPopover QLabel { color: %(text)s; background: transparent; border: none; }"
            "QLabel#formBuilder\\.popoverTitle { font-weight: 600; }"
            "QLabel#formBuilder\\.popoverQtName { color: %(faint)s; }"
            "QPushButton { color: %(text)s; background: %(input)s; border: 1px solid %(border)s;"
            " border-radius: 4px; padding: 6px 10px; }"
            "QPushButton:hover { background: %(hover)s; }"
            "QPushButton#formBuilder\\.popoverDone { background: %(accent)s; color: %(on_accent)s;"
            " border: none; font-weight: 600; }"
            % {
                "fill": tokens.popup,
                "border": border,
                "edge": edge,
                "text": self._chrome.text,
                "faint": self._chrome.faint,
                "input": self._chrome.input,
                "hover": self._chrome.row_hover,
                "accent": self._chrome.accent,
                "on_accent": self._chrome.on_accent,
            }
        )
        self.apply_chrome_shadow()

    # -- closing ---------------------------------------------------------

    def done(self, *_args: object) -> None:
        """Close and keep the writes. Focus returns to the summary button."""
        self._close(restore_focus=True)

    def revert(self) -> None:
        """Esc: undo everything this popover wrote, then close."""
        if self._closed:
            return
        self._session.revert()
        self._close(restore_focus=True)

    def undo_and_close(self) -> None:
        """Ctrl+Z outside a text field: close, keep, then undo the session as one step."""
        if self._closed:
            return
        self._close(restore_focus=True)
        self._session.undo()

    def _on_reset(self) -> None:
        callback = self._reset_callback
        if callback is None:
            return
        callback()
        self._close(restore_focus=True)

    def _close(self, *, restore_focus: bool) -> None:
        if self._closed:
            return
        self._closed = True
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._guard)
        if self._subscription is not None:
            self._subscription()
            self._subscription = None
        self._session.close()
        self.hide()
        if restore_focus:
            self._restore_focus()
            # A click that closed the popover may still move focus after this; put it back once it has.
            QTimer.singleShot(0, self._restore_focus)
        if wrapper_is_valid(self):
            self.deleteLater()

    def _restore_focus(self) -> None:
        anchor = self._anchor
        if anchor is not None and wrapper_is_valid(anchor) and anchor.isVisible():
            anchor.setFocus()

    def close_for_structure(self, *_args: object) -> None:
        """A selection change or a structural command closes the popover and keeps the writes."""
        self._close(restore_focus=False)

    # -- events ----------------------------------------------------------

    def filter_event(self, watched: QObject, event: QEvent) -> bool:
        if self._closed:
            return False
        kind = event.type()
        if kind == _event("KeyPress"):
            return self._key(event)
        if kind == _event("ShortcutOverride"):
            key = event.key()  # type: ignore[attr-defined]
            mods = event.modifiers()  # type: ignore[attr-defined]
            if key == _key("Key_Z") and bool(mods & _modifier("ControlModifier")) and not self._in_text():
                event.accept()  # type: ignore[attr-defined]
                return True
            return False
        if kind == _event("MouseButtonPress") and isinstance(watched, QWidget):
            return self._outside_press(watched)
        return False

    def _in_text(self) -> bool:
        focus = QApplication.focusWidget()
        return isinstance(focus, _TEXT_KINDS)

    def _focus_inside(self) -> bool:
        focus = QApplication.focusWidget()
        return focus is not None and (focus is self or self.isAncestorOf(focus))

    def _key(self, event: QEvent) -> bool:
        if not self._focus_inside():
            return False
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        if key == _key("Key_Escape"):
            self.revert()
            return True
        if key in (_key("Key_Tab"), _key("Key_Backtab")):
            self._cycle(backward=key == _key("Key_Backtab") or bool(mods & _modifier("ShiftModifier")))
            return True
        if key in (_key("Key_Return"), _key("Key_Enter")):
            # The field handles Enter first (its editor commits), then the popover closes.
            if isinstance(QApplication.focusWidget(), QLineEdit):
                QTimer.singleShot(0, self._done_later)
            return False
        if key == _key("Key_Z") and bool(mods & _modifier("ControlModifier")) and not self._in_text():
            self.undo_and_close()
            return True
        return False

    def _done_later(self) -> None:
        if wrapper_is_valid(self):
            self.done()

    def _cycle(self, *, backward: bool) -> None:
        stops = self.focusables()
        if not stops:
            return
        focus = QApplication.focusWidget()
        index = stops.index(focus) if focus in stops else -1
        step = -1 if backward else 1
        stops[(index + step) % len(stops)].setFocus()

    def _outside_press(self, target: QWidget) -> bool:
        if self._contains(target):
            return False
        if target.windowFlags() & _window_flag_popup():  # a combo list or menu the popover opened
            return False
        anchor = self._anchor
        if anchor is not None and wrapper_is_valid(anchor) and (target is anchor or anchor.isAncestorOf(target)):
            # The summary toggles: close here and swallow the press, so the click does not reopen it.
            self.done()
            return True
        self.done()
        return False

    def _contains(self, target: QWidget) -> bool:
        return target is self or self.isAncestorOf(target)


def _width_for(row_width: int, large: bool) -> int:
    if large:
        return min(max(row_width, LARGE_MIN_WIDTH), LARGE_MAX_WIDTH)
    return min(max(row_width, MIN_WIDTH), MAX_WIDTH)


__all__ = ["GAP", "LARGE_MAX_WIDTH", "LARGE_MIN_WIDTH", "MAX_WIDTH", "MIN_WIDTH", "RowPopover", "SummaryButton"]
