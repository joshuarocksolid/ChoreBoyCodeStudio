"""The Insert pane: header, filter, Recently used, categories, search results and Saved pieces.

Moved from ``integration/workbench.py`` (M4.1). Everything the pane needs from the
integration side arrives through constructor ports (``ports.py``) and setters.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QMimeData, QSize, Qt
from app.qt.QtGui import QAction, QActionGroup, QDrag, QKeyEvent, QMouseEvent
from app.qt.QtWidgets import (
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode
from app.features.form_builder.engine.ui4.schema import HeaderDecl
from app.features.form_builder.qtside.canvas.core.palette import MIME_INSERT
from app.features.form_builder.qtside.insert.catalog import load_catalog
from app.features.form_builder.qtside.insert.catalog._custom import custom_entries
from app.features.form_builder.qtside.insert.catalog._model import CATEGORY_ORDER, Entry
from app.features.form_builder.qtside.insert.delegate import ROW_ROLE, EntryDelegate
from app.features.form_builder.qtside.insert.header import PaneHeader
from app.features.form_builder.qtside.insert.pieces_box import PieceBox
from app.features.form_builder.qtside.insert.ports import InsertMemoryPort, PieceOps
from app.features.form_builder.qtside.insert.rows import ENTRY, HEADER, Row, browse_rows, search_rows
from app.features.form_builder.qtside.insert.search import search
from app.features.form_builder.qtside.theme.chrome import FormChrome

ICONS_MIN_WIDTH = 216
_KEY_ROW = Qt.ItemDataRole.UserRole
_ACCESSIBLE = Qt.ItemDataRole.AccessibleTextRole
_EMPTY_TEXT = "Nothing called “%s”. Try text, list or date."
_NOTHING_TO_INSERT = "Nothing to insert. Change the search or press Esc."
FREECAD_TIP = (
    "These widgets come from FreeCAD. In an app that runs without FreeCAD's window, "
    "each one is the plain Qt widget it is based on."
)


class InsertList(QListWidget):
    """The tile or row list. Keys follow UX-CAT-010; drags follow UX-CAT-011."""

    def __init__(self, pane: "InsertPane") -> None:
        super().__init__(pane)
        self._pane = pane

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        key = event.key()
        modifiers = event.modifiers()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._pane.activate_current()
            return
        if key == Qt.Key.Key_Escape:
            self._pane.escape()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and not modifiers:
            row = self._pane.current_row()
            if row is not None and row.kind == HEADER:
                self._pane.set_category_expanded(row.category, key == Qt.Key.Key_Right)
                return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and modifiers == Qt.KeyboardModifier.ControlModifier:
            self._pane.jump_category(1 if key == Qt.Key.Key_Down else -1)
            return
        text = event.text()
        if text and text.isprintable() and not modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            self._pane.type_into_filter(text)
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        item = self.itemAt(event.position().toPoint())
        row = _row_of(item)
        if row is not None and row.kind == HEADER and event.button() == Qt.MouseButton.LeftButton:
            self.setCurrentItem(item)
            self._pane.set_category_expanded(row.category, not row.expanded)
            event.accept()
            return
        super().mousePressEvent(event)

    def focusInEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        self._pane.announce_preview()

    def focusOutEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        self._pane.clear_preview()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if not event.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        item = self.currentItem()
        key = None if item is None else item.data(int(_KEY_ROW))
        if not key:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_INSERT, str(key).encode("utf-8"))
        drag.setMimeData(mime)
        action = drag.exec(Qt.DropAction.CopyAction)
        self._pane.drag_finished(str(key), action == Qt.DropAction.CopyAction)


class _FilterEdit(QLineEdit):
    def __init__(self, pane: "InsertPane") -> None:
        super().__init__(pane)
        self._pane = pane

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self._pane.escape()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._pane.activate_current()
            return
        if event.key() == Qt.Key.Key_Down:
            self._pane.focus_first()
            return
        super().keyPressEvent(event)


class InsertPane(QWidget):
    def __init__(
        self,
        on_collapsed: Callable[[bool], None],
        parent: QWidget,
        *,
        memory: InsertMemoryPort,
        pieces: PieceOps,
    ) -> None:
        super().__init__(parent)
        self._on_collapsed = on_collapsed
        self._memory = memory
        self._ops = pieces
        self._place: Optional[Callable[[str], None]] = None
        self._preview: Optional[Callable[[Optional[str]], None]] = None
        self._on_drag_finished: Optional[Callable[[], None]] = None
        self._leave: Optional[Callable[[], None]] = None
        self._report: Optional[Callable[[str], None]] = None
        self._open_window: Optional[Callable[[str], None]] = None
        self._entries: Tuple[Entry, ...] = load_catalog().entries
        self._windows: Tuple[Entry, ...] = load_catalog().windows
        self._custom: Tuple[Entry, ...] = ()
        self._query = ""
        self._chrome: Optional[FormChrome] = None
        self._session: Optional[FormSession] = None
        self._piece_store: Optional[object] = None
        self._pieces: Tuple[object, ...] = ()
        self._piece_unsub: Optional[Callable[[], None]] = None
        self._notice: Optional[Callable[[str, Callable[[], None]], None]] = None
        self._paste: Optional[Callable[[], None]] = None
        self._collapsed = False
        self._icons = False
        self._delegate = EntryDelegate(self)
        self.setObjectName("formBuilder.insert")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = PaneHeader("Insert", self, self._toggle)
        self.search_button = self.header.add_extra("⌕", "Search widgets", "formBuilder.insertSearch", True)
        self.search_button.clicked.connect(self._focus_filter)
        self.more_button = self.header.add_extra("⋯", "More insert options", "formBuilder.insertMore", True)
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_button.setMenu(self._build_menu())
        layout.addWidget(self.header)
        self.filter = _FilterEdit(self)
        self.filter.setObjectName("formBuilder.insertFilter")
        self.filter.setAccessibleName("Search widgets")
        self.filter.setPlaceholderText("Search widgets")
        self.filter.textChanged.connect(self._filter_changed)
        layout.addWidget(self.filter)
        self.caption = QLabel(self)
        self.caption.setObjectName("formBuilder.insertCaption")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.empty = QWidget(self)
        self.empty.setObjectName("formBuilder.insertEmpty")
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setContentsMargins(12, 12, 12, 12)
        self.empty_text = QLabel(self.empty)
        self.empty_text.setWordWrap(True)
        empty_layout.addWidget(self.empty_text)
        self.clear_link = QPushButton("Clear", self.empty)
        self.clear_link.setObjectName("formBuilder.insertClear")
        self.clear_link.setFlat(True)
        self.clear_link.clicked.connect(self._clear_filter)
        empty_layout.addWidget(self.clear_link, 0, Qt.AlignmentFlag.AlignLeft)
        self.empty.hide()
        layout.addWidget(self.empty)
        self.body = InsertList(self)
        self.body.setObjectName("formBuilder.insertBody")
        self.body.setAccessibleName("Insert")
        self.body.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.body.setItemDelegate(self._delegate)
        self.body.setUniformItemSizes(False)
        self.body.setResizeMode(QListView.ResizeMode.Adjust)
        self.body.itemActivated.connect(self._activated)
        self.body.currentItemChanged.connect(lambda *_args: self.announce_preview())
        layout.addWidget(self.body, 1)
        self._piece_box = PieceBox(self, self)
        self.destroyed.connect(lambda *_args: self._drop_piece_sub())
        layout.addWidget(self._piece_box)
        self._apply_view()
        self._refill()
        self._refresh_pieces()

    # Wiring from the workbench -----------------------------------------------------

    def set_place(self, place: Callable[[str], None]) -> None:
        self._place = place

    def set_preview(self, preview: Callable[[Optional[str]], None]) -> None:
        self._preview = preview

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)

    def set_drag_finished(self, done: Callable[[], None]) -> None:
        self._on_drag_finished = done

    def set_leave(self, leave: Callable[[], None]) -> None:
        """Esc with an empty filter hands focus back to the canvas (UX-CAT-010)."""
        self._leave = leave

    def set_report(self, report: Callable[[str], None]) -> None:
        self._report = report

    def set_open_window(self, open_window: Callable[[str], None]) -> None:
        """Enter on a window-kind row opens the New form tab with that card (UX-CAT-015)."""
        self._open_window = open_window

    def set_paste(self, paste: Callable[[], None]) -> None:
        self._paste = paste

    def set_notice(self, notice: Callable[[str, Callable[[], None]], None]) -> None:
        self._notice = notice

    def bind_session(self, session: FormSession) -> None:
        self._session = session
        self.refresh_custom()

    def apply_chrome(self, chrome: FormChrome) -> None:
        self._chrome = chrome
        self._delegate.set_chrome(chrome)
        self._piece_box.apply_chrome(chrome)
        self.body.viewport().update()

    # Custom widgets of this form ----------------------------------------------------

    def refresh_custom(self) -> None:
        """Rebuild the 'Your widgets' entries from the form's declarations (UX-CAT-005)."""
        session = self._session
        declared: List[Tuple[str, str, str]] = []
        if session is not None:
            for node in session.document.ui.children("customwidgets"):
                if isinstance(node, CustomWidgetNode) and node.class_name:
                    extends = node.field("extends")
                    header = node.field("header")
                    header_text = header.text if isinstance(header, HeaderDecl) else ""
                    declared.append(
                        (
                            node.class_name,
                            extends if isinstance(extends, str) else "QWidget",
                            header_text,
                        )
                    )
        found = custom_entries(declared)
        if found != self._custom:
            self._custom = found
            self._refill()

    # Pieces --------------------------------------------------------------------------

    def bind_pieces(self, store: Optional[object]) -> None:
        self._drop_piece_sub()
        self._piece_store = store
        if store is not None:
            self._pieces = tuple(getattr(store, "load")())
            self._piece_unsub = getattr(store, "subscribe")(self._on_pieces_changed)
        else:
            self._pieces = ()
        self._refresh_pieces()

    def _drop_piece_sub(self) -> None:
        unsub = self._piece_unsub
        self._piece_unsub = None
        if unsub is not None:
            unsub()

    def _on_pieces_changed(self) -> None:
        store = self._piece_store
        if store is None:
            return
        self._pieces = tuple(getattr(store, "load")())
        self._refresh_pieces()

    def save_selection(self, session: FormSession) -> None:
        self._session = session
        self._save_ids(session, session.selection.state.ids)

    def save_node(self, node_id: NodeId) -> None:
        session = self._session
        if session is None or not session.document.contains(node_id):
            return
        selected = session.selection.state.ids
        ids = selected if node_id in selected else (node_id,)
        self._save_ids(session, ids)

    def piece_at(self, index: int) -> Optional[object]:
        if index < 0 or index >= len(self._pieces):
            return None
        return self._pieces[index]

    def rename_piece(self, index: int, name: str) -> None:
        updated = tuple(self._ops.renamed(self._pieces, index, name))
        if updated == self._pieces:
            return
        self._pieces = updated
        self._store_pieces()
        self._refresh_pieces()

    def delete_piece(self, index: int) -> None:
        if index < 0 or index >= len(self._pieces):
            return
        removed = self._pieces[index]
        self._pieces = tuple(self._ops.without(self._pieces, index))
        self._store_pieces()
        self._refresh_pieces()
        notice = self._notice
        if notice is None:
            return

        def undo(slot: int = index, piece: object = removed) -> None:
            self._restore_piece(slot, piece)

        notice("Deleted %s." % getattr(removed, "name"), undo)

    def insert_piece(self, index: int) -> None:
        piece = self.piece_at(index)
        if piece is None:
            return
        self._ops.publish(str(getattr(piece, "xml")))
        paste = self._paste
        if paste is not None:
            paste()

    def piece_menu(self, index: int) -> QMenu:
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        rename.triggered.connect(lambda _checked=False, slot=index: self._prompt_rename(slot))
        delete.triggered.connect(lambda _checked=False, slot=index: self.delete_piece(slot))
        return menu

    def _restore_piece(self, index: int, piece: object) -> None:
        items = list(self._pieces)
        slot = index if 0 <= index <= len(items) else len(items)
        items.insert(slot, piece)
        self._pieces = tuple(items)
        self._store_pieces()
        self._refresh_pieces()

    def _save_ids(self, session: FormSession, ids: Sequence[NodeId]) -> None:
        taken = tuple(str(getattr(item, "name")) for item in self._pieces)
        piece = self._ops.for_ids(session.document, tuple(ids), taken)
        if piece is None:
            return
        self._pieces = self._pieces + (piece,)
        self._store_pieces()
        self._refresh_pieces()

    def _store_pieces(self) -> None:
        store = self._piece_store
        if store is not None:
            getattr(store, "replace")(self._pieces)

    def _refresh_pieces(self) -> None:
        self._piece_box.fill(self._pieces)
        self._piece_box.setVisible(not self._collapsed)
        self._piece_box.list.setVisible(not self._collapsed and bool(self._pieces))

    def _prompt_rename(self, index: int) -> None:
        if index < 0 or index >= len(self._pieces):
            return
        text, ok = QInputDialog.getText(
            self,
            "Rename piece",
            "Name:",
            QLineEdit.EchoMode.Normal,
            str(getattr(self._pieces[index], "name")),
        )
        if not ok:
            return
        self.rename_piece(index, str(text))

    # Collapse, focus and keys --------------------------------------------------------

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.filter.setVisible(not collapsed)
        self.body.setVisible(not collapsed)
        self._refresh_pieces()

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)
        self._on_collapsed(self._collapsed)

    def focus_filter(self) -> None:
        self._focus_filter()

    def _focus_filter(self) -> None:
        self.filter.setFocus()
        self.filter.selectAll()

    def focus_first(self) -> None:
        """Down from the filter: the first result or the first tile (UX-CAT-010)."""
        for index in range(self.body.count()):
            row = _row_of(self.body.item(index))
            if row is not None and row.kind == ENTRY:
                self.body.setCurrentRow(index)
                break
        self.body.setFocus()

    def focus_list(self) -> None:
        self.body.setFocus()

    def escape(self) -> None:
        """Esc in the filter clears it and keeps focus in Insert, on the list (UX-CAT-010)."""
        if self.filter.text():
            self.filter.clear()
            self.focus_list()
            return
        leave = self._leave
        if leave is not None:
            leave()

    def type_into_filter(self, text: str) -> None:
        self.filter.setFocus()
        self.filter.setText(self.filter.text() + text)
        self.filter.setCursorPosition(len(self.filter.text()))

    def current_row(self) -> Optional[Row]:
        return _row_of(self.body.currentItem())

    def activate_current(self) -> None:
        item = self.body.currentItem()
        if item is None:
            if self._query and self._report is not None:
                self._report(_NOTHING_TO_INSERT)
            return
        self._activated(item)

    def jump_category(self, step: int) -> None:
        """Ctrl+Down and Ctrl+Up: the first tile of the next or previous category (UX-CAT-010)."""
        headers = [index for index in range(self.body.count()) if _is_header(self.body.item(index))]
        current = self.body.currentRow()
        if step > 0:
            target = next((index for index in headers if index > current), None)
        else:
            start = max((index for index in headers if index <= current), default=None)
            before = [index for index in headers if start is not None and index < start]
            target = before[-1] if before else None
        if target is None:
            return
        following = target + 1
        landing = following if following < self.body.count() and _is_entry(self.body.item(following)) else target
        self.body.setCurrentRow(landing)

    def set_category_expanded(self, category: str, expanded: bool) -> None:
        if not category:
            return
        self._memory.set_expanded(category, expanded)
        self._refill(select_category=category)

    def _clear_filter(self) -> None:
        self.filter.clear()
        self.filter.setFocus()

    # Preview and drag ----------------------------------------------------------------

    def announce_preview(self) -> None:
        preview = self._preview
        if preview is None or not self.body.hasFocus():
            return
        item = self.body.currentItem()
        row = _row_of(item)
        key = row.key if row is not None and row.kind == ENTRY and not row.window else None
        preview(key or None)

    def clear_preview(self) -> None:
        preview = self._preview
        if preview is not None:
            preview(None)

    def drag_finished(self, key: str, copied: bool) -> None:
        if copied:
            self._memory.note_used(key)
            self.refresh_recent()
        done = self._on_drag_finished
        if done is not None:
            done()

    def _drag_finished(self) -> None:
        done = self._on_drag_finished
        if done is not None:
            done()

    def _activated(self, item: QListWidgetItem) -> None:
        row = _row_of(item)
        if row is None:
            return
        if row.kind == HEADER:
            self.set_category_expanded(row.category, not row.expanded)
            return
        if row.kind != ENTRY:
            return
        if row.window:
            opener = self._open_window
            if opener is not None:
                opener(row.key)
            return
        place = self._place
        if place is not None and row.key:
            place(row.key)

    # Filter and rows -----------------------------------------------------------------

    def _filter_changed(self, text: str) -> None:
        self._query = text.strip()
        self._refill()

    def _all_entries(self) -> Tuple[Entry, ...]:
        return self._entries + self._custom

    def _refill(self, select_category: str = "") -> None:
        query = self._query
        if query:
            hits = search(self._all_entries(), self._windows, query)
            rows = search_rows(hits, query)
        else:
            rows = browse_rows(self._all_entries(), self._memory.recent(), self._memory.expanded_states())
        self._fill(rows, select_category)
        self._apply_view()

    def refresh_recent(self) -> None:
        if not self._query:
            self._refill()

    def _fill(self, rows: Sequence[Row], select_category: str) -> None:
        current_key = ""
        previous = self.body.currentItem()
        previous_row = _row_of(previous)
        if previous_row is not None and previous_row.kind == ENTRY:
            current_key = previous_row.key
        self.body.clear()
        entries_found = 0
        select_row = -1
        for row in rows:
            item = QListWidgetItem("" if row.kind != ENTRY else row.title)
            item.setData(int(ROW_ROLE), row)
            if row.kind == ENTRY:
                entries_found += 1
                item.setData(int(_KEY_ROW), row.key)
                item.setToolTip(self._tooltip(row))
                name = "Insert %s" % row.title.lower()
                if row.search and row.category:
                    name = "%s, %s" % (name, row.category)
                item.setData(int(_ACCESSIBLE), name)
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                item.setFlags(flags)
                if select_row < 0 and current_key and row.key == current_key:
                    select_row = self.body.count()
            else:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                state = "expanded" if row.expanded else "collapsed"
                if row.kind == HEADER:
                    item.setData(int(_ACCESSIBLE), "%s, %d widgets, %s" % (row.title, row.count, state))
                    if row.category == "FreeCAD":
                        item.setToolTip(FREECAD_TIP)
                    if select_category and row.category == select_category:
                        select_row = self.body.count()
            self.body.addItem(item)
        if select_row < 0:
            select_row = next((index for index in range(self.body.count()) if _is_entry(self.body.item(index))), -1)
        if select_row >= 0:
            self.body.setCurrentRow(select_row)
        self._show_empty(bool(self._query) and entries_found == 0)

    def _show_empty(self, empty: bool) -> None:
        self.empty.setVisible(empty)
        self.body.setVisible(not empty and not self._collapsed)
        if empty:
            self.empty_text.setText(_EMPTY_TEXT % self._query)

    def _tooltip(self, row: Row) -> str:
        faint = self._chrome.faint if self._chrome is not None else ""
        qt_class = row.qt_class
        span = '<span style="color:%s">%s</span>' % (faint, qt_class) if faint else qt_class
        return "<b>%s</b><br>%s<br>%s" % (row.title, span, row.description)

    # View ----------------------------------------------------------------------------

    def _build_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        self._icons_action = QAction("Show as icons", menu)
        self._icons_action.setCheckable(True)
        self._list_action = QAction("Show as list", menu)
        self._list_action.setCheckable(True)
        for action in (self._icons_action, self._list_action):
            group.addAction(action)
            menu.addAction(action)
        self._icons_action.triggered.connect(lambda _checked=False: self._choose_view("icons"))
        self._list_action.triggered.connect(lambda _checked=False: self._choose_view("list"))
        menu.addSeparator()
        expand = menu.addAction("Expand all")
        collapse = menu.addAction("Collapse all")
        expand.triggered.connect(lambda _checked=False: self._set_all(True))
        collapse.triggered.connect(lambda _checked=False: self._set_all(False))
        menu.addSeparator()
        clear = menu.addAction("Clear recently used")
        clear.triggered.connect(lambda _checked=False: self._clear_recent())
        return menu

    def _choose_view(self, view: str) -> None:
        self._memory.set_view(view)
        self._apply_view()
        self._refill()

    def _set_all(self, expanded: bool) -> None:
        for category in _categories():
            self._memory.set_expanded(category, expanded)
        self._refill()

    def _clear_recent(self) -> None:
        self._memory.clear_recent()
        self._refill()

    def _auto_icons(self) -> bool:
        stored = self._memory.view()
        if stored == "icons":
            return True
        if stored == "list":
            return False
        return self.width() >= ICONS_MIN_WIDTH

    def _apply_view(self) -> None:
        icons = self._auto_icons()
        self._icons = icons
        self._delegate.set_icons(icons and not self._query)
        self._icons_action.setChecked(icons)
        self._list_action.setChecked(not icons)
        listing = icons and not self._query
        if listing:
            self.body.setViewMode(QListView.ViewMode.IconMode)
            self.body.setFlow(QListView.Flow.LeftToRight)
            self.body.setWrapping(True)
            self.body.setSpacing(0)
            self.body.setGridSize(QSize())
        else:
            self.body.setViewMode(QListView.ViewMode.ListMode)
            self.body.setFlow(QListView.Flow.TopToBottom)
            self.body.setWrapping(False)
            self.body.setSpacing(0)
        self._delegate.set_width(max(self.body.viewport().width(), ICONS_MIN_WIDTH // 2))
        self.body.doItemsLayout()

    def resizeEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_view()


def _row_of(item: Optional[QListWidgetItem]) -> Optional[Row]:
    if item is None:
        return None
    value = item.data(int(ROW_ROLE))
    return value if isinstance(value, Row) else None


def _is_header(item: Optional[QListWidgetItem]) -> bool:
    row = _row_of(item)
    return row is not None and row.kind == HEADER


def _is_entry(item: Optional[QListWidgetItem]) -> bool:
    row = _row_of(item)
    return row is not None and row.kind == ENTRY


def _categories() -> Tuple[str, ...]:
    return CATEGORY_ORDER

