"""Outline: the structure pane, and a complete keyboard editor.

Tab nests into the previous container, Shift+Tab un-nests, Alt+Up/Down moves,
F2 renames in place and keeps the keyboard, "/" opens quick insert, and rows can
be dragged to reorder or reparent with a visible insertion line.
"""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from spikes.form_builder.catalog import CATALOG, fuzzy
from spikes.form_builder.commands import (
    Compound,
    Delete,
    EnsureLayout,
    MoveItem,
    Rename,
    SetItemAttrib,
    delete_targets,
    nest_command,
    next_cell,
    resolve_layout_item,
    unnest_command,
)
from spikes.form_builder.icons import glyph_for_class, paint_glyph
from spikes.form_builder.model import (
    Action,
    Layout,
    Spacer,
    Widget,
    all_names,
    child_widgets,
    find_node,
    get_property,
    item_content,
    layout_items,
    locate,
    unique_name,
    valid_identifier,
    widget_layout,
)
from spikes.form_builder.theme import current

ROLE_ID = Qt.UserRole
ROLE_KIND = Qt.UserRole + 1
ROLE_CLASS = Qt.UserRole + 2
ROLE_HINT = Qt.UserRole + 3
# PySide enum arithmetic runs in Python; build the flag sets once, not per row.
FLAGS = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
EDITABLE_FLAGS = FLAGS | Qt.ItemIsEditable


class OutlineDelegate(QStyledItemDelegate):
    """Glyph, name, and a muted detail; layouts in the layout colour."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 26)

    def paint(self, painter: QPainter, option, index: QModelIndex):
        tokens = current()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        if selected or hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(tokens.accent_soft if selected else tokens.surface_alt))
            painter.drawRoundedRect(rect.adjusted(0, 1, -4, -1), 5, 5)
        kind = index.data(ROLE_KIND) or "widget"
        class_name = index.data(ROLE_CLASS) or ""
        name = index.data(Qt.DisplayRole) or ""
        hint = index.data(ROLE_HINT) or ""
        glyph_color = {"layout": tokens.layout, "spacer": tokens.gap, "action": tokens.warn}.get(
            kind, tokens.accent if selected else tokens.muted
        )
        x = rect.left() + 4
        glyph = "Action" if kind == "action" else glyph_for_class(class_name)
        paint_glyph(painter, glyph, QRectF(x, rect.center().y() - 8, 16, 16), glyph_color)
        x += 24
        font = QFont(option.font)
        font.setPixelSize(13)
        font.setItalic(kind == "spacer")
        painter.setFont(font)
        metrics = QFontMetrics(font)
        painter.setPen(QColor(tokens.layout if kind == "layout" else tokens.text))
        available = rect.right() - x - 6
        elided = metrics.elidedText(name, Qt.ElideRight, int(max(available, 10)))
        painter.drawText(QRectF(x, rect.top(), available, rect.height()), Qt.AlignVCenter, elided)
        x += metrics.horizontalAdvance(elided) + 8
        small = QFont(font)
        small.setPixelSize(11)
        small.setItalic(False)
        painter.setFont(small)
        small_metrics = QFontMetrics(small)
        if hint and x < rect.right() - 24:
            painter.setPen(QColor(tokens.faint))
            text = small_metrics.elidedText(hint, Qt.ElideRight, int(rect.right() - x - 6))
            painter.drawText(QRectF(x, rect.top(), rect.right() - x, rect.height()), Qt.AlignVCenter, text)
        painter.restore()

    def createEditor(self, parent, option, index):
        tokens = current()
        editor = QLineEdit(parent)
        editor.setStyleSheet(
            "QLineEdit { font-size: 13px; padding: 0 4px; border: 2px solid %s; border-radius: 4px;"
            " background: %s; color: %s; }" % (tokens.accent, tokens.surface, tokens.text)
        )
        return editor

    def updateEditorGeometry(self, editor, option, index):
        rect = QRect(option.rect)
        rect.setLeft(rect.left() + 24)
        rect.setRight(rect.right() - 6)
        editor.setGeometry(rect.adjusted(0, 1, 0, -1))


class Outline(QTreeWidget):
    selection_made = Signal(list)
    context_requested = Signal(QPoint)
    quick_insert = Signal()
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        self.setMouseTracking(True)
        self.setItemDelegate(OutlineDelegate(self))
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda point: self.context_requested.emit(self.viewport().mapToGlobal(point)))
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.doc = None
        self.history = None
        self._quiet = False
        self._items: dict[str, QTreeWidgetItem] = {}
        self._collapsed: set[str] = set()
        self.itemSelectionChanged.connect(self._emit_selection)
        self.itemChanged.connect(self._renamed)
        self.itemCollapsed.connect(lambda item: self._collapsed.add(item.data(0, ROLE_ID)))
        self.itemExpanded.connect(lambda item: self._collapsed.discard(item.data(0, ROLE_ID)))

    def set_document(self, doc, history):
        self.doc = doc
        self.history = history
        self._collapsed = set()
        self._quiet = True
        self.clearSelection()
        self.setCurrentItem(None)
        self._quiet = False
        self.rebuild()

    # -- build
    def rebuild(self):
        selected = self.selected_ids()
        current_id = self.currentItem().data(0, ROLE_ID) if self.currentItem() is not None else None
        scroll = self.verticalScrollBar().value()
        self._quiet = True
        self.setUpdatesEnabled(False)
        self.clear()
        self._items = {}
        if self.doc is not None:
            root = self._node_item(self.doc.root)
            self.addTopLevelItem(root)
            for part in self.doc.root.body:
                if isinstance(part, Action):
                    root.addChild(self._action_item(part))
            if self._collapsed:
                self._expand(root)
            else:
                self.expandAll()
        self._quiet = False
        if selected:
            self.select_ids([node_id for node_id in selected if node_id in self._items], current_id)
        self.verticalScrollBar().setValue(scroll)
        self.setUpdatesEnabled(True)

    def _expand(self, item: QTreeWidgetItem):
        item.setExpanded(item.data(0, ROLE_ID) not in self._collapsed)
        for index in range(item.childCount()):
            self._expand(item.child(index))

    def _make(self, node_id, name, class_name, kind, hint="", editable=True) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, ROLE_ID, node_id)
        item.setData(0, ROLE_KIND, kind)
        item.setData(0, ROLE_CLASS, class_name)
        item.setData(0, ROLE_HINT, hint)
        item.setFlags(EDITABLE_FLAGS if editable else FLAGS)
        self._items[node_id] = item
        return item

    def _node_item(self, node) -> QTreeWidgetItem:
        if isinstance(node, Widget):
            text = ""
            for key in ("text", "title", "windowTitle", "placeholderText"):
                prop = get_property(node, key)
                if prop is not None and prop.body.tag == "string" and prop.body.text:
                    text = prop.body.text.replace("\n", " ")
                    break
            short = node.class_name.split("::")[-1]
            hint = f"{short}  “{text}”" if text and len(text) < 40 else short
            item = self._make(node.id, node.object_name or node.class_name, node.class_name, "widget", hint)
            layout = widget_layout(node)
            if layout is not None:
                item.addChild(self._layout_item(layout))
            for child in child_widgets(node):
                item.addChild(self._node_item(child))
            return item
        if isinstance(node, Layout):
            return self._layout_item(node)
        if isinstance(node, Spacer):
            return self._make(node.id, node.name or "spacer", "Spacer", "spacer", "spacer")
        return self._make(getattr(node, "id", ""), getattr(node, "object_name", "?"), type(node).__name__, "widget")

    def _layout_item(self, layout: Layout) -> QTreeWidgetItem:
        words = {"QVBoxLayout": "vertical", "QHBoxLayout": "horizontal", "QGridLayout": "grid", "QFormLayout": "form"}
        item = self._make(layout.id, layout.object_name or layout.class_name, layout.class_name, "layout", words.get(layout.class_name, layout.class_name))
        for child in layout_items(layout):
            content = item_content(child)
            if content is not None:
                item.addChild(self._node_item(content))
        return item

    def _action_item(self, action: Action) -> QTreeWidgetItem:
        text = get_property(action, "text")
        hint = f"action  “{text.body.text}”" if text is not None else "action"
        return self._make(action.id, action.name, "Action", "action", hint)

    # -- selection
    def selected_ids(self):
        return [item.data(0, ROLE_ID) for item in self.selectedItems() if item.data(0, ROLE_ID)]

    def select_ids(self, ids, current_id=None):
        self._quiet = True
        self.clearSelection()
        first = None
        for node_id in ids:
            item = self._items.get(node_id)
            if item is None:
                continue
            item.setSelected(True)
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            if first is None:
                first = item
        target = self._items.get(current_id) if current_id in ids else first
        if target is not None:
            self.setCurrentItem(target, 0, QItemSelectionModel.NoUpdate)
            self.scrollToItem(target)
        self._quiet = False

    def _emit_selection(self):
        if not self._quiet:
            self.selection_made.emit(self.selected_ids())

    # -- rename
    def _renamed(self, item, column):
        if self._quiet or column != 0 or self.history is None or self.doc is None:
            return
        node_id = item.data(0, ROLE_ID)
        node = find_node(self.doc, node_id)
        if node is None:
            return
        current_name = node.object_name if isinstance(node, (Widget, Layout)) else getattr(node, "name", "")
        text = item.text(0).strip()
        if text == current_name:
            return
        if not valid_identifier(text) or text in all_names(self.doc):
            self._quiet = True
            item.setText(0, current_name)
            self._quiet = False
            reason = "is already used" if valid_identifier(text) else "is not a Python name"
            self.status.emit(f"“{text}” {reason}. The name stays {current_name}.")
            return
        # Run after the editor closes, so the rebuild never deletes the row being edited.
        QTimer.singleShot(0, lambda: self._apply_rename(node_id, text))

    def _apply_rename(self, node_id, text):
        self.history.execute(Rename(node_id, text))
        self.select_ids([node_id])
        self.setFocus()

    # -- keyboard
    def keyPressEvent(self, event):
        if self.doc is None or self.history is None or self.state() == QAbstractItemView.EditingState:
            super().keyPressEvent(event)
            return
        ids = self.selected_ids()
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_F2 and self.currentItem() is not None:
            self.editItem(self.currentItem(), 0)
            return
        if event.text() == "/":
            self.quick_insert.emit()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace) and ids:
            targets = delete_targets(self.doc, ids)
            if targets:
                self._after_delete(ids)
                self.history.execute(Delete(targets))
            return
        if key == Qt.Key_Tab and not mods & Qt.ShiftModifier and ids:
            command = nest_command(self.doc, ids[0])
            if command is not None:
                self.history.execute(command)
            else:
                self.status.emit("Tab nests into the container just above. There is none here.")
            return
        if key == Qt.Key_Backtab or (key == Qt.Key_Tab and mods & Qt.ShiftModifier):
            if ids:
                command = unnest_command(self.doc, ids[0])
                if command is not None:
                    self.history.execute(command)
                else:
                    self.status.emit("Already at the top level of its container.")
            return
        if key in (Qt.Key_Up, Qt.Key_Down) and mods & Qt.AltModifier and ids:
            self.move_selection(ids[0], -1 if key == Qt.Key_Up else 1)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter) and self.currentItem() is not None:
            item = self.currentItem()
            if item.childCount():
                item.setExpanded(True)
                self.setCurrentItem(item.child(0))
            return
        if key == Qt.Key_Escape and self.currentItem() is not None and self.currentItem().parent() is not None:
            self.setCurrentItem(self.currentItem().parent())
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, _next):
        return False  # Tab belongs to nesting here, not to focus traversal.

    def _after_delete(self, ids):
        """Keep the keyboard in the tree: select the next sibling after a delete."""
        item = self._items.get(ids[0])
        if item is None or item.parent() is None:
            return
        parent = item.parent()
        position = parent.indexOfChild(item)
        if position + 1 < parent.childCount():
            sibling = parent.child(position + 1)
        elif position > 0:
            sibling = parent.child(position - 1)
        else:
            sibling = parent
        QTimer.singleShot(0, lambda node_id=sibling.data(0, ROLE_ID): self._reselect(node_id))

    def _reselect(self, node_id):
        if find_node(self.doc, node_id) is not None:
            self.select_ids([node_id])
            self.selection_made.emit([node_id])

    def move_selection(self, node_id, delta):
        item = resolve_layout_item(self.doc, node_id)
        if item is None:
            return
        located = locate(self.doc, item.id)
        if located is None or not isinstance(located[0], Layout):
            return
        layout = located[0]
        if layout.class_name in ("QFormLayout", "QGridLayout"):
            self._move_row(layout, item, delta)
            return
        items = layout_items(layout)
        index = items.index(item)
        target = index + delta
        if 0 <= target < len(items):
            self.history.execute(MoveItem(item.id, layout.id, target if delta < 0 else target + 1))

    def _move_row(self, layout, item, delta):
        """In a form or grid, Alt+Up/Down swaps the whole row with its neighbour."""
        rows = sorted({int(other.attrib.get("row", "0") or 0) for other in layout_items(layout)})
        row = int(item.attrib.get("row", "0") or 0)
        position = rows.index(row)
        if not 0 <= position + delta < len(rows):
            return
        other_row = rows[position + delta]
        steps = []
        for other in layout_items(layout):
            current_row = int(other.attrib.get("row", "0") or 0)
            if current_row in (row, other_row):
                attrib = dict(other.attrib)
                attrib["row"] = str(other_row if current_row == row else row)
                steps.append(SetItemAttrib(other.id, attrib))
        self.history.execute(Compound(steps))

    # -- drag and drop
    def dropEvent(self, event):
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        if self.doc is None or self.history is None or self.currentItem() is None:
            return
        target = self.itemAt(event.position().toPoint())
        source_id = self.currentItem().data(0, ROLE_ID)
        item = resolve_layout_item(self.doc, source_id)
        if item is None or target is None:
            return
        target_id = target.data(0, ROLE_ID)
        if target_id == source_id or self._contains(source_id, target_id):
            self.status.emit("A widget cannot go inside itself.")
            return
        command = self._drop_command(item, target_id, self.dropIndicatorPosition())
        if command is not None:
            self.history.execute(command)
            self.select_ids([source_id])
            self.selection_made.emit([source_id])

    def _drop_command(self, item, target_id, position):
        dest = find_node(self.doc, target_id)
        if position == QAbstractItemView.OnItem:
            layout = dest if isinstance(dest, Layout) else (widget_layout(dest) if isinstance(dest, Widget) else None)
            if layout is not None:
                return MoveItem(item.id, layout.id, len(layout_items(layout)), next_cell(layout, item_content(item)))
            if isinstance(dest, Widget) and dest.class_name in ("QWidget", "QFrame", "QGroupBox"):
                layout_id = self.doc.alloc()
                return Compound([
                    EnsureLayout(dest.id, "QVBoxLayout", layout_id, unique_name(self.doc, "verticalLayout")),
                    MoveItem(item.id, layout_id, 0, {}),
                ])
            return None
        holder = resolve_layout_item(self.doc, target_id)
        located = locate(self.doc, holder.id) if holder is not None else None
        if located is None or not isinstance(located[0], Layout):
            return None
        layout = located[0]
        below = position == QAbstractItemView.BelowItem
        if layout.class_name not in ("QFormLayout", "QGridLayout"):
            slot = layout_items(layout).index(holder) + (1 if below else 0)
            return MoveItem(item.id, layout.id, slot, {})
        row = int(holder.attrib.get("row", "0") or 0) + (1 if below else 0)
        steps = []
        for other in layout_items(layout):
            if other.id == item.id:
                continue
            current_row = int(other.attrib.get("row", "0") or 0)
            if current_row >= row:
                moved = dict(other.attrib)
                moved["row"] = str(current_row + 1)
                steps.append(SetItemAttrib(other.id, moved))
        content = item_content(item)
        is_label = isinstance(content, Widget) and content.class_name == "QLabel"
        column = "0" if layout.class_name == "QGridLayout" or is_label else "1"
        steps.append(MoveItem(item.id, layout.id, 10**6, {"row": str(row), "column": column}))
        return Compound(steps)

    def _contains(self, ancestor_id, node_id) -> bool:
        item = self._items.get(node_id)
        while item is not None:
            if item.data(0, ROLE_ID) == ancestor_id:
                return True
            item = item.parent()
        return False


class QuickInsert(QFrame):
    """Type to filter, arrows to move, Enter to insert. Says where the widget will land."""

    chosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Popover")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setObjectName("Search")
        self.edit.setPlaceholderText("Insert a widget…")
        from spikes.form_builder.icons import icon as make_icon

        self.edit.addAction(make_icon("search", current().faint), QLineEdit.LeadingPosition)
        self.where = QLabel("")
        self.where.setObjectName("Faint")
        self.where.setWordWrap(True)
        self.list = QListWidget()
        self.list.setIconSize(QSize(16, 16))
        self.list.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self.edit)
        layout.addWidget(self.where)
        layout.addWidget(self.list)
        self.edit.textChanged.connect(self.refresh)
        self.edit.returnPressed.connect(self.accept_current)
        self.edit.installEventFilter(self)
        self.list.itemClicked.connect(lambda _item: self.accept_current())
        self.resize(300, 380)
        self.refresh("")

    def refresh(self, text):
        from spikes.form_builder.icons import icon

        self.list.clear()
        tokens = current()
        for entry in CATALOG:
            if fuzzy(text, entry.label) or fuzzy(text, entry.class_name):
                color = tokens.layout if entry.kind == "layout" else (tokens.gap if entry.kind == "spacer" else tokens.muted)
                item = QListWidgetItem(icon(entry.class_name, color), entry.label)
                item.setData(Qt.UserRole, entry)
                item.setToolTip(entry.class_name)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        rows = max(1, min(self.list.count(), 11))
        self.list.setFixedHeight(rows * 28 + 6)
        self.adjustSize()

    def eventFilter(self, watched, event):
        if watched is self.edit and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key_Down, Qt.Key_Up):
                row = self.list.currentRow() + (1 if event.key() == Qt.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if event.key() == Qt.Key_Escape:
                self.close()
                return True
        return super().eventFilter(watched, event)

    def accept_current(self):
        item = self.list.currentItem()
        self.close()
        if item is not None:
            self.chosen.emit(item.data(Qt.UserRole))

    def popup_at(self, point, where: str = ""):
        self.where.setText(where)
        self.where.setVisible(bool(where))
        self.edit.clear()
        self.refresh("")
        self.move(point)
        self.show()
        self.raise_()
        self.edit.setFocus()
