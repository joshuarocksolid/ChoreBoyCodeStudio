"""The event picker popover. It shows one page at a time and never calls the log."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from app.qt.QtCore import QEvent, QObject, QPoint, Qt, QSize
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.logic.events import declared_methods
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.pickers.flow import (
    Closed,
    Commit,
    Item,
    Page,
    PickContext,
    PickerSource,
    Press,
    opening,
    reduce,
)
from app.features.form_builder.qtside.theme.chrome import FormChrome, popover_style

_WIDTH = 320
_ROW = 28
_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_ESCAPE = enum_value(Qt.Key.Key_Escape)
_UP = enum_value(Qt.Key.Key_Up)
_DOWN = enum_value(Qt.Key.Key_Down)
_LEFT = enum_value(Qt.Key.Key_Left)
_RIGHT = enum_value(Qt.Key.Key_Right)
_BACK = enum_value(Qt.Key.Key_Backspace)
_ROLE = enum_value(Qt.ItemDataRole.UserRole)

_SHOW_EVENTS = False
_SHOW_ACTIONS = False


def remember_base(kind: str, checked: bool) -> None:
    global _SHOW_EVENTS, _SHOW_ACTIONS
    if kind == "event":
        _SHOW_EVENTS = checked
    else:
        _SHOW_ACTIONS = checked


def remembered_base(kind: str) -> bool:
    return _SHOW_EVENTS if kind == "event" else _SHOW_ACTIONS


class EventPicker(QFrame):
    """320 px popup. Esc on the first page closes and writes nothing."""

    def __init__(self, parent: QWidget, chrome: FormChrome, on_commit: Callable[[object], None]) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("formBuilder.eventPicker")
        self.setAccessibleName("Event picker")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._chrome = chrome
        self._on_commit = on_commit
        self._ctx: Optional[PickContext] = None
        self._page: Optional[Page] = None
        self._host: Optional[QWidget] = None
        self._filling = False
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 10)
        column.setSpacing(6)
        self._title = QLabel(self)
        self._title.setObjectName("formBuilder.eventPickerTitle")
        column.addWidget(self._title)
        self.search = QLineEdit(self)
        self.search.setObjectName("formBuilder.eventPickerSearch")
        self.search.setAccessibleName("Find an event")
        self.search.setPlaceholderText("Type to find an event")
        self.search.installEventFilter(self)
        self.search.textChanged.connect(self._typed)
        column.addWidget(self.search)
        self.field = QLineEdit(self)
        self.field.setObjectName("formBuilder.eventPickerMethod")
        self.field.setAccessibleName("Method name")
        self.field.installEventFilter(self)
        self.field.textChanged.connect(self._method_typed)
        self.field.hide()
        column.addWidget(self.field)
        self.notice = QLabel(self)
        self.notice.setObjectName("formBuilder.eventPickerNotice")
        self.notice.setWordWrap(True)
        self.notice.setProperty("note", True)
        column.addWidget(self.notice)
        self.rows = QListWidget(self)
        self.rows.setObjectName("formBuilder.eventPickerList")
        self.rows.setAccessibleName("Choices")
        self.rows.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rows.itemClicked.connect(self._clicked)
        column.addWidget(self.rows)
        self.check = QCheckBox(self)
        self.check.setObjectName("formBuilder.eventPickerBase")
        self.check.toggled.connect(self._toggled)
        column.addWidget(self.check)
        self.setStyleSheet(popover_style(self.objectName(), chrome) + self._extra(chrome))
        self.setFixedWidth(_WIDTH)

    def open_at(self, host: QWidget, ctx: PickContext) -> None:
        self._host = host
        self._ctx = ctx
        self._apply(opening(ctx))
        self.adjustSize()
        origin = host.mapToGlobal(QPoint(0, host.height()))
        self.move(origin)
        self.show()
        focus = self.field if self.field.isVisible() else self.search
        focus.setFocus()
        if focus is self.field:
            self.field.selectAll()
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._focus_left)

    def _focus_left(self, _old: object, new: object) -> None:
        if not self.isVisible():
            return
        if isinstance(new, QWidget) and (new is self or self.isAncestorOf(new)):
            return
        # A click outside the popup is the same as Esc: close, write nothing.
        self.hide()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ShortcutOverride and watched in (self.search, self.field):
            event.accept()
            return True
        if event.type() == QEvent.Type.KeyPress and watched in (self.search, self.field):
            return self._key(event)  # type: ignore[arg-type]
        return super().eventFilter(watched, event)

    def _key(self, event: QKeyEvent) -> bool:
        key = enum_value(event.key())
        if key == _UP:
            return self._press("up")
        if key == _DOWN:
            return self._press("down")
        if key in _ENTER:
            return self._press("enter")
        if key == _RIGHT:
            return self._press("right")
        if key == _LEFT and not self._line().text():
            return self._press("left")
        if key == _BACK and not self._line().text() and watched_empty(self._page):
            return self._press("backspace")
        if key == _ESCAPE:
            return self._press("esc")
        if key == _BACK and self._line() is self.field:
            return False
        return False

    def _line(self) -> QLineEdit:
        return self.field if self.field.isVisible() else self.search

    def _press(self, key: str, text: str = "") -> bool:
        ctx, page = self._ctx, self._page
        if ctx is None or page is None:
            return False
        nxt = reduce(ctx, page, Press(key, text))
        if isinstance(nxt, Closed):
            self._shut()
            return True
        if isinstance(nxt, Commit):
            self.hide()
            self._on_commit(nxt.gesture)
            self._shut()
            return True
        if isinstance(nxt, Page):
            self._apply(nxt)
            return True
        return False

    def _typed(self, text: str) -> None:
        if self._filling or self._page is None or text == self._page.filter:
            return
        self._press("filter", text)

    def _method_typed(self, text: str) -> None:
        if self._filling:
            return
        self._press("field", text)

    def _toggled(self, checked: bool) -> None:
        if self._filling or self._page is None:
            return
        remember_base("event" if self._page.kind == "event" else "actions", checked)
        self._press("check", "1" if checked else "0")

    def _clicked(self, item: QListWidgetItem) -> None:
        page = self._page
        if page is None:
            return
        index = item.data(_ROLE)
        if not isinstance(index, int) or not (0 <= index < len(page.rows)):
            return
        row = page.rows[index]
        if row.header or not row.enabled:
            return
        self._page = replace(page, current=index)
        self._press("enter")

    def _apply(self, page: Page) -> None:
        self._page = page
        self._filling = True
        self._title.setText(page.title)
        method = page.kind == "method"
        self.search.setVisible(not method)
        self.field.setVisible(method)
        if method:
            if self.field.text() != page.field:
                self.field.setText(page.field)
            self.field.setFocus()
        elif self.search.text() != page.filter:
            self.search.setText(page.filter)
        self.notice.setText(page.notice)
        self.notice.setVisible(bool(page.notice))
        self.check.setVisible(bool(page.check))
        self.check.setText(page.check)
        if self.check.isChecked() != page.checked:
            self.check.setChecked(page.checked)
        self._fill(page)
        self._filling = False
        self.adjustSize()

    def _fill(self, page: Page) -> None:
        chrome = self._chrome
        self.rows.clear()
        for index, item in enumerate(page.rows):
            row = QListWidgetItem()
            row.setData(_ROLE, index)
            if item.header or not item.enabled:
                row.setFlags(row.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable)
            self.rows.addItem(row)
            label = QLabel(self._html(item, chrome), self.rows)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            label.setStyleSheet("background: transparent; border: none; padding: 2px 6px;")
            height = _ROW + (16 if item.note else 0)
            row.setSizeHint(QSize(280, height))
            self.rows.setItemWidget(row, label)
        if page.rows:
            self.rows.setCurrentRow(page.current)
        shown = min(max(len(page.rows), 1), 8)
        self.rows.setFixedHeight(shown * _ROW + 8)

    def _html(self, item: Item, chrome: FormChrome) -> str:
        from html import escape

        if item.header:
            return "<span style=\"color:%s\">%s</span>" % (chrome.muted, escape(item.text))
        color = chrome.text if item.enabled else chrome.muted
        body = "<span style=\"color:%s\">%s</span>" % (color, escape(item.text))
        if item.faint:
            body += " <span style=\"color:%s\">%s</span>" % (chrome.faint, escape(item.faint))
        if item.note:
            body += "<br><span style=\"color:%s\">%s</span>" % (chrome.faint, escape(item.note))
        return body

    def _shut(self) -> None:
        host = self._host
        self.hide()
        if host is not None:
            host.setFocus()

    def _extra(self, chrome: FormChrome) -> str:
        frame = "QFrame#formBuilder\\.eventPicker"
        return (
            "%(f)s QLineEdit { color: %(text)s; background: %(input)s; border: 1px solid %(border)s;"
            " border-radius: 4px; padding: 4px 8px; }"
            "%(f)s QLineEdit:focus { border: %(focus)dpx solid %(accent)s; }"
            "%(f)s QListWidget { color: %(text)s; background: %(panel)s; border: none; outline: none; }"
            "%(f)s QListWidget::item:selected { background: %(hover)s; border: %(focus)dpx solid %(accent)s; }"
            "%(f)s QCheckBox { color: %(text)s; }"
        ) % {
            "f": frame,
            "text": chrome.text,
            "input": chrome.input,
            "border": chrome.border,
            "panel": chrome.panel,
            "hover": chrome.row_hover,
            "accent": chrome.accent,
            "focus": chrome.focus_width,
        }


def watched_empty(page: Optional[Page]) -> bool:
    return page is not None and not page.filter


def build_context(doc: object, source: PickerSource, target: str, methods: tuple, window_file: str, window_class: str) -> PickContext:
    from app.features.form_builder.engine.ui4.document import UiDocument

    assert isinstance(doc, UiDocument)
    kind = "event" if not source.signal and not source.changing else "actions"
    if source.changing or not source.signal:
        kind = "event"
    taken = tuple(dict.fromkeys(tuple(methods) + tuple(declared_methods(doc))))
    return PickContext(
        doc,
        QtClassTable.shared(),
        source,
        target,
        tuple(methods),
        window_file,
        window_class,
        remembered_base(kind),
        taken,
        (),
    )
