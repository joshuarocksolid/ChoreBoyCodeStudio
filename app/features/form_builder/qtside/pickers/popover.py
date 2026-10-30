"""The event picker popover. It shows one page at a time and never calls the log."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from app.qt.QtCore import QAbstractListModel, QEvent, QObject, QPoint, QRect, QSize, Qt
from app.qt.QtGui import QColor, QKeyEvent
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QLabel,
    QLineEdit,
    QListView,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.logic.events import declared_methods
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.pickers.flow import (
    Closed,
    Commit,
    Page,
    PickContext,
    PickerSource,
    Press,
    opening,
    reduce,
)
from app.features.form_builder.qtside.theme.chrome import FormChrome, popover_style

_WIDTH = 320
_ROW = 24
_FAINT = int(enum_value(Qt.ItemDataRole.UserRole)) + 1
_NOTE = int(enum_value(Qt.ItemDataRole.UserRole)) + 2
_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_ESCAPE = enum_value(Qt.Key.Key_Escape)
_UP = enum_value(Qt.Key.Key_Up)
_DOWN = enum_value(Qt.Key.Key_Down)
_LEFT = enum_value(Qt.Key.Key_Left)
_RIGHT = enum_value(Qt.Key.Key_Right)
_BACK = enum_value(Qt.Key.Key_Backspace)
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
        self._listening = False
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
        self._model = _RowModel(self)
        self.rows = QListView(self)
        self.rows.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.rows.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.rows.setUniformItemSizes(True)
        self.rows.setItemDelegate(_RowDelegate(chrome, self.rows))
        self.rows.setObjectName("formBuilder.eventPickerList")
        self.rows.setAccessibleName("Choices")
        self.rows.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rows.setModel(self._model)
        self.rows.clicked.connect(self._clicked)
        column.addWidget(self.rows)
        self.check = QCheckBox(self)
        self.check.setObjectName("formBuilder.eventPickerBase")
        self.check.installEventFilter(self)
        self.check.toggled.connect(self._toggled)
        column.addWidget(self.check)
        self.setStyleSheet(popover_style(self.objectName(), chrome) + self._extra(chrome))
        self.setFixedWidth(_WIDTH)

    def open_at(self, host: QWidget, ctx: PickContext, at: Optional[QPoint] = None) -> None:
        self._host = host
        self._ctx = ctx
        self._apply(opening(ctx))
        self.adjustSize()
        self._place(host, at)
        self.show()
        focus = self.field if self.field.isVisible() else self.search
        focus.setFocus()
        if focus is self.field:
            self.field.selectAll()
        self._listen()

    def _place(self, host: QWidget, at: Optional[QPoint]) -> None:
        screen = host.screen()
        area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1600, 900)
        if at is None:
            anchor = host.mapToGlobal(QPoint(0, host.height()))
            above = host.mapToGlobal(QPoint(0, 0)).y() - self.height()
            host_right = host.mapToGlobal(QPoint(host.width(), 0)).x()
        else:
            anchor = at
            above = anchor.y() - self.height()
            host_right = anchor.x() + host.width()
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        x = anchor.x()
        if x + width > area.right():
            x = host_right - width
        x = max(area.left(), min(x, area.right() - width + 1))
        y = anchor.y()
        if y + height > area.bottom() and above >= area.top():
            y = above
        y = max(area.top(), min(y, area.bottom() - height + 1))
        self.move(int(x), int(y))

    def _listen(self) -> None:
        if self._listening:
            return
        app = QApplication.instance()
        if app is None:
            return
        app.focusChanged.connect(self._focus_left)  # type: ignore[attr-defined]
        self._listening = True

    def _unlisten(self) -> None:
        if not self._listening:
            return
        app = QApplication.instance()
        if app is not None:
            try:
                app.focusChanged.disconnect(self._focus_left)  # type: ignore[attr-defined]
            except (RuntimeError, TypeError):
                pass
        self._listening = False

    def _focus_left(self, _old: object, new: object) -> None:
        if not self.isVisible():
            return
        if isinstance(new, QWidget) and (new is self or self.isAncestorOf(new)):
            return
        # A click outside already moved focus. Close without pulling it back.
        self._unlisten()
        self.hide()
        self.deleteLater()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        check = getattr(self, "check", None)
        watched_line = watched in (self.search, self.field) or watched is check
        if event.type() == QEvent.Type.ShortcutOverride and watched_line:
            event.accept()
            return True
        if event.type() == QEvent.Type.KeyPress and watched_line:
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
        if self._page.check.startswith("Show "):
            remember_base("event" if self._page.kind == "event" else "actions", checked)
        self._press("check", "1" if checked else "0")

    def _clicked(self, index: object) -> None:
        page = self._page
        if page is None or not index.isValid():  # type: ignore[attr-defined]
            return
        row_index = index.row()  # type: ignore[attr-defined]
        if not (0 <= row_index < len(page.rows)):
            return
        row = page.rows[row_index]
        if row.header or not row.enabled:
            return
        self._page = replace(page, current=row_index)
        self._press("enter")

    def _apply(self, page: Page) -> None:
        self._page = page
        self._filling = True
        self._title.setText(page.title)
        method = page.kind == "method"
        self.search.setVisible(not method)
        self.field.setVisible(method)
        if page.kind == "event":
            self.search.setPlaceholderText("Type to find an event")
        else:
            self.search.setPlaceholderText("")
        self.search.setAccessibleName(page.title or "Choices")
        self.rows.setAccessibleName(page.title or "Choices")
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
        if not self.isVisible():
            self.adjustSize()

    def _fill(self, page: Page) -> None:
        # Every match is in the model. The view paints only the rows in view.
        rows = []
        flags = []
        enabled = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        notes = False
        for item in page.rows:
            rows.append((item.text, item.faint, item.note, item.header, item.enabled))
            flags.append(Qt.ItemFlag.NoItemFlags if item.header or not item.enabled else enabled)
            notes = notes or bool(item.note)
        self.rows.setUniformItemSizes(not notes)
        self._model.set_rows(rows, flags)
        if page.rows:
            current = self._model.index(min(page.current, len(page.rows) - 1), 0)
            self.rows.setCurrentIndex(current)
            self.rows.scrollTo(current)
        shown = min(max(len(page.rows), 1), 8)
        height = shown * (_ROW + (16 if notes else 0)) + 8
        if self.rows.height() != height:
            self.rows.setFixedHeight(height)

    def _shut(self) -> None:
        self._unlisten()
        host = self._host
        self.hide()
        self.deleteLater()
        if host is not None:
            host.setFocus()

    def _extra(self, chrome: FormChrome) -> str:
        frame = "QFrame#formBuilder\\.eventPicker"
        return (
            "%(f)s QLineEdit { color: %(text)s; background: %(input)s; border: 1px solid %(border)s;"
            " border-radius: 4px; padding: 4px 8px; }"
            "%(f)s QLineEdit:focus { border: %(focus)dpx solid %(accent)s; }"
            "%(f)s QListView { color: %(text)s; background: %(panel)s; border: none; outline: none; }"
            "%(f)s QListView::item { color: %(text)s; }"
            "%(f)s QListView::item:selected { color: %(text)s; background: %(hover)s; border: %(focus)dpx solid %(accent)s; }"
            "%(f)s QListView::item:disabled { color: %(muted)s; }"
            "%(f)s QCheckBox { color: %(text)s; }"
        ) % {
            "f": frame,
            "text": chrome.text,
            "muted": chrome.muted,
            "input": chrome.input,
            "border": chrome.border,
            "panel": chrome.panel,
            "hover": chrome.row_hover,
            "accent": chrome.accent,
            "focus": chrome.focus_width,
        }


class _RowModel(QAbstractListModel):
    """One painted list. Rows are strings, not a widget each."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._rows: list = []
        self._flags: list = []
        chrome = parent._chrome  # type: ignore[attr-defined]
        self._text = QColor(chrome.text)
        self._muted = QColor(chrome.muted)
        self._faint = QColor(chrome.faint)

    def rowCount(self, parent: object = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():  # type: ignore[attr-defined]
            return 0
        return len(self._rows)

    def data(self, index: object, role: int = 0) -> object:
        if not index.isValid():  # type: ignore[attr-defined]
            return None
        text, faint, note, header, enabled = self._rows[index.row()]  # type: ignore[attr-defined]
        kind = enum_value(role) if not isinstance(role, int) else role
        if kind == enum_value(Qt.ItemDataRole.DisplayRole):
            return text
        if kind == enum_value(Qt.ItemDataRole.ForegroundRole):
            if header or not enabled:
                return self._muted
            if faint and not text:
                return self._faint
            return self._text
        if kind == _FAINT:
            return faint
        if kind == _NOTE:
            return note
        if kind == enum_value(Qt.ItemDataRole.SizeHintRole):
            return QSize(0, _ROW + (16 if note else 0))
        return None

    def flags(self, index: object) -> object:
        if not index.isValid():  # type: ignore[attr-defined]
            return Qt.ItemFlag.NoItemFlags
        return self._flags[index.row()]  # type: ignore[attr-defined]

    def set_rows(self, rows: list, flags: list) -> None:
        if rows == self._rows and flags == self._flags:
            return
        self.beginResetModel()
        self._rows = rows
        self._flags = flags
        self.endResetModel()


class _RowDelegate(QStyledItemDelegate):
    """Words on the first line, the signature in faint, the reason on the next line."""

    def __init__(self, chrome: FormChrome, parent: QWidget) -> None:
        super().__init__(parent)
        self._faint = QColor(chrome.faint)
        self._muted = QColor(chrome.muted)

    def paint(self, painter: object, option: object, index: object) -> None:  # noqa: N802
        style = option.widget.style()  # type: ignore[attr-defined]
        drawn = QStyleOptionViewItem(option)  # type: ignore[arg-type]
        self.initStyleOption(drawn, index)  # type: ignore[arg-type]
        drawn.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, drawn, painter, option.widget)  # type: ignore[attr-defined]
        text = index.data(enum_value(Qt.ItemDataRole.DisplayRole)) or ""  # type: ignore[attr-defined]
        faint = index.data(_FAINT) or ""  # type: ignore[attr-defined]
        note = index.data(_NOTE) or ""  # type: ignore[attr-defined]
        color = index.data(enum_value(Qt.ItemDataRole.ForegroundRole))  # type: ignore[attr-defined]
        painter.save()  # type: ignore[attr-defined]
        painter.setPen(color if isinstance(color, QColor) else self._muted)  # type: ignore[attr-defined]
        rect = option.rect.adjusted(8, 0, -8, 0)  # type: ignore[attr-defined]
        metrics = painter.fontMetrics()  # type: ignore[attr-defined]
        line = QRect(rect)
        if note:
            line.setHeight(_ROW)
        main = str(text)
        if faint:
            gap = metrics.horizontalAdvance("  " + str(faint))
            room = max(8, line.width() - gap)
            main = metrics.elidedText(main, Qt.TextElideMode.ElideMiddle, room)
        else:
            main = metrics.elidedText(main, Qt.TextElideMode.ElideMiddle, line.width())
        painter.drawText(line, enum_value(Qt.AlignmentFlag.AlignVCenter) | enum_value(Qt.AlignmentFlag.AlignLeft), main)  # type: ignore[attr-defined]
        if faint:
            used = metrics.horizontalAdvance(main + "  ")
            faint_rect = QRect(line)
            faint_rect.setLeft(line.left() + used)
            painter.setPen(self._faint)  # type: ignore[attr-defined]
            painter.drawText(  # type: ignore[attr-defined]
                faint_rect,
                enum_value(Qt.AlignmentFlag.AlignVCenter) | enum_value(Qt.AlignmentFlag.AlignLeft),
                metrics.elidedText(str(faint), Qt.TextElideMode.ElideRight, max(8, faint_rect.width())),
            )
        if note:
            note_rect = QRect(rect)
            note_rect.setTop(rect.top() + _ROW - 2)
            painter.setPen(self._muted)  # type: ignore[attr-defined]
            painter.drawText(  # type: ignore[attr-defined]
                note_rect,
                enum_value(Qt.AlignmentFlag.AlignLeft) | enum_value(Qt.AlignmentFlag.AlignTop),
                metrics.elidedText(str(note), Qt.TextElideMode.ElideMiddle, note_rect.width()),
            )
        painter.restore()  # type: ignore[attr-defined]


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
