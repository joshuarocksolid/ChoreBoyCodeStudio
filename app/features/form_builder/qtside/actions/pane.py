"""The Actions section of the left pane (UX-MAIN-010, 011, 019).

Rows are the form's actions: text with the mnemonic hidden, the shortcut, and
where the action is used ("File menu, toolBar" or "Not used"). Action groups
are rows with their actions under them. The pane reads the document and runs
commands through the session; it holds no state of its own beyond the filter.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import Rename, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.actions import (
    DeleteActions,
    GroupActions,
    NewAction,
    PasteActions,
    UngroupActions,
)
from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.spec import NodeSpec
from app.features.form_builder.engine.ui4.values import StringValue
from app.qt.QtCore import QEvent, QPoint, Qt, QTimer
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

ROW_HEIGHT = 24
FILTER_PLACEHOLDER = "Search actions"
_COPIED: List[NodeSpec] = []

_ID_ROLE = Qt.ItemDataRole.UserRole
_KIND_ROLE = Qt.ItemDataRole.UserRole + 1


def clipboard_specs() -> Tuple[NodeSpec, ...]:
    """Actions copied from any form of this session, for Ctrl+V into another (R3 139)."""
    return tuple(_COPIED)


class _Tree(QTreeWidget):
    def __init__(self, pane: "ActionsPane") -> None:
        super().__init__(pane)
        self._pane = pane

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if self._pane.handle_key(event):
            return
        super().keyPressEvent(event)


class ActionsPane(QWidget):
    def __init__(
        self,
        session: FormSession,
        say: Callable[[str], None],
        confirm: Callable[[str, str], bool],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._say = say
        self._confirm = confirm
        self._icons = False
        self._rows: Dict[int, QTreeWidgetItem] = {}
        self._building = False
        self.setObjectName("formBuilder.actions")
        self.setAccessibleName("Actions")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 4)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(4)
        self._title = QLabel("ACTIONS", self)
        self._title.setObjectName("formBuilder.actions.title")
        head.addWidget(self._title)
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText(FILTER_PLACEHOLDER)
        self._filter.setClearButtonEnabled(True)
        self._filter.setAccessibleName(FILTER_PLACEHOLDER)
        self._filter.textChanged.connect(self.refresh)
        head.addWidget(self._filter, 1)
        self._add = QToolButton(self)
        self._add.setText("+")
        self._add.setToolTip("New action")
        self._add.setAccessibleName("New action")
        self._add.clicked.connect(self.new_action)
        head.addWidget(self._add)
        more = QToolButton(self)
        more.setText("⋯")
        more.setAccessibleName("More")
        menu = QMenu(more)
        menu.addAction("Show as icons").triggered.connect(lambda: self._show_as(True))
        menu.addAction("Show as list").triggered.connect(lambda: self._show_as(False))
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        head.addWidget(more)
        layout.addLayout(head)
        self._tree = _Tree(self)
        self._tree.setObjectName("formBuilder.actions.list")
        self._tree.setAccessibleName("Actions list")
        self._tree.setColumnCount(3)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(14)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._menu_at)
        self._tree.itemSelectionChanged.connect(self._push_selection)
        self._tree.itemChanged.connect(self._text_edited)
        self._tree.header().setStretchLastSection(False)
        layout.addWidget(self._tree, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.refresh)
        self._sub = session.log.subscribe(self._changed, priority=PRIORITY_VIEWS)
        self._sel_unsub = session.selection.subscribe(self._selection_changed)
        self.refresh()

    # ------------------------------------------------------------ plumbing
    def dispose(self) -> None:
        self._timer.stop()
        self._sub.close()
        self._sel_unsub()

    def _changed(self, _change: object) -> None:
        self._timer.start()

    def focus_tree(self) -> None:
        self._tree.setFocus()
        if self._tree.currentItem() is None and self._tree.topLevelItemCount():
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    def _show_as(self, icons: bool) -> None:
        self._icons = icons
        self.refresh()

    # --------------------------------------------------------------- rows
    def refresh(self, *_args: object) -> None:
        doc = self._session.document
        infos = q.list_actions(doc)
        needle = self._filter.text().strip().lower()
        self._building = True
        selected = set(self._session.selection.state.ids)
        self._tree.clear()
        self._rows = {}
        shown = 0
        by_group: Dict[Optional[str], List[q.ActionInfo]] = {}
        for info in infos:
            if needle and needle not in q.plain_text(info.text).lower() and needle not in info.name.lower():
                continue
            by_group.setdefault(info.group, []).append(info)
            shown += 1
        groups = {node.field("name"): node for node in q.action_groups(doc)}
        for info in by_group.get(None, ()):
            self._row(None, info, selected)
        for name, members in by_group.items():
            if name is None:
                continue
            node = groups.get(name)
            parent = QTreeWidgetItem(self._tree, [name, "", "Only one on at a time"])
            parent.setData(0, _ID_ROLE, int(node.id) if node is not None else 0)
            parent.setData(0, _KIND_ROLE, "group")
            parent.setSizeHint(0, parent.sizeHint(0).expandedTo(parent.sizeHint(0)))
            for info in members:
                self._row(parent, info, selected)
            parent.setExpanded(True)
        if needle and shown == 0:
            row = QTreeWidgetItem(self._tree, ["New action “%s”" % self._filter.text().strip(), "", ""])
            row.setData(0, _KIND_ROLE, "create")
        self._title.setText("ACTIONS %d" % len(infos))
        self._building = False

    def _row(self, parent: Optional[QTreeWidgetItem], info: q.ActionInfo, selected: set) -> None:
        item = QTreeWidgetItem(parent if parent is not None else self._tree)
        item.setText(0, q.plain_text(info.text) or info.name)
        item.setText(1, info.shortcut)
        item.setText(2, info.used_line)
        item.setData(0, _ID_ROLE, int(info.id))
        item.setData(0, _KIND_ROLE, "action")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setToolTip(0, info.name)
        item.setSelected(info.id in selected)
        self._rows[int(info.id)] = item

    def _selected_actions(self) -> Tuple[NodeId, ...]:
        found = []
        for item in self._tree.selectedItems():
            if item.data(0, _KIND_ROLE) == "action":
                found.append(NodeId(item.data(0, _ID_ROLE)))
        return tuple(found)

    def _current(self) -> Optional[QTreeWidgetItem]:
        return self._tree.currentItem()

    # ---------------------------------------------------------- selection
    def _push_selection(self) -> None:
        if self._building:
            return
        ids = self._selected_actions()
        if ids:
            self._session.selection.set(ids, source=SelectionSource.PROGRAM)

    def _selection_changed(self, _change: object) -> None:
        if self._building:
            return
        chosen = set(self._session.selection.state.ids)
        self._building = True
        try:
            for number, item in self._rows.items():
                want = NodeId(number) in chosen
                if item.isSelected() != want and (want or not self._tree.hasFocus()):
                    item.setSelected(want)
        finally:
            self._building = False

    # ------------------------------------------------------------ commands
    def new_action(self, text: str = "") -> None:
        typed = text if isinstance(text, str) and text else self._filter.text().strip()
        if not typed:
            typed = "New action"
        try:
            made = self._session.log.execute(NewAction(typed)).result
        except CommandRejected as refusal:
            self._say(str(refusal))
            return
        self._filter.clear()
        self.refresh()
        item = self._rows.get(int(made))
        if item is not None:
            self._tree.setCurrentItem(item)
            self._tree.clearSelection()
            item.setSelected(True)

    def delete_selected(self) -> None:
        ids = self._selected_actions()
        if not ids:
            return
        doc = self._session.document
        infos = {info.id: info for info in q.list_actions(doc)}
        used = [infos[i] for i in ids if i in infos and infos[i].places]
        if used:
            first = used[0]
            if len(ids) == 1:
                sentence = "Delete the action %s? It's on %s." % (q.plain_text(first.text), " and ".join(first.used_line.split(", ")))
            else:
                sentence = "Delete %d actions? %d of them are used." % (len(ids), len(used))
            if not self._confirm(sentence, "Delete action"):
                return
        first_info = infos.get(ids[0])
        text = q.plain_text(first_info.text) if first_info is not None else ""
        try:
            self._session.log.execute(DeleteActions(ids, text))
        except CommandRejected as refusal:
            self._say(str(refusal))

    def rename_current(self) -> None:
        item = self._current()
        if item is None or item.data(0, _KIND_ROLE) not in ("action", "group"):
            return
        node_id = NodeId(item.data(0, _ID_ROLE))
        node = self._session.document.get(node_id)
        if node is None:
            return
        from app.qt.QtWidgets import QInputDialog

        old = str(node.field("name"))
        new, ok = QInputDialog.getText(self, "Rename", "Object name", text=old)
        if ok and new and new != old:
            try:
                self._session.log.execute(Rename(node_id, new))
            except CommandRejected as refusal:
                self._say(str(refusal))

    def group_selected(self) -> None:
        ids = self._selected_actions()
        try:
            self._session.log.execute(GroupActions(ids))
        except CommandRejected as refusal:
            self._say(str(refusal))

    def ungroup(self, group: NodeId) -> None:
        try:
            self._session.log.execute(UngroupActions(group))
        except CommandRejected as refusal:
            self._say(str(refusal))

    def copy_selected(self) -> None:
        doc = self._session.document
        specs = [doc.node(i).to_spec() for i in self._selected_actions()]
        if specs:
            _COPIED[:] = specs

    def paste(self) -> None:
        if not _COPIED:
            return
        try:
            self._session.log.execute(PasteActions(tuple(_COPIED)))
        except CommandRejected as refusal:
            self._say(str(refusal))

    def _text_edited(self, item: QTreeWidgetItem, column: int) -> None:
        if self._building or column != 0 or item.data(0, _KIND_ROLE) != "action":
            return
        node_id = NodeId(item.data(0, _ID_ROLE))
        node = self._session.document.get(node_id)
        text = item.text(0)
        if node is None or not text.strip() or text == q.plain_text(q.text_of(node)):
            self.refresh()
            return
        try:
            self._session.log.execute(SetProperty(node_id, "text", StringValue(text)))
        except CommandRejected as refusal:
            self._say(str(refusal))

    # ----------------------------------------------------------------- keys
    def handle_key(self, event: QKeyEvent) -> bool:
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        item = self._current()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if item is not None and item.data(0, _KIND_ROLE) == "create":
                self.new_action(self._filter.text())
            elif item is not None and item.data(0, _KIND_ROLE) == "action":
                self._tree.editItem(item, 0)
            return True
        if key == Qt.Key.Key_F2:
            self.rename_current()
            return True
        if key == Qt.Key.Key_Delete:
            self.delete_selected()
            return True
        if ctrl and key == Qt.Key.Key_C:
            self.copy_selected()
            return True
        if ctrl and key == Qt.Key.Key_V:
            self.paste()
            return True
        text = event.text()
        if text and text.isprintable() and not ctrl and not (mods & Qt.KeyboardModifier.AltModifier):
            self._filter.setFocus()
            self._filter.setText(self._filter.text() + text)
            return True
        return False

    # ----------------------------------------------------------------- menu
    def _menu_at(self, point: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("New action").triggered.connect(lambda: self.new_action(""))
        ids = self._selected_actions()
        if len(ids) >= 2:
            menu.addAction("Make a choice group").triggered.connect(self.group_selected)
        item = self._tree.itemAt(point)
        if item is not None and item.data(0, _KIND_ROLE) == "group":
            group = NodeId(item.data(0, _ID_ROLE))
            menu.addAction("Ungroup").triggered.connect(lambda: self.ungroup(group))
        if ids:
            menu.addAction("Delete").triggered.connect(self.delete_selected)
        menu.exec(self._tree.viewport().mapToGlobal(point))

    def row_texts(self) -> Sequence[Tuple[str, str, str]]:
        """``(text, shortcut, used-in)`` for each visible row: what a test or a screenshot reads."""
        found: List[Tuple[str, str, str]] = []

        def walk(item: QTreeWidgetItem) -> None:
            found.append((item.text(0), item.text(1), item.text(2)))
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(index))
        return found

    def event(self, event: QEvent) -> bool:
        return super().event(event)
