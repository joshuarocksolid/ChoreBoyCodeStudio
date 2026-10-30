"""The Events section (UX-BEH-003). The sender line and the newer-logic notice live here."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QKeyEvent, QResizeEvent
from app.qt.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected
from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection, SectionHost, SectionInputs
from app.features.form_builder.qtside.inspector.behavior_ext._rows import (
    TWO_PLACES,
    EventView,
    Gesture,
    SenderView,
    StepView,
    finish,
    project_sender,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import warning_color
from app.features.form_builder.qtside.inspector.model import ManyBehavior
from app.features.form_builder.qtside.pickers import method_actions, open_event_picker
from app.features.form_builder.qtside.pickers.flow import PickerSource

_UP = enum_value(Qt.Key.Key_Up)
_DOWN = enum_value(Qt.Key.Key_Down)
_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_DELETE = enum_value(Qt.Key.Key_Delete)
_SPACE = enum_value(Qt.Key.Key_Space)
_ESC = enum_value(Qt.Key.Key_Escape)
_F12 = enum_value(Qt.Key.Key_F12)
_MENU = enum_value(Qt.Key.Key_Menu)
_F10 = enum_value(Qt.Key.Key_F10)
_D = enum_value(Qt.Key.Key_D)
_PERIOD = enum_value(Qt.Key.Key_Period)


class EventsBody(QWidget):
    def __init__(self, host: SectionHost) -> None:
        super().__init__(host.parent)
        self.setObjectName("formBuilder.events")
        self._services = host.services
        self._chrome = host.services.chrome
        self._refresh: Optional[Callable[[], None]] = None
        self._view: Optional[SenderView] = None
        self._sender = ""
        self._chain: List[QWidget] = []
        self._focus: Optional[Tuple[str, int]] = None
        self._picker: Optional[QWidget] = None
        self._line = QLabel(self)
        self._line.setObjectName("formBuilder.events.sender")
        self._notice = QLabel(self)
        self._notice.setWordWrap(True)
        self._notice.setObjectName("formBuilder.events.notice")
        overline = QWidget(self)
        row = QHBoxLayout(overline)
        row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("EVENTS", overline)
        title.setObjectName("formBuilder.events.overline")
        row.addWidget(title)
        row.addStretch(1)
        self._when = QPushButton("+ When\u2026", overline)
        self._when.clicked.connect(self._add_event)
        self._when.installEventFilter(self)
        row.addWidget(self._when)
        self._events = QVBoxLayout()
        self._events.setContentsMargins(0, 0, 0, 0)
        self._events.setSpacing(2)
        self._empty = QLabel(self)
        self._empty.setWordWrap(True)
        self._caption = QLabel(self)
        self._caption.setWordWrap(True)
        self._message = QLabel(self)
        self._message.setWordWrap(True)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 4, 0, 4)
        column.setSpacing(4)
        column.addWidget(self._line)
        column.addWidget(self._notice)
        column.addWidget(overline)
        self._overline = overline
        column.addLayout(self._events)
        column.addWidget(self._empty)
        column.addWidget(self._caption)
        column.addWidget(self._message)
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus)  # type: ignore[attr-defined]

    def set_refresh(self, refresh: Callable[[], None]) -> None:
        self._refresh = refresh

    def apply_colors(self, panel: str, text: str) -> None:
        chrome = self._chrome
        self.setStyleSheet(
            "QWidget#formBuilder\\.events, QWidget#formBuilder\\.events QWidget { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.events\\.notice { color: %s; }"

            "QPushButton { color: %s; background: %s; border: 1px solid %s; border-radius: 4px; padding: 2px 8px; }"
            "QPushButton:focus, QToolButton:focus, QWidget:focus { border: %dpx solid %s; }"
            % (
                panel,
                text,
                text,
                warning_color(chrome),
                text,
                chrome.input,
                chrome.border,
                chrome.focus_width,
                chrome.accent,
            )
        )

    def _picker_open(self) -> bool:
        picker = self._picker
        if picker is None:
            return False
        try:
            return bool(picker.isVisible())
        except RuntimeError:
            # Qt deleted the popup (a later popup took its place).
            self._picker = None
            return False

    def has_draft(self) -> bool:
        return self._picker_open()

    def discard_draft(self) -> bool:
        if not self._picker_open():
            return False
        picker = self._picker
        if picker is None:
            return False
        picker.hide()
        return True

    def note_added(self, signal: str, index: int) -> None:
        self._focus = (signal, index)

    def focus_step(self, signal: str, index: int) -> None:
        self.note_added(signal, index)
        self._place_focus()

    def paint(self, inputs: SectionInputs) -> None:
        self._chrome = self._services.chrome
        doc = inputs.session.document
        view = inputs.view
        if isinstance(view, ManyBehavior):
            shown = project_sender(doc, QtClassTable.shared(), "", kind="many")
        else:
            self._sender = view.sender_name
            shown = project_sender(
                doc, QtClassTable.shared(), view.sender_name, qt_names=_qt_names(self)
            )
        if shown == self._view:
            return
        self._view = shown
        self._render(shown)

    def _render(self, shown: SenderView) -> None:
        editing = shown.kind == "one" and not shown.read_only
        self._line.setText(shown.line)
        self._line.setVisible(bool(shown.line))
        self._notice.setText(shown.notice)
        self._notice.setVisible(bool(shown.notice))
        self._message.setText(shown.message)
        self._message.setVisible(bool(shown.message))
        self._overline.setVisible(shown.kind == "one")
        self._when.setVisible(editing)
        self._when.setObjectName("formBuilder.events.first" if editing and not shown.events else "formBuilder.events.when")
        self._empty.setText(shown.empty if shown.kind == "one" and not shown.events else "")
        self._empty.setVisible(bool(self._empty.text()))
        self._caption.setText(shown.caption)
        self._caption.setVisible(bool(shown.caption))
        self._remember_focus()
        while self._events.count():
            item = self._events.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setObjectName("")
                widget.deleteLater()
        self._chain = []
        if shown.kind != "one":
            return
        first = True
        for event in shown.events:
            group = _Group(self, event, editing)
            self._events.addWidget(group)
            if first and (event.steps or event.unreadable or event.banner):
                group.mark_first()
                first = False
            self._chain.extend(group.chain())
        if editing and not shown.events:
            self._chain.append(self._when)
        self._place_focus()

    def first_focus(self) -> Optional[QWidget]:
        """The live row Alt+B should focus. Empty events land on + When…."""
        for widget in self._chain:
            if widget.isVisible():
                return widget
        if self._when.isVisible():
            return self._when
        return None

    def _remember_focus(self) -> None:
        if self._focus is not None:
            return
        focus = QApplication.focusWidget()
        if focus is None or not self.isAncestorOf(focus):
            return
        signal = getattr(focus, "signal_name", None)
        index = getattr(focus, "step_index", None)
        if isinstance(signal, str) and isinstance(index, int):
            self._focus = (signal, index)

    def _reveal(self, widget: QWidget) -> None:
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(widget)
                return
            parent = parent.parentWidget()

    def _place_focus(self) -> None:
        if self._focus is None:
            return
        signal, index = self._focus
        self._focus = None
        for widget in self._chain:
            if getattr(widget, "signal_name", None) == signal and getattr(widget, "step_index", -2) == index:
                widget.setFocus()
                self._reveal(widget)
                return

    def _on_focus(self, _old: object, _new: object) -> None:
        for index in range(self._events.count()):
            group = self._events.itemAt(index).widget()
            sync = getattr(group, "sync_then", None)
            if callable(sync):
                sync()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ShortcutOverride and isinstance(watched, (_Row, _ThenButton, QPushButton)):
            if watched is self._when or isinstance(watched, (_Row, _ThenButton)):
                if _claimed(event):  # type: ignore[arg-type]
                    event.accept()
                    return True
        if event.type() == QEvent.Type.KeyPress and watched is self._when:
            return self._when_key(event)  # type: ignore[arg-type]
        if event.type() == QEvent.Type.KeyPress and isinstance(watched, _ThenButton):
            return self._then_key(watched, event)  # type: ignore[arg-type]
        if event.type() == QEvent.Type.KeyPress and isinstance(watched, _Row):
            return self._key(watched, event)  # type: ignore[arg-type]
        return super().eventFilter(watched, event)

    def _when_key(self, event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        if key == _DOWN:
            if self._chain and self._chain[0] is not self._when:
                self._chain[0].setFocus()
            return True
        if key == _UP:
            return True
        if key == _ESC:
            self._to_canvas()
            return True
        return False

    def _then_key(self, button: "_ThenButton", event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        if key in _ENTER:
            button.click()
            return True
        if key == _UP:
            self._move(-1)
            return True
        if key == _DOWN:
            self._move(1)
            return True
        if key == _ESC:
            self._to_canvas()
            return True
        return False

    def _key(self, row: "_Row", event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        mods = enum_value(event.modifiers())
        alt = bool(mods & enum_value(Qt.KeyboardModifier.AltModifier))
        ctrl = bool(mods & enum_value(Qt.KeyboardModifier.ControlModifier))
        shift = bool(mods & enum_value(Qt.KeyboardModifier.ShiftModifier))
        if key == _UP and alt:
            return self._act(row, "move", -1)
        if key == _DOWN and alt:
            return self._act(row, "move", 1)
        if key == _UP:
            self._move(-1)
            return True
        if key == _DOWN:
            self._move(1)
            return True
        if key in _ENTER:
            self._activate(row)
            return True
        if key == _DELETE:
            return self._act(row, "delete_event" if row.step_index < 0 else "delete", 0)
        if key == _SPACE:
            return self._act(row, "toggle", 0)
        if key == _D and ctrl:
            return self._act(row, "duplicate", 0)
        if key == _ESC:
            self._to_canvas()
            return True
        if key == _F12:
            if row.method_name:
                self._go_code(row.method_name)
            return True
        if key == _PERIOD and ctrl:
            self._fix(row)
            return True
        if key == _MENU or (key == _F10 and shift):
            row.open_menu()
            return True
        return False

    def _move(self, delta: int) -> None:
        chain = [widget for widget in self._chain if widget.isVisible()]
        focus = QApplication.focusWidget()
        if focus not in chain:
            if chain:
                chain[0].setFocus()
            return
        index = chain.index(focus) + delta
        if 0 <= index < len(chain):
            chain[index].setFocus()
            self._reveal(chain[index])

    def _activate(self, row: "_Row") -> None:
        if row.step_index < 0:
            if not row.locked:
                self._open(PickerSource(self._sender, changing=row.signal_name), row)
            return
        if row.readonly:
            return
        self._open(PickerSource(self._sender, row.signal_name, replace_index=row.step_index), row)

    def _act(self, row: "_Row", kind: str, direction: int) -> bool:
        if row.step_index < 0 and kind != "delete_event":
            return True
        if kind == "delete_event" and row.step_index >= 0:
            kind = "delete"
        self._run(Gesture(kind, signal=row.signal_name, index=max(row.step_index, 0), direction=direction))
        return True

    def _add_event(self) -> None:
        self._open(PickerSource(self._sender), self._when)

    def _add_step(self, signal: str, button: QWidget) -> None:
        self._open(PickerSource(self._sender, signal), button)

    def _open(self, source: PickerSource, host: QWidget) -> None:
        if self._view is not None and self._view.read_only:
            self._run(Gesture("toggle"))
            return
        self._picker = open_event_picker(host, source, "")

    def _run(self, gesture: Gesture) -> None:
        doc = self._services.session.document
        outcome = finish(doc, QtClassTable.shared(), self._sender, gesture)
        if outcome is None:
            return
        if outcome.command is None:
            _narrate(self, outcome.status)
            return
        self.note_added(outcome.focus_signal, outcome.focus_index)
        result = self._services.execute(outcome.command)
        if isinstance(result, Rejected):
            _narrate(self, result.message)
            return
        if isinstance(result, Dropped):
            return
        if outcome.status:
            _narrate(self, outcome.status)

    def _fix(self, row: "_Row") -> None:
        event = getattr(row, "_event", None)
        if event is not None and getattr(event, "stored_twice", False) and row.step_index < 0:
            self._merge(row.signal_name)
            return
        if row.unreadable or (event is not None and event.banner):
            open_property_as_text(self, row.property_name, self._sender)

    def _go_code(self, method: str) -> None:
        service = method_actions()
        go = getattr(service, "go_to", None)
        surface = _surface(self)
        if callable(go) and surface is not None:
            go(surface, method)

    def _to_canvas(self) -> None:
        window = self.window()
        canvas = window.findChild(QWidget, "formBuilder.canvas") if window is not None else None
        if canvas is not None:
            canvas.setFocus()

    def _delete_event(self, signal: str) -> None:
        self._run(Gesture("delete_event", signal=signal))

    def _change_event(self, signal: str, host: QWidget) -> None:
        self._open(PickerSource(self._sender, changing=signal), host)

    def _merge(self, signal: str) -> None:
        self._run(Gesture("merge", signal=signal))


class _ThenButton(QPushButton):
    def __init__(self, body: EventsBody, signal: str, parent: QWidget) -> None:
        super().__init__("+ Then\u2026", parent)
        self._signal = signal
        self.clicked.connect(lambda: body._add_step(signal, self))
        self.installEventFilter(body)


class _Group(QWidget):
    def __init__(self, body: EventsBody, event: EventView, editing: bool) -> None:
        super().__init__(body)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._body = body
        self._editable = editing and not event.locked
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.header = _Row(body, event.signal, -1, event.header, event.accessible, event.locked, event.unreadable, False, event.property_name)
        if event.qt:
            self.header.set_faint(event.qt)
        menu = self.header.menu_button(event)
        if not event.unreadable and (event.locked or not editing):
            menu.setEnabled(False)
        column.addWidget(self.header)
        if event.banner:
            banner = QLabel(event.banner, self)
            banner.setWordWrap(True)
            banner.setMinimumWidth(0)
            banner.setStyleSheet("color: %s;" % body._chrome.error)
            column.addWidget(banner)
        if event.stored_twice:
            note = QWidget(self)
            line = QHBoxLayout(note)
            line.setContentsMargins(0, 0, 0, 0)
            label = QLabel(TWO_PLACES, note)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            label.setStyleSheet("color: %s;" % body._chrome.muted)
            line.addWidget(label, 1)
            merge = QPushButton("Merge", note)
            merge.setAccessibleName("Merge")
            merge.clicked.connect(lambda: body._merge(event.signal))
            merge.setEnabled(self._editable)
            line.addWidget(merge)
            column.addWidget(note)
        self._steps: List[_Row] = []
        for step in event.steps:
            row = _Row(
                body,
                event.signal,
                step.index,
                "%d  %s" % (step.index + 1, step.words),
                step.accessible,
                step.readonly or event.locked,
                False,
                step.missing or step.unknown,
                event.property_name,
                step,
            )
            if step.off:
                row.set_faint_text()
            if step.missing or (event.unreadable):
                row.set_error()
            column.addWidget(row)
            self._steps.append(row)
        self.then = _ThenButton(body, event.signal, self)
        self.then.setVisible(False)
        self.then.setEnabled(self._editable)
        column.addWidget(self.then)

    def mark_first(self) -> None:
        self.header.setObjectName("formBuilder.events.first")

    def chain(self) -> List[QWidget]:
        rows: List[QWidget] = [self.header]
        rows.extend(self._steps)
        rows.append(self.then)
        return rows

    def sync_then(self) -> None:
        if not self._editable:
            self.then.hide()
            return
        focus = QApplication.focusWidget()
        hot = focus is not None and self.isAncestorOf(focus)
        self.then.setVisible(hot)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self._editable:
            self.then.show()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        self.sync_then()


class _Row(QWidget):
    def __init__(
        self,
        body: EventsBody,
        signal: str,
        index: int,
        text: str,
        accessible: str,
        locked: bool,
        unreadable: bool,
        problem: bool,
        prop: str,
        step: Optional[StepView] = None,
    ) -> None:
        super().__init__(body)
        self.signal_name = signal
        self.step_index = index
        self.locked = locked
        self.readonly = locked
        self.unreadable = unreadable
        self.property_name = prop
        self.method_name = step.method if step is not None else ""
        self._off = bool(step is not None and step.off)
        self._body = body
        self._event = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(accessible)
        self.setToolTip(text)
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 0, 2, 0)
        self._label = QLabel(text, self)
        self._label.setMinimumWidth(0)
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        line.addWidget(self._label, 1)
        self._menu = QToolButton(self)
        self._menu.setText("\u22ef")
        self._menu.setAccessibleName("Event menu")
        self._menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if index >= 0:
            self._menu.hide()
        line.addWidget(self._menu)
        if step is not None and step.problem:
            badge = QLabel("!", self)
            badge.setFixedWidth(12)
            badge.setToolTip(step.problem)
            badge.setStyleSheet("color: %s; background: transparent;" % body._chrome.error)
            line.addWidget(badge)
        if step is not None and step.method:
            place = QLabel("not checked", self)
            place.setStyleSheet("color: %s; background: transparent;" % body._chrome.faint)
            place.setToolTip(step.method)
            line.addWidget(place)
        if problem:
            self._label.setStyleSheet("color: %s;" % body._chrome.error)
        self.installEventFilter(body)
        self._full = text
        if step is not None and step.unknown:
            self._label.setStyleSheet("color: %s;" % warning_color(body._chrome))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = self._label.width()
        if width <= 0:
            return
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, width)
        if shown != self._label.text():
            self._label.setText(shown)

    def menu_button(self, event: EventView) -> QToolButton:
        self._event = event
        menu = QMenu(self._menu)
        if event.unreadable or (event.locked and event.banner):
            menu.addAction(
                "Open as text",
                lambda: open_property_as_text(self._body, event.property_name, self._body._sender),
            )
        elif not event.locked:
            menu.addAction("Change event\u2026", lambda: self._body._change_event(event.signal, self))
            menu.addAction("Delete the event", lambda: self._body._delete_event(event.signal))
        self._menu.setMenu(menu)
        return self._menu

    def set_faint(self, text: str) -> None:
        extra = QLabel(text, self)
        extra.setStyleSheet("color: %s;" % self._body._chrome.faint)
        self.layout().insertWidget(1, extra)  # type: ignore[union-attr]

    def set_faint_text(self) -> None:
        self._label.setStyleSheet("color: %s;" % self._body._chrome.faint)

    def set_error(self) -> None:
        self._label.setStyleSheet("color: %s;" % self._body._chrome.error)

    def open_menu(self) -> None:
        if self.step_index < 0:
            self._menu.showMenu()
            return
        menu = QMenu(self)
        if not self.readonly:
            word = "Turn on" if self._off else "Turn off"
            menu.addAction(word, lambda: self._body._run(Gesture("toggle", self.signal_name, self.step_index)))
            menu.addAction("Duplicate", lambda: self._body._run(Gesture("duplicate", self.signal_name, self.step_index)))
            menu.addAction("Move up", lambda: self._body._run(Gesture("move", self.signal_name, self.step_index, -1)))
            menu.addAction("Move down", lambda: self._body._run(Gesture("move", self.signal_name, self.step_index, 1)))
            menu.addAction("Delete", lambda: self._body._run(Gesture("delete", self.signal_name, self.step_index)))
            menu.addAction("Change\u2026", lambda: self._body._activate(self))
        if self.method_name:
            menu.addAction("Go to code", lambda: self._body._go_code(self.method_name))
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        if self.step_index >= 0:
            self._menu.show()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        if self.step_index >= 0 and not self.hasFocus():
            self._menu.hide()

    def focusInEvent(self, event: QEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        if self.step_index >= 0:
            self._menu.show()

    def contextMenuEvent(self, event: QEvent) -> None:  # noqa: N802
        self.open_menu()
        event.accept()  # type: ignore[attr-defined]


def open_property_as_text(widget: QWidget, prop: str, sender: str = "") -> None:
    """Show the .ui text with the caret on this widget's own ``name="<property>"``."""
    surface = _surface(widget)
    if surface is None or not prop:
        return
    source = surface.content_source()
    if source.mode == "visual":
        surface.toggle_source_view()
    editor = surface.source_editor()
    if editor is None:
        return
    text = editor.toPlainText()
    start = 0
    if sender:
        at_widget = text.find('name="%s"' % sender)
        if at_widget >= 0:
            start = at_widget
    end = text.find("<widget ", start + 1)
    if end < 0:
        end = len(text)
    at = text.find('name="%s"' % prop, start, end)
    if at < 0:
        return
    cursor = editor.textCursor()
    cursor.setPosition(at)
    editor.setTextCursor(cursor)
    editor.setFocus()


def _claimed(event: QKeyEvent) -> bool:
    key = enum_value(event.key())
    mods = enum_value(event.modifiers())
    if key in (_UP, _DOWN, _DELETE, _SPACE, _ESC, _F12, _MENU):
        return True
    if key in _ENTER:
        return True
    if key == _D and mods & enum_value(Qt.KeyboardModifier.ControlModifier):
        return True
    if key == _PERIOD and mods & enum_value(Qt.KeyboardModifier.ControlModifier):
        return True
    if key == _F10 and mods & enum_value(Qt.KeyboardModifier.ShiftModifier):
        return True
    return False


def _qt_names(widget: QWidget) -> bool:
    current: Optional[QWidget] = widget
    while current is not None:
        props = getattr(current, "properties", None)
        visible = getattr(props, "qt_names_visible", None)
        if callable(visible):
            return bool(visible())
        current = current.parentWidget()
    return False


def _narrate(widget: QWidget, sentence: str) -> None:
    if not sentence:
        return
    surface = _surface(widget)
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)


def _surface(widget: QWidget) -> object:
    current: Optional[QWidget] = widget
    while current is not None:
        if callable(getattr(current, "toggle_source_view", None)) and callable(getattr(current, "source_editor", None)):
            return current
        current = current.parentWidget()
    return None


def _create(host: SectionHost) -> QWidget:
    return EventsBody(host)


def register(registry: object) -> None:
    registry.add(BehaviorSection("events", 30, _create))  # type: ignore[attr-defined]
