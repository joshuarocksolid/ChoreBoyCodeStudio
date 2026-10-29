"""The row popover shell and the summary button (UX-PED-003, UX-PED-004).

Helper module: underscore, not registered. Editors open a ``RowPopover`` from
their row's ``SummaryButton``. Nothing here knows a property; the editor writes
through ``host.commit(value, session=popover.session)`` or ``popover.session.run``.

Session rules (see ``_services``): the popover's session is opened when the
popover is built. A keep close (Done, Enter in a one-line field or a spin box,
a click outside, a selection change, a structural command, a tab switch, a
pane hide, a window resize) moves focus to the summary first, so a field's
focus-out commit joins the session, then closes the session. ``revert()``
(Esc) does the same flush and then rolls the session back, so the document
and the undo stack are as they were before the popover opened. Ctrl+Z
(``QKeySequence.StandardKey.Undo``, not Ctrl+Shift+Z) outside a text field
keeps, then undoes that one step; with nothing written it is the form's
Undo, and that step closes the popover. Enter inside a list (or a widget that sets
``fbEnterStays``) does not close. Tab inside a multi-line editor does not cycle.

Focus: while open, focus stays in the popover; when it closes, focus goes to
the summary button, whatever closed it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from app.qt.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from app.features.form_builder.qtside.theme.chrome import apply_level2_shadow, control_qss
from app.qt.QtGui import QColor, QFontMetrics, QKeySequence, QPalette
from app.qt.QtWidgets import (
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import event_global_pos, wrapper_is_valid

if TYPE_CHECKING:
    from app.features.form_builder.qtside.inspector.api import EditorHost, EditSession
    from app.features.form_builder.qtside.theme.chrome import FormChrome

#: UX-PED-003 widths: the inspector content width, clamped; large editors 320-480 and grow left.
MIN_WIDTH = 236
MAX_WIDTH = 320
LARGE_MIN_WIDTH = 320
LARGE_MAX_WIDTH = 480
GAP = 4
PADDING = 12
ARROW = "▾"


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _modifier(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _mouse(name: str) -> object:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _event(name: str) -> object:
    return getattr(getattr(QEvent, "Type", QEvent), name)


def _no_focus() -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")


def _strong_focus() -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")


def popover_title(row_label: str, qt_name: str) -> str:
    """The popover's title. A row labelled by its Qt name (All properties,
    custom properties) gets friendly words; the Qt name stays the caption."""
    if not row_label or row_label != qt_name:
        return row_label
    words: List[str] = []
    for index, ch in enumerate(row_label):
        if index and ch.isupper() and not row_label[index - 1].isupper():
            words.append(" ")
        words.append(ch.lower() if index else ch.upper())
    return "".join(words)


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
        self._elided_for: Optional[Tuple[str, int]] = None
        self._named_for: Optional[Tuple[str, str]] = None
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
        if text != self._full or self._elided_for is None:
            self._full = text
            self.setToolTip(text)
        self._elide()
        self._name()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (_event("FontChange"), _event("StyleChange")):
            self._elided_for = None

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
        # Eliding measures the text; skip it when neither the text nor the width changed.
        if self._elided_for == (self._full, available):
            return
        self._elided_for = (self._full, available)
        shown = QFontMetrics(self.font()).elidedText(self._full, _elide_right(), available) if self._full else ""
        self.setText(("%s %s" % (shown, ARROW)).strip() if self._full else ARROW)

    def _name(self) -> None:
        summary = self._full or "Default"
        if self._named_for == (self._row_label, summary):
            return
        self._named_for = (self._row_label, summary)
        self.setAccessibleName("%s: %s" % (self._row_label, summary))


class _Guard(QObject):
    """App-level filter for an open popover: keys, outside clicks and the Ctrl+Z hand-off."""

    def __init__(self, popover: "RowPopover") -> None:
        super().__init__(popover)
        self._popover = popover

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        return self._popover.filter_event(watched, event)


_TEXT_KINDS = (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox)
_MULTILINE = (QPlainTextEdit, QTextEdit)
_ENTER_COMMITS = (QLineEdit, QAbstractSpinBox)


def _keeps_tab(widget: object) -> bool:
    """A multi-line box that types a tab. One that hands Tab on (tabChangesFocus) cycles with the popover."""
    return isinstance(widget, _MULTILINE) and not widget.tabChangesFocus()


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
        on_keep: Optional[Callable[[], None]] = None,
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
        self._on_keep = on_keep
        self._window_size: Optional[object] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        outer.setSpacing(8)
        # A custom property's name is its label (UX-PED-060): no friendly
        # words, and no second copy of the name as the caption.
        custom = bool(getattr(row, "is_custom", False))
        title = QLabel(row_label if custom else popover_title(row_label, qt_name), self)
        title.setObjectName("formBuilder.popoverTitle")
        outer.addWidget(title)
        if qt_name and not (custom and qt_name == row_label):
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
        self._paint_wells()
        self.place()
        self.show()
        self.raise_()
        self._guard_wheels()
        window = self.window()
        self._window_size = window.size() if window is not None else None
        QApplication.instance().installEventFilter(self._guard)  # type: ignore[union-attr]
        self._subscription = self._session.watch(self.close_for_structure)
        first = self.focusables()
        if first:
            first[0].setFocus()

    def _guard_wheels(self) -> None:
        """UX-PED-005 for fields the popover owns. The row's guard does not cover them.

        The same filter lives on the row. This copy stays here because an editor
        module may import ``inspector.api`` and not ``_properties``.
        """
        _install_wheel_guard(self._body)

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

    @property
    def row(self) -> QWidget:
        return self._row

    def restyle(self, chrome: "FormChrome") -> None:
        """A live theme switch while the popover is open: new colours, same content."""
        if self._closed or chrome is self._chrome:
            return
        self._chrome = chrome
        self._apply_style()
        self._paint_wells()

    def apply_chrome_shadow(self) -> None:
        """UX-ELEV-001 level 2: a soft shadow. High contrast has none (a 2 px border instead)."""
        apply_level2_shadow(self, self._chrome)

    def _apply_style(self) -> None:
        tokens = self._chrome.fb
        frame_px = 2 if self._chrome.is_high_contrast else 1
        edge = self._chrome.text if self._chrome.is_high_contrast else tokens.popup_border
        focus = self._chrome.focus_width if self._chrome.focus_width > 0 else 1
        # The popover is parented to the window, so it does not inherit the
        # inspector sheet. The field rules are the pane's, scoped under the
        # frame. The Qt-name rule names both the frame and the label: a bare
        # ``QLabel#id`` loses to ``QFrame#id QLabel`` and the caption stays
        # body colour instead of faint.
        frame = "QFrame#formBuilder\\.rowPopover"
        fields = (
            "QLineEdit",
            "QSpinBox",
            "QDoubleSpinBox",
            "QComboBox",
            "QPlainTextEdit",
            "QTextEdit",
            "QKeySequenceEdit",
            "QListWidget",
            "QFontComboBox",
        )
        field_sel = ", ".join("%s %s" % (frame, kind) for kind in fields)
        focus_sel = ", ".join("%s %s:focus" % (frame, kind) for kind in fields)
        state_kinds = (
            "QLineEdit",
            "QComboBox",
            "QSpinBox",
            "QDoubleSpinBox",
            "QFontComboBox",
            "QCheckBox",
            "QPlainTextEdit",
            "QPushButton#formBuilder\\.summary",
        )
        unset_sel = ", ".join('%s %s[fbState="unset"]' % (frame, kind) for kind in state_kinds)
        mixed_sel = ", ".join(
            '%s %s[fbState="mixed"]' % (frame, kind) for kind in state_kinds + ("QListWidget",)
        )
        self.setStyleSheet(
            (
            "%(frame)s { background: %(fill)s; border: %(frame_px)dpx solid %(edge)s; border-radius: 6px; }"
            "%(frame)s QScrollArea { background: %(input)s; border: none; }"
            "%(frame)s QLabel { color: %(text)s; background: transparent; border: none; }"
            "%(frame)s QCheckBox { color: %(text)s; background: transparent; }"
            "%(frame)s QLabel#formBuilder\\.rowError { color: %(error)s; }"
            "%(frame)s QLabel#formBuilder\\.popoverTitle { color: %(text)s; font-size: 13px; font-weight: 600; }"
            "%(frame)s QLabel#formBuilder\\.popoverQtName { color: %(faint)s; font-size: 11px; font-weight: 400; }"
            "%(fields)s { background: %(input)s; color: %(text)s; border: 1px solid %(line)s; }"
            "%(unset)s { color: %(faint)s; }"
            "%(mixed)s { color: %(faint)s; font-style: italic; }"
            "%(focused)s { border: %(focus)dpx solid %(accent)s; }"
            "%(frame)s QPushButton:!flat { color: %(text)s; background: %(input)s; border: 1px solid %(line)s;"
            " border-radius: 4px; padding: 6px 10px; }"
            "%(frame)s QPushButton:!flat:hover { background: %(hover)s; }"
            "%(frame)s QPushButton:!flat:checked { background: %(accent)s; color: %(on_accent)s; }"
            "%(frame)s QPushButton[fbGlyph=\"true\"] { padding: 2px 6px; }"
            # Tool buttons (font B I U S, size presets, resets) and the drop-down
            # lists of combos would otherwise be native, light in a dark theme.
            "%(frame)s QToolButton { color: %(text)s; background: %(input)s; border: 1px solid %(line)s;"
            " border-radius: 4px; padding: 2px 6px; }"
            "%(frame)s QToolButton::menu-indicator { image: none; width: 0px; }"
            "%(frame)s QToolButton:hover { background: %(hover)s; }"
            "%(frame)s QToolButton:checked { background: %(accent)s; color: %(on_accent)s; }"
            "%(frame)s QToolButton:focus { border: %(focus)dpx solid %(accent)s; }"
            "%(frame)s QComboBox QAbstractItemView { background: %(input)s; color: %(text)s;"
            " border: 1px solid %(line)s; selection-background-color: %(accent)s;"
            " selection-color: %(on_accent)s; }"
            "%(frame)s QPushButton#formBuilder\\.popoverDone { background: %(accent)s; color: %(on_accent)s;"
            " border: none; font-weight: 600; }"
            % {
                "frame": frame,
                "fields": field_sel,
                "unset": unset_sel,
                "mixed": mixed_sel,
                "focused": focus_sel,
                "fill": tokens.popup,
                "frame_px": frame_px,
                "edge": edge,
                "text": self._chrome.text,
                "faint": self._chrome.faint,
                "error": self._chrome.error,
                "input": self._chrome.input,
                "line": self._chrome.border,
                "hover": self._chrome.row_hover,
                "accent": self._chrome.accent,
                "on_accent": self._chrome.on_accent,
                "focus": focus,
            }
            )
            + control_qss(self._chrome)
        )
        self.apply_chrome_shadow()

    def _paint_wells(self) -> None:
        """Scroll wells inside the popover keep the input colour. A bare viewport stays the platform white."""
        color = QColor(self._chrome.input)
        for scroll in self.findChildren(QScrollArea):
            for widget in (scroll.viewport(), scroll.widget()):
                if widget is None:
                    continue
                palette = widget.palette()
                palette.setColor(QPalette.Window, color)
                palette.setColor(QPalette.Base, color)
                widget.setPalette(palette)
                widget.setAutoFillBackground(True)

    # -- closing ---------------------------------------------------------

    def done(self, *_args: object) -> None:
        """Close and keep the writes. Focus returns to the summary button."""
        self._close(restore_focus=True, keep=True)

    def revert(self) -> None:
        """Esc: undo everything this popover wrote, then close."""
        self._close(restore_focus=True, keep=False)

    def undo_and_close(self) -> None:
        """Ctrl+Z outside a text field: close, keep, then undo the session as one step."""
        if self._closed:
            return
        self._close(restore_focus=True, keep=True)
        self._session.undo()

    def _on_reset(self) -> None:
        callback = self._reset_callback
        if callback is None:
            return
        callback()
        self._close(restore_focus=True, keep=True)

    def _close(self, *, restore_focus: bool, keep: bool) -> None:
        if self._closed:
            return
        self._closed = True
        self._unwatch()
        # Focus leaves the field while the session is still open, so
        # editingFinished commits into this step. A keep close then ends the
        # session. Esc rolls that step back, pending text included.
        self._flush_focus()
        if keep and self._on_keep is not None:
            self._on_keep()
        if keep:
            self._session.close()
        else:
            self._session.revert()
        self.hide()
        if restore_focus:
            self._restore_focus()
            # A click that closed the popover may still move focus after this; put it back once it has.
            QTimer.singleShot(0, self._restore_focus)
        if wrapper_is_valid(self):
            self.deleteLater()

    def _flush_focus(self) -> None:
        anchor = self._anchor
        if anchor is not None and wrapper_is_valid(anchor):
            anchor.setFocus()
            return
        focus = QApplication.focusWidget()
        if isinstance(focus, QWidget) and (focus is self or self.isAncestorOf(focus)):
            focus.clearFocus()

    def _unwatch(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._guard)
        if self._subscription is not None:
            self._subscription()
            self._subscription = None

    def _restore_focus(self) -> None:
        anchor = self._anchor
        if anchor is not None and wrapper_is_valid(anchor) and anchor.isVisible():
            anchor.setFocus()

    def close_for_structure(self, *_args: object) -> None:
        """A selection change or a structural command closes the popover and keeps the writes."""
        self._close(restore_focus=False, keep=True)

    # -- events ----------------------------------------------------------

    def filter_event(self, watched: QObject, event: QEvent) -> bool:
        if self._closed:
            return False
        kind = event.type()
        if kind == _event("KeyPress"):
            return self._key(event)
        if kind == _event("ShortcutOverride"):
            return self._shortcut(event)
        if kind == _event("MouseButtonPress") and isinstance(watched, QWidget):
            return self._outside_press(watched, event)
        if kind == _event("Wheel") and isinstance(watched, QWidget):
            return self._wheel(watched, event)
        if kind in (_event("Hide"), _event("Destroy")) and isinstance(watched, QWidget):
            return self._lifetime(watched)
        if kind == _event("Resize") and watched is self.window():
            size = watched.size()  # type: ignore[attr-defined]
            if size == self._window_size:
                return False
            self._window_size = size
            self.done()
            return False
        return False

    def _in_text(self) -> bool:
        focus = QApplication.focusWidget()
        return isinstance(focus, _TEXT_KINDS)

    def _focus_inside(self) -> bool:
        focus = QApplication.focusWidget()
        return focus is not None and (focus is self or self.isAncestorOf(focus))

    def _is_undo(self, event: QEvent) -> bool:
        matches = getattr(event, "matches", None)
        if not callable(matches):
            return False
        return bool(matches(getattr(QKeySequence.StandardKey, "Undo")))

    def _enter_stays(self) -> bool:
        """A list editor uses Enter to add a row (UX-CONT-019). It must not close the popover."""
        widget = QApplication.focusWidget()
        while isinstance(widget, QWidget):
            if isinstance(widget, QAbstractItemView) or bool(widget.property("fbEnterStays")):
                return True
            if widget is self:
                return False
            widget = widget.parentWidget()
        return False

    def _key(self, event: QEvent) -> bool:
        if not self._focus_inside():
            return False
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        if key == _key("Key_Escape"):
            self.revert()
            return True
        if key in (_key("Key_Tab"), _key("Key_Backtab")):
            if bool(mods & _modifier("ControlModifier")) or _keeps_tab(QApplication.focusWidget()):
                return False
            self._cycle(backward=key == _key("Key_Backtab") or bool(mods & _modifier("ShiftModifier")))
            return True
        if key in (_key("Key_Return"), _key("Key_Enter")):
            # The field handles Enter first (its editor commits), then the popover closes.
            if not self._enter_stays() and isinstance(QApplication.focusWidget(), _ENTER_COMMITS):
                QTimer.singleShot(0, self._done_later)
            return False
        if self._is_undo(event) and not self._in_text() and self._session.has_step():
            self.undo_and_close()
            return True
        return False

    def _shortcut(self, event: QEvent) -> bool:
        """A window-level Esc, Tab or Return shortcut must not win while focus is in here."""
        if not self._focus_inside():
            return False
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        accept = False
        if self._is_undo(event) and not self._in_text() and self._session.has_step():
            # With nothing written, Ctrl+Z is the form's Undo; that foreign step closes the popover.
            accept = True
        elif key == _key("Key_Escape"):
            accept = True
        elif key in (_key("Key_Tab"), _key("Key_Backtab")):
            accept = not bool(mods & _modifier("ControlModifier")) and not _keeps_tab(
                QApplication.focusWidget()
            )
        elif key in (_key("Key_Return"), _key("Key_Enter")):
            accept = not self._enter_stays()
        if not accept:
            return False
        event.accept()  # type: ignore[attr-defined]
        return True

    def _wheel(self, target: QWidget, event: QEvent) -> bool:
        """Scrolling the inspector (or anything else in the window) closes and keeps.

        A wheel over the popover that nothing in it takes propagates to the
        window; the point is still inside the popover, so it stays open.
        """
        if target is self or self.isAncestorOf(target):
            return False
        if target.window() is not self.window():
            return False
        if self.rect().contains(self.mapFromGlobal(event_global_pos(event))):
            return False
        self.done()
        return False

    def _lifetime(self, watched: QWidget) -> bool:
        """Hide or destroy of the row or an ancestor (a tab switch, a pane hide) closes and keeps."""
        if watched is self or self.isAncestorOf(watched):
            return False
        if not self._on_row_chain(watched):
            return False
        self.done()
        return False

    def _on_row_chain(self, widget: QWidget) -> bool:
        cursor: Optional[QWidget] = self._row if wrapper_is_valid(self._row) else None
        while cursor is not None and wrapper_is_valid(cursor):
            if cursor is widget:
                return True
            if cursor.isWindow():
                return False
            cursor = cursor.parentWidget()
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

    def _outside_press(self, target: QWidget, event: QEvent) -> bool:
        # A combo list and a child dialog are their own windows. A modal file
        # picker is activeModalWidget. Both count as inside (M4.3c).
        if QApplication.activeModalWidget() is not None:
            return False
        if target.window() is not self.window():
            return False
        if self.rect().contains(self.mapFromGlobal(event_global_pos(event))):
            return False
        anchor = self._anchor
        swallow = (
            anchor is not None
            and wrapper_is_valid(anchor)
            and (target is anchor or anchor.isAncestorOf(target))
        )
        self.done()
        return swallow


_WHEEL_EVENT = getattr(getattr(QEvent, "Type", QEvent), "Wheel")
_WHEEL_KINDS = (QAbstractSpinBox, QComboBox, QAbstractSlider)


class _WheelGuard(QObject):
    """A spin box, combo or slider ignores the wheel until it has focus."""

    def __init__(self, target: QWidget) -> None:
        super().__init__(target)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() != _WHEEL_EVENT:
            return False
        focus = QApplication.focusWidget()
        if focus is not None and isinstance(watched, QWidget) and (
            focus is watched or watched.isAncestorOf(focus)
        ):
            return False
        event.ignore()
        return True


def _install_wheel_guard(root: QWidget) -> None:
    for target in [root, *root.findChildren(QWidget)]:
        if isinstance(target, _WHEEL_KINDS):
            target.installEventFilter(_WheelGuard(target))


def _width_for(row_width: int, large: bool) -> int:
    if large:
        return min(max(row_width, LARGE_MIN_WIDTH), LARGE_MAX_WIDTH)
    return min(max(row_width, MIN_WIDTH), MAX_WIDTH)


__all__ = ["GAP", "LARGE_MAX_WIDTH", "LARGE_MIN_WIDTH", "MAX_WIDTH", "MIN_WIDTH", "RowPopover", "SummaryButton"]
