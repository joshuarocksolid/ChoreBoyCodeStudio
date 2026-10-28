"""Pages group in the inspector (UX-CONT-019)."""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.commands.catalog import MovePage, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.pages import DeletePage, InsertPage
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.pages import (
    page_kind,
    page_title,
    page_widget_count,
    pages,
    start_index,
)
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.qtside.inspector.api import GroupHost, GroupId, Registrar, Row
from app.features.form_builder.qtside.inspector.editors._list_editor import ListEditor
from app.qt.QtWidgets import QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget


def register(registrar: Registrar) -> None:
    registrar.group_body(GroupId.PAGES, PagesBody, applies=_applies)


def _applies(document: object, owners: Tuple[NodeId, ...]) -> bool:
    if len(owners) != 1:
        return False
    return page_kind(document, owners[0]) is not None  # type: ignore[arg-type]


class PagesBody:
    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        self._host = host
        self._widget = QWidget(parent)
        self._widget.setObjectName("formBuilder.pagesGroup")
        self._list = ListEditor(name="Pages", parent=self._widget)
        self._list.set_on_add(self._add)
        self._list.set_on_delete(self._delete)
        self._list.set_on_move(self._move)
        self._list.set_on_edit(self._edit)
        self._list.set_on_space(self._space)
        self._list.set_on_focus(self._focus)
        self._list.set_read_only(self._locked)
        self._confirm = QWidget(self._widget)
        self._confirm.setObjectName("formBuilder.pageConfirm")
        self._confirm_text = QLabel(self._confirm)
        delete = QPushButton("Delete page", self._confirm)
        delete.setObjectName("formBuilder.pageConfirmDelete")
        delete.clicked.connect(self._confirm_delete)
        cancel = QPushButton("Cancel", self._confirm)
        cancel.clicked.connect(self._confirm.hide)
        row = QVBoxLayout(self._confirm)
        row.addWidget(self._confirm_text)
        row.addWidget(delete)
        row.addWidget(cancel)
        self._confirm.hide()
        self._pending: Optional[object] = None
        add = QToolButton(self._widget)
        add.setText("+ Add page")
        add.setObjectName("formBuilder.pagesAdd")
        add.clicked.connect(lambda: self._add(self._list.row_count() - 1))
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)
        layout.addWidget(add)
        layout.addWidget(self._confirm)

    @property
    def widget(self) -> QWidget:
        return self._widget

    def show(self, rows: Tuple[Row, ...]) -> None:
        del rows
        self._reload()

    def _reload(self) -> None:
        owners = self._host.owners
        if len(owners) != 1:
            self._list.set_texts(())
            return
        document = self._host.document
        found = pages(document, owners[0])
        kind = page_kind(document, owners[0])
        titles = []
        for index, page in enumerate(found):
            title = page_title(document, page.id)
            if kind is not None and kind.title_home is None:
                title = "Page %d %s" % (index + 1, page.object_name or "")
            titles.append(title)
        start = start_index(document, owners[0])
        self._list.set_start(None if start is None else start)
        self._list.set_texts(tuple(titles))

    def _add(self, index: int) -> None:
        self._run(InsertPage(self._owner(), index + 1 if index >= 0 else 0))

    def _move(self, index: int, target: int) -> None:
        self._run(MovePage(self._owner(), index, target))

    def _edit(self, index: int, text: str) -> None:
        page = self._page(index)
        kind = page_kind(self._host.document, self._owner())
        if page is None or kind is None or kind.title_home is None:
            return
        storage, name = kind.title_home
        command = SetProperty(page.id, name, StringValue(text), storage, merge_token="page-title:%s" % int(page.id))
        self._execute(command)

    def _space(self, index: int) -> None:
        kind = page_kind(self._host.document, self._owner())
        if kind is None or not kind.has_start_page:
            return
        self._run(SetProperty(self._owner(), "currentIndex", NumberValue(index)))

    def _delete(self, index: int) -> None:
        page = self._page(index)
        if page is None:
            return
        count = page_widget_count(self._host.document, page.id)
        command = DeletePage(self._owner(), index)
        if count <= 0:
            self._run(command)
            return
        title = page_title(self._host.document, page.id) or page.object_name or "page"
        noun = "widget" if count == 1 else "widgets"
        self._pending = command
        self._confirm_text.setText("Delete page \u201c%s\u201d and the %d %s on it?" % (title, count, noun))
        self._confirm.show()

    def _confirm_delete(self) -> None:
        command = self._pending
        self._pending = None
        self._confirm.hide()
        if command is not None:
            self._run(command)

    def _focus(self, index: int) -> None:
        live = self._host.live(self._owner())
        if live is None:
            return
        if hasattr(live, "setCurrentIndex"):
            live.setCurrentIndex(index)
        elif hasattr(live, "setCurrentId"):
            live.setCurrentId(index)

    def _locked(self, index: int) -> bool:
        kind = page_kind(self._host.document, self._owner())
        return kind is not None and kind.title_home is None

    def _run(self, command: object) -> None:
        self._host.run(getattr(command, "label", "Edit"), (command,))  # type: ignore[arg-type]
        self._reload()

    def _execute(self, command: object) -> None:
        session = getattr(self._host, "session", None)
        log = getattr(session, "log", None)
        if log is not None:
            log.execute(command)
        else:
            self._host.run(getattr(command, "label", "Edit"), (command,))  # type: ignore[arg-type]
        self._reload()

    def _owner(self) -> NodeId:
        return self._host.owners[0]

    def _page(self, index: int) -> object:
        found = pages(self._host.document, self._owner())
        if index < 0 or index >= len(found):
            return None
        return found[index]
