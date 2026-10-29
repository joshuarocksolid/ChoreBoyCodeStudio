"""Item editor popover (UX-ITEM-002). One session, one undo step."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.commands.catalog import SetItems
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.items.model import (
    ITEM_CLASSES,
    MODEL_VIEW_SENTENCE,
    Draft,
    commit_slots,
    kind_of,
    load_draft,
)
from app.features.form_builder.qtside.items.place import seat_beside, seat_under
from app.features.form_builder.qtside.theme.chrome import FormChrome, default_chrome
from app.qt.QtCore import QEvent, QObject, QPoint, QRect, QSettings, QSize, Qt, QTimer
from app.qt.QtGui import QColor, QGuiApplication, QPalette
from app.qt.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

_REGULAR = QSize(360, 320)
# After the inspector's own watchers (UX-PED-004 sessions use 1000).
_WATCH_PRIORITY = 1000
_WIDE = QSize(480, 360)


def open_editor(
    session: FormSession,
    node: NodeId,
    parent: Optional[QWidget],
    *,
    beside: Optional[QRect] = None,
    under: Optional[QRect] = None,
    chrome: Optional[FormChrome] = None,
) -> Optional["ItemEditor"]:
    draft = load_draft(session.document, node)
    if draft is None:
        return None
    editor = ItemEditor(session, draft, parent, chrome=chrome)
    editor.seat(beside=beside, under=under)
    editor.show()
    editor.raise_()
    editor.focus_first()
    return editor


class ItemEditor(QFrame):
    def __init__(
        self,
        session: FormSession,
        draft: Draft,
        parent: Optional[QWidget] = None,
        *,
        chrome: Optional[FormChrome] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.itemEditor")
        self._session = session
        self._chrome = chrome or default_chrome()
        self._paint_chrome()
        # Picture pickers find the form's folder by walking up to a widget
        # whose ``_services.session`` has the form path (form_directory).
        self._services = _FormFolder(session)
        self._draft = draft
        self._token = "items:%s:%s" % (int(draft.widget), id(self))
        self._checkpoint = session.log.checkpoint()
        self._closed = False
        self._wide = draft.kind in ("tree", "table")
        tool = getattr(Qt, "Tool", None)
        frameless = getattr(Qt, "FramelessWindowHint", None)
        if tool is not None and frameless is not None:
            self.setWindowFlags(tool | frameless)
        self.setMinimumSize(240, 180)
        self._own_size: Optional[QSize] = None
        self.resize(self._remembered())
        column = QVBoxLayout(self)
        column.setContentsMargins(8, 8, 8, 8)
        column.setSpacing(6)
        header = QHBoxLayout()
        title = QLabel("Items of %s" % draft.name)
        title.setObjectName("formBuilder.itemEditorTitle")
        header.addWidget(title, 1)
        done = QPushButton("Done")
        done.setObjectName("formBuilder.itemEditorDone")
        done.clicked.connect(self.close_keep)
        header.addWidget(done)
        column.addLayout(header)
        self._body = _body_for(self)
        column.addWidget(self._body, 1)
        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(self))
        column.addLayout(grip_row)
        self._filter = _Escape(self)
        app = QGuiApplication.instance()
        if app is not None:
            app.installEventFilter(self._filter)
        # UX-ITEM-007: another widget selected, an undo, or any step this
        # editor did not make closes it and keeps what it wrote. The inspector
        # opener has no canvas to tell it, so the editor watches for itself.
        self._own = 0
        self._log_watch = session.log.subscribe(self._foreign, priority=_WATCH_PRIORITY)
        self._selection_watch = session.selection.subscribe(self._selection_changed)

    @property
    def session(self) -> FormSession:
        return self._session

    @property
    def chrome(self) -> FormChrome:
        return self._chrome

    def _paint_chrome(self) -> None:
        chrome = self._chrome
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(chrome.panel))
        palette.setColor(QPalette.WindowText, QColor(chrome.text))
        palette.setColor(QPalette.Base, QColor(chrome.input))
        palette.setColor(QPalette.Text, QColor(chrome.text))
        palette.setColor(QPalette.Button, QColor(chrome.panel))
        palette.setColor(QPalette.ButtonText, QColor(chrome.text))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    @property
    def draft(self) -> Draft:
        return self._draft

    @property
    def token(self) -> str:
        return self._token

    def replace(self, draft: Draft) -> None:
        self._draft = draft
        self._commit()

    def make_room(self, height: int) -> None:
        """Grow before a row popover (the item icon) opens in this window.

        A popover closes when its window resizes, so this runs before it
        shows. The remembered size stays the user's own.
        """
        if self.height() >= height:
            return
        if self._own_size is None:
            self._own_size = self.size()
        self.resize(self.width(), height)

    def focus_first(self) -> None:
        focus = getattr(self._body, "focus_first", None)
        if callable(focus):
            focus()

    def seat(self, *, beside: Optional[QRect], under: Optional[QRect]) -> None:
        size = self.size()
        if beside is not None:
            viewport = beside
            screen = _screen()
            if screen is not None:
                viewport = screen
            self.move(seat_beside(beside, size, viewport))
            return
        if under is not None:
            bounds = _screen() or under
            self.move(seat_under(under, size, bounds))
            return
        screen = _screen()
        if screen is not None:
            self.move(screen.center() - QPoint(size.width() // 2, size.height() // 2))

    def close_keep(self) -> None:
        if self._closed:
            return
        trim = getattr(self._body, "trimmed", None)
        if callable(trim):
            self._draft = trim(self._draft)
            self._commit()
        self._finish()

    def revert(self) -> None:
        if self._closed:
            return
        self._session.log.rollback(self._checkpoint, self._token)
        self._finish()

    def closeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        self._remember()
        self._detach()
        super().closeEvent(event)

    def _commit(self) -> None:
        items, rows, columns = commit_slots(self._draft)
        self._own += 1
        try:
            self._session.log.execute(
                SetItems(
                    self._draft.widget,
                    items,
                    rows,
                    columns,
                    merge_token=self._token,
                    widget_name=self._draft.name,
                )
            )
        finally:
            self._own -= 1
        fresh = load_draft(self._session.document, self._draft.widget)
        if fresh is not None:
            self._draft = fresh

    def _foreign(self, _change_set: object) -> None:
        if self._own or self._closed:
            return
        # Deferred: a log listener must not write. The draft may be stale now,
        # so close without writing it again.
        QTimer.singleShot(0, self._close_quietly)

    def _close_quietly(self) -> None:
        if not self._closed:
            self._finish()

    def _selection_changed(self, change: object) -> None:
        current = getattr(getattr(change, "after", None), "current", None)
        if current != self._draft.widget and not self._closed:
            QTimer.singleShot(0, self.close_keep)

    def _finish(self) -> None:
        self._closed = True
        self._remember()
        self._detach()
        self.close()
        # Each opening builds a new editor; do not keep closed ones around.
        self.deleteLater()

    def _detach(self) -> None:
        watch = getattr(self, "_log_watch", None)
        if watch is not None:
            watch.close()
            self._log_watch = None
        stop = getattr(self, "_selection_watch", None)
        if stop is not None:
            stop()
            self._selection_watch = None
        app = QGuiApplication.instance()
        if app is not None and self._filter is not None:
            app.removeEventFilter(self._filter)

    def _remembered(self) -> QSize:
        raw = QSettings().value(self._size_key())
        if isinstance(raw, QSize) and raw.width() > 0 and raw.height() > 0:
            return raw
        return _WIDE if self._wide else _REGULAR

    def _remember(self) -> None:
        QSettings().setValue(self._size_key(), self._own_size or self.size())

    def _size_key(self) -> str:
        return "formBuilder/itemEditor/wideSize" if self._wide else "formBuilder/itemEditor/size"


class _Escape(QObject):
    def __init__(self, editor: ItemEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        press = getattr(getattr(QEvent, "Type", QEvent), "KeyPress", None)
        if press is None:
            press = QEvent.KeyPress
        if event.type() != press:
            return False
        key = getattr(event, "key", None)
        if key is None or key() != getattr(Qt, "Key_Escape", None):
            return False
        if not _inside(watched, self._editor):
            return False
        if _cell_editing(watched) or _in_row_popover(watched):
            # A row popover (the item icon) handles its own Esc.
            # Esc in an open table cell cancels that cell, not the session.
            return False
        self._editor.revert()
        return True


def _inside(watched: QObject, editor: QWidget) -> bool:
    current: Optional[QObject] = watched
    seen = set()
    while current is not None and id(current) not in seen:
        if current is editor:
            return True
        seen.add(id(current))
        parent = current.parent()
        current = parent if isinstance(parent, QObject) else None
    return False


class _FormFolder:
    def __init__(self, session: FormSession) -> None:
        self.session = session


def _in_row_popover(watched: QObject) -> bool:
    current: Optional[QObject] = watched
    while current is not None:
        if current.objectName() == "formBuilder.rowPopover":
            return True
        parent = current.parent()
        current = parent if isinstance(parent, QObject) else None
    return False


def _cell_editing(watched: QObject) -> bool:
    current: Optional[QObject] = watched
    while current is not None:
        if isinstance(current, QAbstractItemView):
            return current.state() == QAbstractItemView.State.EditingState
        parent = current.parent()
        current = parent if isinstance(parent, QObject) else None
    return False


def _screen() -> Optional[QRect]:
    app = QGuiApplication.instance()
    if app is None:
        return None
    screen = app.primaryScreen()
    if screen is None:
        return None
    return screen.availableGeometry()


def _body_for(editor: ItemEditor) -> QWidget:
    kind = editor.draft.kind
    if kind in ("combo", "list"):
        from app.features.form_builder.qtside.items.list_body import ListBody

        return ListBody(editor)
    if kind == "tree":
        from app.features.form_builder.qtside.items.tree_body import TreeBody

        return TreeBody(editor)
    from app.features.form_builder.qtside.items.table_body import TableBody

    return TableBody(editor)


def widget_kind(class_name: str) -> Optional[str]:
    return kind_of(class_name)


def is_item_widget(class_name: str) -> bool:
    return class_name in ITEM_CLASSES


__all__ = ["MODEL_VIEW_SENTENCE", "ItemEditor", "is_item_widget", "open_editor"]
