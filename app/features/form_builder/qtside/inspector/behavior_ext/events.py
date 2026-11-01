"""The Events section (UX-BEH-003). The sender line and the newer-logic notice live here."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, List, Optional, Tuple

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
from app.qt.qt_compat import delete_now, enum_value

from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector._services import Dropped, Rejected
from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection, SectionHost, SectionInputs
from app.features.form_builder.qtside.inspector.behavior_ext._rows import (
    TWO_PLACES,
    EventView,
    Gesture,
    Outcome,
    SenderView,
    StepView,
    finish,
    project_sender,
    unused_method_sentence,
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
        self._built: Dict[str, Tuple[SenderView, List["_Group"]]] = {}
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
        # Inline row colors were captured from the previous chrome. Drop the
        # kept groups so the next paint builds them again.
        for _name, (_shown, groups) in list(self._built.items()):
            _release_groups(self._events, groups)
        self._built = {}
        self._view = None
        chrome = self._chrome
        self.setStyleSheet(
            "QWidget#formBuilder\\.events, QWidget#formBuilder\\.events QWidget { background: %s; color: %s; }"
            "QLabel, QWidget#formBuilder\\.events QLabel { color: %s; background: transparent; }"
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
        self._picker = None
        if picker is None:
            return False
        release = getattr(picker, "release", None)
        if callable(release):
            release()
        else:
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
        shown = _with_by_name(self, shown)
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
        self.setUpdatesEnabled(False)
        self._one_read = _window_read(_surface(self)) if shown.kind == "one" else None
        self._one_read_ready = shown.kind == "one"
        try:
            cached = self._built.get(shown.object_name) if shown.kind == "one" else None
            if cached is not None and cached[0] == shown:
                self._show_built(shown.object_name)
                if editing and not shown.events:
                    self._chain.append(self._when)
            else:
                self._fill_groups(shown, editing)
        finally:
            self._one_read_ready = False
            self.setUpdatesEnabled(True)
        self._place_focus()

    def _fill_groups(self, shown: SenderView, editing: bool) -> None:
        previous = self._built.pop(shown.object_name, None) if shown.kind == "one" else None
        if previous is not None:
            _release_groups(self._events, previous[1])
        if shown.kind != "one":
            self._show_built("")
            return
        self._show_built("")
        groups: List[_Group] = []
        first = True
        self._chain = []
        for event in shown.events:
            group = _Group(self, event, editing)
            groups.append(group)
            self._events.addWidget(group)
            if first and (event.steps or event.unreadable or event.banner):
                group.mark_first()
                first = False
            self._chain.extend(group.chain())
        if editing and not shown.events:
            self._chain.append(self._when)
        if shown.object_name:
            self._built[shown.object_name] = (shown, groups)
            while len(self._built) > 4:
                oldest = next(iter(self._built))
                if oldest == shown.object_name:
                    break
                _release_groups(self._events, self._built.pop(oldest)[1])

    def _show_built(self, name: str) -> None:
        self._chain = []
        for sender, (_shown, groups) in self._built.items():
            visible = sender == name
            for group in groups:
                group.setVisible(visible)
                header = group.header
                if visible and getattr(group, "_marked_first", False):
                    header.setObjectName("formBuilder.events.first")
                    self._chain.extend(group.chain())
                elif visible:
                    header.setObjectName("")
                    self._chain.extend(group.chain())
                else:
                    header.setObjectName("")

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
        if getattr(row, "_by_name", False):
            return self._by_name_key(row, event)
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
        previous = self._picker
        self._picker = open_event_picker(host, source, "")
        if previous is not None and previous is not self._picker:
            release = getattr(previous, "release", None)
            if callable(release):
                try:
                    release()
                except RuntimeError:
                    pass

    def _run(self, gesture: Gesture) -> None:
        doc = self._services.session.document
        outcome = finish(doc, QtClassTable.shared(), self._sender, gesture)
        if outcome is None:
            return
        if outcome.command is None:
            _narrate(self, outcome.status)
            return
        if _rule_instead(self, outcome):
            return
        self.note_added(outcome.focus_signal, outcome.focus_index)
        result = self._services.execute(outcome.command)
        if isinstance(result, Rejected):
            _narrate(self, result.message)
            return
        if isinstance(result, Dropped):
            return
        if outcome.status == "METHOD_UNUSED":
            _narrate(self, unused_method_sentence(outcome.unused_method, _window_file(self)))
        if outcome.status:
            _narrate(self, outcome.status)

    def _only_if(self, row: "_Row") -> None:
        from app.qt.QtWidgets import QDialog, QLineEdit, QVBoxLayout
        from app.qt.qt_compat import exec_qt

        dialog = QDialog(self)
        dialog.setWindowTitle("Only if")
        dialog.setObjectName("formBuilder.onlyIfDialog")
        edit = QLineEdit(dialog)
        edit.setObjectName("formBuilder.onlyIf")
        edit.setAccessibleName("Only if")
        edit.setText(getattr(row, "_only_if_text", "").replace("only if ", "", 1))
        column = QVBoxLayout(dialog)
        column.addWidget(edit)
        edit.returnPressed.connect(dialog.accept)
        edit.setFocus()
        if exec_qt(dialog) != enum_value(QDialog.DialogCode.Accepted):
            return
        self._run(Gesture("set_when", row.signal_name, row.step_index, condition=edit.text()))

    def _fix(self, row: "_Row") -> None:
        event = getattr(row, "_event", None)
        if event is not None and getattr(event, "stored_twice", False) and row.step_index < 0:
            self._merge(row.signal_name)
            return
        if row.unreadable or (event is not None and event.banner):
            open_property_as_text(self, row.property_name, self._sender)
            return
        _apply_listed_fix(self, row)

    def _by_name_key(self, row: "_Row", event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        mods = enum_value(event.modifiers())
        shift = bool(mods & enum_value(Qt.KeyboardModifier.ShiftModifier))
        if key == _UP:
            self._move(-1)
            return True
        if key == _DOWN:
            self._move(1)
            return True
        if key in _ENTER or key == _F12:
            self._go_code(row.method_name)
            return True
        if key == _MENU or (key == _F10 and shift):
            row.open_menu()
            return True
        if key == _ESC:
            self._to_canvas()
            return True
        return True

    def _go_code(self, method: str) -> None:
        service = method_actions()
        go = getattr(service, "go_to", None)
        surface = _surface(self)
        if not callable(go) or surface is None or not method:
            return
        if go(surface, method):
            return
        file_name = _window_file(self) or "the window file"
        _narrate(self, "%s() isn't in %s yet. Press Ctrl+. to create it." % (method, file_name))

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


def _release_groups(layout: QVBoxLayout, groups: List["_Group"]) -> None:
    wanted = {id(group) for group in groups}
    index = layout.count() - 1
    while index >= 0:
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if widget is not None and id(widget) in wanted:
            layout.takeAt(index)
            widget.hide()
            widget.setParent(None)
            delete_now(widget)
        index -= 1


class _ThenButton(QPushButton):
    def __init__(self, body: EventsBody, signal: str, parent: QWidget) -> None:
        super().__init__("+ Then\u2026", parent)
        self._signal = signal
        self.clicked.connect(lambda: body._add_step(signal, self))
        self.installEventFilter(body)


class _Group(QWidget):
    def __init__(self, body: EventsBody, event: EventView, editing: bool) -> None:
        super().__init__(body)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
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
            stack = QVBoxLayout(note)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(2)
            label = QLabel(TWO_PLACES, note)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            label.setStyleSheet("color: %s;" % warning_color(body._chrome))
            stack.addWidget(label)
            merge = QPushButton("Merge", note)
            merge.setAccessibleName("Merge")
            merge.clicked.connect(lambda: body._merge(event.signal))
            merge.setEnabled(self._editable)
            stack.addWidget(merge, 0, Qt.AlignmentFlag.AlignLeft)
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
        for name in _by_name(body, event.signal):
            words = "%s() runs by its name" % name
            view = StepView(-2, words, words, False, False, False, True, "", name)
            row = _Row(body, event.signal, -2, words, words, True, False, False, "", view)
            row._by_name = True
            column.addWidget(row)
            self._steps.append(row)
        self.then = _ThenButton(body, event.signal, self)
        self.then.setVisible(False)
        self.then.setEnabled(self._editable)
        column.addWidget(self.then)

    def mark_first(self) -> None:
        self._marked_first = True
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


_STEP_MENU_RESERVE = 0


def _step_menu_reserve(parent: QWidget) -> int:
    """Width of the "…" button, measured once.

    Step rows reserve this width with a spacer. The button itself is built on
    the first hover or focus, so painting a long behavior list does not
    construct one tool button per step.
    """
    global _STEP_MENU_RESERVE
    if _STEP_MENU_RESERVE:
        return _STEP_MENU_RESERVE
    probe = QToolButton(parent)
    probe.setText("\u22ef")
    _STEP_MENU_RESERVE = max(probe.sizeHint().width(), 16)
    probe.setParent(None)
    return _STEP_MENU_RESERVE


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
        self._fitted = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        head, _sep, condition = text.partition("\n")
        if condition:
            self.setFixedHeight(40)
        line = QHBoxLayout(self)
        line.setContentsMargins(2, 0, 2, 0)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        self._label = QLabel(head, self)
        self._label.setWordWrap(True)
        self._label.setMinimumWidth(0)
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._label.setToolTip(text)
        self._label.setAccessibleName(accessible)
        text_col.addWidget(self._label)
        if condition:
            only = QLabel(condition, self)
            only.setObjectName("formBuilder.events.onlyIf")
            only.setWordWrap(True)
            only.setMinimumWidth(0)
            only.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            only.setStyleSheet("color: %s; background: transparent;" % body._chrome.faint)
            text_col.addWidget(only)
        line.addLayout(text_col, 1)
        # Step rows build the menu button on hover or focus. Header rows show it
        # immediately. A by-name row puts it last, after the place link.
        self._menu: Optional[QToolButton] = None
        if index == -1:
            line.addWidget(self._make_menu())
        if step is not None and step.problem:
            badge = QLabel("!", self)
            badge.setObjectName("formBuilder.events.badge")
            badge.setFixedWidth(12)
            badge.setToolTip(step.problem)
            badge.setStyleSheet("color: %s; background: transparent;" % body._chrome.error)
            line.addWidget(badge)
        if step is not None and step.method:
            line.addWidget(_place_link(self, body, step.method))
        if index < -1:
            line.addWidget(self._make_menu())
        elif index >= 0:
            # The "…" appears on hover or focus. Its width stays reserved, so the
            # place link does not grow into that slot and then draw under the button.
            self._menu_reserve = _step_menu_reserve(self)
            self._pointer = False
            line.addSpacing(self._menu_reserve)
        if problem:
            self._label.setStyleSheet("color: %s;" % body._chrome.error)
        self.installEventFilter(body)
        self._full = head
        self._only_if_text = condition
        if step is not None and step.unknown:
            self._label.setStyleSheet("color: %s;" % warning_color(body._chrome))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_texts()

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._fitted and self.width() > 0:
            return
        self._fit_texts()
        self._fitted = True

    def _fit_texts(self) -> None:
        """Elide the call first, down to about eight characters, then the place.

        The place keeps a trailing ``:NN``. Neither widget is given a maximum
        width smaller than the text it shows, so glyphs are never clipped.
        """
        if self.width() <= 0:
            return
        call_metrics = self._label.fontMetrics()
        place = self.findChild(QPushButton, "formBuilder.events.place")
        place_metrics = place.fontMetrics() if place is not None else call_metrics
        if self.step_index >= 0:
            menu_w = int(getattr(self, "_menu_reserve", 0) or 0) + 4
        elif self._menu is not None and not self._menu.isHidden():
            menu_w = self._menu.sizeHint().width() + 4
        else:
            menu_w = 0
        badge = 16 if self.findChild(QLabel, "formBuilder.events.badge") is not None else 0
        available = max(0, self.width() - menu_w - badge - 8)
        place_full = str(place.property("cbcsFull") or "") if place is not None else ""
        pad = 8
        place_natural = _text_width(place_metrics, place_full) + pad if place_full else 0
        call_full = self._full
        call_natural = _text_width(call_metrics, call_full) + 4
        place_floor_sample = "\u2026:NN"
        place_floor = _text_width(place_metrics, place_floor_sample) + pad if place_full else 0
        if call_natural + place_natural <= available:
            call_shown = call_full
            place_shown = place_full
            place_budget = place_natural
        elif call_natural + place_floor <= available:
            call_shown = call_full
            place_budget = max(place_floor, available - call_natural)
            place_shown = _elide_place(place_full, place_metrics, max(8, place_budget - pad)) if place_full else ""
        else:
            place_budget = place_floor if place_full else 0
            place_shown = _elide_place(place_full, place_metrics, max(8, place_budget - pad)) if place_full else ""
            call_room = max(8, available - place_budget)
            call_shown = _elide_call(call_full, call_metrics, call_room)
        if self._label.text() != call_shown:
            self._label.setText(call_shown)
        if place is None:
            return
        # The button centers its text, so the width must cover every glyph.
        # A shortfall clips the middle. Elide again until the ink fits.
        place_shown = _fit_place(place_full, place_shown, place_metrics, place_budget, pad)
        if place.text() != place_shown:
            place.setText(place_shown)
        ink = _text_width(place_metrics, place_shown) + pad
        place.setMaximumWidth(16777215)
        place.setFixedWidth(max(8, min(place_budget, ink)))
        reason = str(place.property("cbcsReason") or "")
        if reason:
            tip = (place_full + "\n" + reason) if place_shown != place_full and place_full else reason
            if place.toolTip() != tip:
                place.setToolTip(tip)

    def _make_menu(self) -> QToolButton:
        button = QToolButton(self)
        button.setText("\u22ef")
        button.setAccessibleName("Event menu")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._menu = button
        return button

    def menu_button(self, event: EventView) -> QToolButton:
        self._event = event
        button = self._menu or self._make_menu()
        button.pressed.connect(self._ensure_header_menu)
        return button

    def _ensure_header_menu(self) -> None:
        button = self._menu
        event = self._event
        if button is None or event is None or button.menu() is not None:
            return
        menu = QMenu(button)
        if event.unreadable or (event.locked and event.banner):
            menu.addAction(
                "Open as text",
                lambda: open_property_as_text(self._body, event.property_name, self._body._sender),
            )
        elif not event.locked:
            menu.addAction("Change event\u2026", lambda: self._body._change_event(event.signal, self))
            menu.addAction("Delete the event", lambda: self._body._delete_event(event.signal))
        button.setMenu(menu)
        button.showMenu()

    def _show_step_menu(self, shown: bool) -> None:
        if self.step_index < 0:
            return
        button = self._menu
        layout = self.layout()
        reserve = int(getattr(self, "_menu_reserve", 0) or 0)
        if shown:
            if button is None:
                button = self._make_menu()
                button.setFixedWidth(reserve or button.sizeHint().width())
            if layout is not None and layout.indexOf(button) < 0:
                if layout.count():
                    layout.takeAt(layout.count() - 1)
                layout.addWidget(button)
            button.show()
            button.setText("\u22ef")
        elif button is not None and layout is not None and layout.indexOf(button) >= 0:
            layout.removeWidget(button)
            button.hide()
            layout.addSpacing(reserve or button.width() or 16)
        self._fit_texts()

    def set_faint(self, text: str) -> None:
        extra = QLabel(text, self)
        extra.setStyleSheet("color: %s;" % self._body._chrome.faint)
        self.layout().insertWidget(1, extra)  # type: ignore[union-attr]

    def set_faint_text(self) -> None:
        self._label.setStyleSheet("color: %s;" % self._body._chrome.faint)

    def set_error(self) -> None:
        self._label.setStyleSheet("color: %s;" % self._body._chrome.error)

    def open_menu(self) -> None:
        if self.step_index < 0 and not getattr(self, "_by_name", False):
            self._ensure_header_menu()
            return
        menu = QMenu(self)
        if not self.readonly and self.step_index >= 0:
            menu.addAction("Only if\u2026", lambda: self._body._only_if(self))
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
            menu.addAction("Rename", lambda name=self.method_name: _arm_rename(self, name))
        if "runs by its name" in self._full:
            menu.addAction("Why does it run?", lambda: _narrate(self, _by_name_why()))
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        super().enterEvent(event)
        self._pointer = True
        self._show_step_menu(True)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._pointer = False
        self._show_step_menu(self.hasFocus())

    def focusInEvent(self, event: QEvent) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._show_step_menu(True)

    def focusOutEvent(self, event: QEvent) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._show_step_menu(bool(getattr(self, "_pointer", False)))

    def contextMenuEvent(self, event: QEvent) -> None:  # noqa: N802
        self.open_menu()
        event.accept()  # type: ignore[attr-defined]


def _place_link(row: QWidget, body: "EventsBody", method: str) -> QPushButton:
    text, tone, reason = _place_state(body, method)
    button = QPushButton(text, row)
    button.setFlat(True)
    button.setObjectName("formBuilder.events.place")
    button.setProperty("cbcsFull", text)
    checked = text == "not checked"
    button.setProperty("cbcsReason", reason if checked else "")
    button.setToolTip(reason if checked else text)
    button.setAccessibleName(text)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    if tone == "warn":
        color = warning_color(body._chrome)
    elif tone == "ok":
        color = body._chrome.muted
    else:
        color = body._chrome.faint
    button.setStyleSheet(
        "QPushButton { color: %s; background: transparent; border: none; padding: 0px; margin: 0px; }"
        "QPushButton:focus { border: %dpx solid %s; }"
        % (color, body._chrome.focus_width, body._chrome.accent)
    )
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    button.clicked.connect(lambda: body._go_code(method))
    return button


def _place_state(body: "EventsBody", method: str) -> Tuple[str, str, str]:
    file_name = _window_file(body) or "the window file"
    surface = _surface(body)
    read = _window_read(surface, body)
    if surface is None or read is None:
        return "not checked", "faint", "The window file could not be read."
    if read.status != "ok":
        return "not checked", "faint", read.reason or "The window file could not be read."
    found = read.facts.method(method)
    if found is None:
        return "not in %s" % file_name, "warn", method
    return "%s:%d" % (file_name, found.line), "ok", method


def _window_read(surface: object, body: Optional["EventsBody"] = None) -> Any:
    """The handler service's window read, without qtside importing integration.

    One render reads the window file once and hands that result to every section.
    """
    if body is not None and getattr(body, "_one_read_ready", False):
        return getattr(body, "_one_read", None)
    from app.features.form_builder.qtside.pickers import method_actions

    if surface is None:
        return None
    read = getattr(method_actions(), "reading", None)
    if not callable(read):
        return None
    return read(surface)


def _apply_listed_fix(body: "EventsBody", row: "_Row") -> bool:
    """Ctrl+. on a call step runs that step's Use fix (FB201)."""
    surface = _surface(body)
    run = getattr(surface, "run_problem_fix", None)
    if surface is None or not callable(run) or not row.method_name:
        return False
    for item in surface.session.diagnostics.all():
        if item.code != "FB201":
            continue
        missing = ""
        offered = False
        for fix in item.fixes:
            if fix.fix_id == "use-method":
                offered = True
            elif fix.fix_id == "create-method":
                for name, value in fix.args:
                    if name == "method":
                        missing = value
        if offered and missing == row.method_name:
            return bool(run("use-method", {"fb_key": item.key}))
    return False


def _with_by_name(body: "EventsBody", shown: SenderView) -> SenderView:
    """A by-name method is its own event group when that event has no steps."""
    body.by_name_count = 0
    if shown.kind != "one" or not shown.object_name:
        return shown
    document = body._services.session.document
    if str(document.ui.field("connectslotsbyname") or "") == "false":
        return shown
    read = _window_read(_surface(body), body)
    if read is None or getattr(read, "status", "") != "ok":
        return shown
    sender = shown.object_name
    prefix = "on_%s_" % sender
    have = {event.signal for event in shown.events}
    signatures = _sender_signatures(body) if body._sender else ()
    extra = []
    for item in read.facts.methods:
        name = item.name
        if not name.startswith(prefix):
            continue
        signal = name[len(prefix):]
        if not signal or signal in have:
            continue
        if not slot_types_match(item.slot_types, signal, signatures):
            continue
        from app.features.form_builder.engine.logic.events_catalog import event_words

        words = event_words(signal)
        extra.append(
            EventView(
                signal,
                "When %s" % words.header,
                "",
                "Event, %s" % words.header,
                (),
                False,
                False,
                "",
                False,
                "",
            )
        )
        have.add(signal)
    body.by_name_count = len(extra)
    if not extra:
        return shown
    return replace(
        shown,
        events=shown.events + tuple(extra),
        empty="",
        caption="",
        event_count=shown.event_count + len(extra),
    )


def _by_name(body: "EventsBody", signal: str) -> Tuple[str, ...]:
    surface = _surface(body)
    if surface is None:
        return ()
    document = body._services.session.document
    if str(document.ui.field("connectslotsbyname") or "") == "false":
        return ()
    read = _window_read(surface, body)
    if read is None or read.status != "ok":
        return ()
    wanted = "on_%s_%s" % (body._sender, signal)
    signatures = _sender_signatures(body)
    return tuple(
        item.name
        for item in read.facts.methods
        if item.name == wanted and slot_types_match(item.slot_types, signal, signatures)
    )


def _sender_signatures(body: "EventsBody") -> Tuple[str, ...]:
    from app.features.form_builder.engine.logic.compat import node_class
    from app.features.form_builder.engine.logic.events import sender_node

    doc = body._services.session.document
    node = sender_node(doc, body._sender)
    if node is None:
        return ()
    class_name, _slots = node_class(doc, QtClassTable.shared(), node)
    return tuple(QtClassTable.shared().signals(class_name))


def slot_types_match(types: Optional[Tuple[str, ...]], signal: str, signatures: Tuple[str, ...]) -> bool:
    from app.features.form_builder.engine.project.handler_checks import slot_types_match as match

    return match(types, signal, signatures)


def _by_name_why() -> str:
    return (
        "Qt runs methods named on_{object}_{event} by themselves, "
        "because Connect methods by name is on."
    )


def _window_file(widget: QWidget) -> str:
    import os

    services = getattr(widget, "_services", None)
    scope = getattr(getattr(services, "session", None), "scope", None)
    path = getattr(scope, "window_path", None) or ""
    return os.path.basename(path) if path else ""


def _text_width(metrics: object, text: str) -> int:
    if not text:
        return 0
    advance = int(metrics.horizontalAdvance(text))  # type: ignore[attr-defined]
    bounds = int(metrics.boundingRect(text).width())  # type: ignore[attr-defined]
    return max(advance, bounds)


def _fit_place(full: str, shown: str, metrics: object, budget: int, pad: int) -> str:
    """Elide until the place ink, plus padding, fits the button.

    A centered button clips both sides when the text is wider than the button.
    ``elidedText`` can still be a pixel over, so characters come off until it fits.
    """
    if not full:
        return ""
    room = max(8, budget - pad)
    fitted = shown or full
    if _text_width(metrics, fitted) <= room:
        return fitted
    fitted = _elide_place(full, metrics, room)
    if fitted and _text_width(metrics, fitted) <= room:
        return fitted
    suffix = ""
    body = full
    if ":" in full:
        head, tail = full.rsplit(":", 1)
        if tail.isdigit():
            suffix = ":" + tail
            body = head
    mark = "\u2026"
    while body and _text_width(metrics, body + mark + suffix) > room:
        body = body[:-1]
    return body + mark + suffix if body else mark + suffix


def _elide_call(text: str, metrics: object, width: int) -> str:
    if "A step Code Studio can't edit (" in text:
        return _elide_row(text, metrics, width)
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(1, width))  # type: ignore[attr-defined]


def _elide_place(text: str, metrics: object, width: int) -> str:
    """Right-elide a place, keeping a trailing ``:NN`` line suffix."""
    suffix = ""
    body = text
    if ":" in text:
        head, tail = text.rsplit(":", 1)
        if tail.isdigit():
            suffix = ":" + tail
            body = head
    elide = metrics.elidedText  # type: ignore[attr-defined]
    if not suffix:
        return elide(text, Qt.TextElideMode.ElideRight, max(1, width))
    room = width - metrics.horizontalAdvance(suffix)  # type: ignore[attr-defined]
    if room < 8:
        room = 8
    return elide(body, Qt.TextElideMode.ElideRight, room) + suffix


def _elide_row(text: str, metrics: object, width: int) -> str:
    """Elide the middle of a row. An unreadable verb keeps its sentence and elides only the verb."""
    marker = "A step Code Studio can't edit ("
    elide = getattr(metrics, "elidedText")
    if marker in text and text.endswith(")"):
        start = text.index(marker) + len(marker)
        head = text[:start]
        verb = text[start:-1]
        tail = ")"
        room = width - metrics.horizontalAdvance(head + tail)  # type: ignore[attr-defined]
        if room < 8:
            room = 8
        return head + elide(verb, Qt.TextElideMode.ElideMiddle, room) + tail
    return elide(text, Qt.TextElideMode.ElideRight, width)


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


def _rule_instead(body: "EventsBody", outcome: Outcome) -> bool:
    """A toggled setEnabled or setVisible can become a rule. True skips the slot."""
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.events import read_event
    from app.features.form_builder.engine.logic.formula import normalize
    from app.features.form_builder.engine.logic.formula_env import env_for
    from app.features.form_builder.engine.logic.intents.m7_rules import steer_for
    from app.features.form_builder.engine.ui4.nodes import WidgetNode
    from app.features.form_builder.qtside.formula.steer_ui import ask_steer, steer_sentence

    command = outcome.command
    if not isinstance(command, SetEventSteps) or command.signal_name != "toggled":
        return False
    doc = body._services.session.document
    old = read_event(doc, command.sender, command.signal_name).steps
    new = command.steps
    added = None
    if len(new) == len(old) + 1 and tuple(new[:-1]) == tuple(old):
        added = new[-1]
    elif len(new) == len(old):
        for left, right in zip(old, new):
            if left != right:
                added = right
                break
    if added is None or getattr(added, "verb", "") != "slot":
        return False
    steer = steer_for(command.signal_name, getattr(added, "slot", "") or "")
    if steer is None:
        return False
    env = env_for(doc, None, QtClassTable.shared())
    target = getattr(added, "target", "") or ""
    choice = ask_steer(
        body,
        steer_sentence(added.slot, _logic_display(env, target), _logic_display(env, command.sender)),
    )
    if choice == "connect":
        return False
    if choice != "rule":
        return True
    ids = doc.by_name(target)
    if not ids:
        return True
    node = doc.node(ids[0])
    if not isinstance(node, WidgetNode):
        return True
    words = "Visible when" if steer.key == "cbcsVisibleWhen" else "Enabled when"
    text = normalize(command.sender)
    if not text:
        return True
    body._services.execute_all(
        "Set %s for %s" % (words, _logic_display(env, target)),
        [SetLogic(node.id, steer.key, text)],
    )
    return True


def _logic_display(env: object, name: str) -> str:
    widgets = getattr(env, "widgets", None)
    facts = widgets.get(name) if widgets is not None else None
    display = getattr(facts, "display", "") if facts is not None else ""
    return display or name


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


def _arm_rename(widget: QWidget, method: str) -> None:
    from app.features.form_builder.qtside.logic_panel.open import arm_method_rename

    arm_method_rename(widget, method)


def register(registry: object) -> None:
    registry.add(BehaviorSection("events", 30, _create))  # type: ignore[attr-defined]
