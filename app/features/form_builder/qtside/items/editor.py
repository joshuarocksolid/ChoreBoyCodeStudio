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
from app.qt.QtCore import QEvent, QObject, QPoint, QRect, QSettings, QSize, Qt
from app.qt.QtGui import QGuiApplication
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

_REGULAR = QSize(360, 320)
_WIDE = QSize(480, 360)


def open_editor(
    session: FormSession,
    node: NodeId,
    parent: Optional[QWidget],
    *,
    beside: Optional[QRect] = None,
    under: Optional[QRect] = None,
) -> Optional["ItemEditor"]:
    draft = load_draft(session.document, node)
    if draft is None:
        return None
    editor = ItemEditor(session, draft, parent)
    editor.seat(beside=beside, under=under)
    editor.show()
    editor.raise_()
    editor.focus_first()
    return editor


class ItemEditor(QFrame):
    def __init__(self, session: FormSession, draft: Draft, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.itemEditor")
        self._session = session
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

    @property
    def draft(self) -> Draft:
        return self._draft

    @property
    def token(self) -> str:
        return self._token

    def replace(self, draft: Draft) -> None:
        self._draft = draft
        self._commit()

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
        fresh = load_draft(self._session.document, self._draft.widget)
        if fresh is not None:
            self._draft = fresh

    def _finish(self) -> None:
        self._closed = True
        self._remember()
        self._detach()
        self.close()

    def _detach(self) -> None:
        app = QGuiApplication.instance()
        if app is not None and self._filter is not None:
            app.removeEventFilter(self._filter)

    def _remembered(self) -> QSize:
        raw = QSettings().value(self._size_key())
        if isinstance(raw, QSize) and raw.width() > 0 and raw.height() > 0:
            return raw
        return _WIDE if self._wide else _REGULAR

    def _remember(self) -> None:
        QSettings().setValue(self._size_key(), self.size())

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
