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
from app.qt.QtCore import QByteArray, QEvent, QMimeData, QPoint, QRect, QSize, Qt, QTimer
from app.qt.QtGui import QColor, QDrag, QFont, QKeyEvent, QPainter, QPen
from app.qt.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

ROW_HEIGHT = 24
#: A list row also carries the "where it is used" caption, so it is two lines tall (UX-MAIN-010).
LIST_ROW_HEIGHT = 38
ICON_SIDE = 16
#: What a drag of Actions rows carries: the names of the actions, one per line.
MIME_ACTIONS = "application/x-cbcs-actions"
FILTER_PLACEHOLDER = "Search actions"
_COPIED: List[NodeSpec] = []

_ID_ROLE = Qt.ItemDataRole.UserRole
_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
_SHORTCUT_ROLE = Qt.ItemDataRole.UserRole + 2
_CAPTION_ROLE = Qt.ItemDataRole.UserRole + 3
_ICON_ROLE = Qt.ItemDataRole.UserRole + 4


def clipboard_specs() -> Tuple[NodeSpec, ...]:
    """Actions copied from any form of this session, for Ctrl+V into another (R3 139)."""
    return tuple(_COPIED)


class _RowDelegate(QStyledItemDelegate):
    """16 px icon square, the text, the shortcut in ``fb.faint``, and under them the caption (UX-MAIN-010)."""

    def __init__(self, pane: "ActionsPane") -> None:
        super().__init__(pane)
        self._pane = pane

    def sizeHint(self, option: QStyleOptionViewItem, index: object) -> QSize:  # noqa: N802
        return QSize(0, ROW_HEIGHT if self._pane.icons_only else LIST_ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: object) -> None:
        model = getattr(index, "model")()
        kind = getattr(index, "data")(_KIND_ROLE)
        text = str(getattr(index, "data")(Qt.ItemDataRole.DisplayRole) or "")
        shortcut = str(getattr(index, "data")(_SHORTCUT_ROLE) or "")
        caption = str(getattr(index, "data")(_CAPTION_ROLE) or "")
        has_icon = bool(getattr(index, "data")(_ICON_ROLE))
        del model
        painter.save()
        try:
            rect = QRect(option.rect)
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            palette = option.palette
            if selected:
                painter.fillRect(rect, palette.highlight())
            ink = palette.highlightedText().color() if selected else palette.text().color()
            faint = QColor(self._pane.faint_color() or "") if self._pane.faint_color() else QColor(ink)
            if selected or not faint.isValid():
                faint = QColor(ink)
                faint.setAlpha(170)
            icons_only = self._pane.icons_only
            x = rect.left() + 8 + (14 if getattr(index, "parent")().isValid() else 0)
            top = rect.top() + (rect.height() - ICON_SIDE) // 2 if icons_only else rect.top() + 4
            if kind == "action":
                # A blank square when the action has no picture; a filled one when it has.
                painter.setPen(QPen(faint, 1.0))
                if has_icon:
                    fill = QColor(faint)
                    fill.setAlpha(90)
                    painter.setBrush(fill)
                else:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRect(x, top, ICON_SIDE - 1, ICON_SIDE - 1))
            text_left = x + ICON_SIDE + 8
            line = QRect(text_left, rect.top() + 2, max(10, rect.right() - text_left - 8), 20 if not icons_only else rect.height() - 4)
            font = QFont(option.font)
            if kind == "group":
                font.setBold(True)
            painter.setFont(font)
            painter.setPen(ink)
            metrics = painter.fontMetrics()
            right = 0
            if shortcut and not icons_only:
                right = metrics.horizontalAdvance(shortcut) + 8
                painter.setPen(faint)
                painter.drawText(line, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), shortcut)
            painter.setPen(ink)
            shown = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(10, line.width() - right))
            painter.drawText(line, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), shown)
            if caption and not icons_only:
                small = QFont(option.font)
                small.setPixelSize(max(9, int(small.pointSizeF() * 1.25) - 2 if small.pointSizeF() > 0 else 10))
                painter.setFont(small)
                painter.setPen(faint)
                note = QRect(text_left, rect.top() + 20, max(10, rect.right() - text_left - 8), 16)
                painter.drawText(
                    note,
                    int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                    painter.fontMetrics().elidedText(caption, Qt.TextElideMode.ElideRight, note.width()),
                )
        finally:
            painter.restore()


class _Tree(QTreeWidget):
    def __init__(self, pane: "ActionsPane") -> None:
        super().__init__(pane)
        self._pane = pane
        self._press: Optional[QPoint] = None
        self.setItemDelegate(_RowDelegate(pane))

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        self._press = getattr(event, "pos")() if getattr(event, "button")() == Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def mouseMoveEvent(self, event: object) -> None:  # noqa: N802
        press = self._press
        if press is not None and (getattr(event, "pos")() - press).manhattanLength() >= QApplication.startDragDistance():
            self._press = None
            if self._pane.start_drag():
                return
        super().mouseMoveEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        self._press = None
        super().mouseReleaseEvent(event)  # type: ignore[arg-type]

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
        self._faint = ""
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
        self._tree.setColumnCount(1)
        self._tree.setHeaderHidden(True)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(14)
        self._tree.setUniformRowHeights(True)
        self._tree.setDragEnabled(False)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._menu_at)
        self._tree.itemSelectionChanged.connect(self._push_selection)
        self._tree.itemChanged.connect(self._text_edited)
        layout.addWidget(self._tree, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.refresh)
        self._sub = session.log.subscribe(self._changed, priority=PRIORITY_VIEWS)
        self._sel_unsub = session.selection.subscribe(self._selection_changed)
        self.refresh()

    # ------------------------------------------------------------ plumbing
    def apply_theme(self, tokens: object) -> None:
        """The look of the Outline and Insert sections, from the shell tokens (light, dark, both high contrast)."""

        def token(name: str, fallback: str = "") -> str:
            value = getattr(tokens, name, "") or fallback
            return str(value)

        width = int(getattr(tokens, "focus_border_width", 1) or 1)
        self.setStyleSheet(
            "QWidget#formBuilder\\.actions { background: %(panel)s; color: %(text)s; }"
            "QLabel#formBuilder\\.actions\\.title { color: %(muted)s; background: transparent;"
            " font-size: 10px; font-weight: 600; letter-spacing: 0.5px; }"
            "QLineEdit { background: %(edit)s; color: %(text)s; border: 1px solid %(border)s; }"
            "QLineEdit:focus { border: %(width)dpx solid %(accent)s; }"
            "QToolButton { background: transparent; color: %(text)s; border: none; min-width: 24px; min-height: 24px; }"
            "QToolButton:focus { border: %(width)dpx solid %(accent)s; }"
            "QTreeWidget#formBuilder\\.actions\\.list { background: %(edit)s; color: %(text)s; border: 1px solid %(border)s;"
            " selection-background-color: %(selected)s; selection-color: %(text)s; }"
            "QTreeWidget#formBuilder\\.actions\\.list::item:selected { background: %(selected)s; color: %(text)s; }"
            "QTreeWidget#formBuilder\\.actions\\.list:focus { border: %(width)dpx solid %(accent)s; }"
            % {
                "panel": token("panel_bg"),
                "text": token("text_primary"),
                "muted": token("text_muted", token("text_primary")),
                "edit": token("editor_bg", token("panel_bg")),
                "border": token("border"),
                "accent": token("accent"),
                "selected": token("tree_selected_bg", token("accent")),
                "width": width,
            }
        )
        self._faint = token("text_muted")
        self.refresh()

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
        self._tree.scheduleDelayedItemsLayout()
        self._tree.viewport().update()

    @property
    def icons_only(self) -> bool:
        """"Show as icons": one 24 px line per action, without the shortcut and the caption."""
        return self._icons

    def faint_color(self) -> str:
        return self._faint

    def start_drag(self) -> bool:
        """Drag the selected actions onto a menu or a toolbar (UX-MAIN-009, 010). True when a drag ran."""
        doc = self._session.document
        names = []
        for node_id in self._selected_actions():
            node = doc.get(node_id)
            if node is not None:
                names.append(str(node.field("name")))
        if not names:
            return False
        mime = QMimeData()
        mime.setData(MIME_ACTIONS, QByteArray("\n".join(names).encode("utf-8")))
        drag = QDrag(self._tree)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)
        return True

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
            parent = QTreeWidgetItem(self._tree, [name])
            parent.setData(0, _CAPTION_ROLE, "Only one on at a time")
            parent.setData(0, _ID_ROLE, int(node.id) if node is not None else 0)
            parent.setData(0, _KIND_ROLE, "group")
            for info in members:
                self._row(parent, info, selected)
            parent.setExpanded(True)
        if needle and shown == 0:
            row = QTreeWidgetItem(self._tree, ["New action “%s”" % self._filter.text().strip()])
            row.setData(0, _KIND_ROLE, "create")
        self._title.setText("ACTIONS %d" % len(infos))
        self._building = False

    def _row(self, parent: Optional[QTreeWidgetItem], info: q.ActionInfo, selected: set) -> None:
        item = QTreeWidgetItem(parent if parent is not None else self._tree)
        item.setText(0, q.plain_text(info.text) or info.name)
        # The shortcut and the used-in caption are fb.faint (UX-MAIN-010); the delegate paints them.
        item.setData(0, _SHORTCUT_ROLE, info.shortcut)
        item.setData(0, _CAPTION_ROLE, info.used_line)
        item.setData(0, _ICON_ROLE, info.has_icon)
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
            found.append((item.text(0), str(item.data(0, _SHORTCUT_ROLE) or ""), str(item.data(0, _CAPTION_ROLE) or "")))
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(index))
        return found

    def event(self, event: QEvent) -> bool:
        return super().event(event)
