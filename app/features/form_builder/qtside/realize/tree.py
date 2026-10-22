"""Container reconcile. Live widgets move through a pool keyed by node id.

Phase 1 detaches every moved object before any container is rebuilt. Phase 2
then walks dirty containers shallow-first, so a widget that moved into an
earlier container is already in the pool when that container asks for it.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.qt import QtGui, QtWidgets
from app.qt.QtCore import Qt
from app.qt.QtGui import QAction, QActionGroup, QIcon
from app.qt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QGridLayout,
    QLayout,
    QListWidget,
    QMainWindow,
    QMdiArea,
    QMenu,
    QMenuBar,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolBox,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QWizard,
)
from app.qt.qt_compat import delete_now, wrapper_is_valid
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import child_stack_order
from app.features.form_builder.engine.ui4.nodes import (
    ActionGroupNode,
    ActionNode,
    ActionRefNode,
    CustomWidgetNode,
    LayoutItemNode,
    LayoutNode,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.values import EnumValue, SizeValue
from app.features.form_builder.qtside.realize.props import (
    apply_entry,
    resolve_enum,
    splitter_sizes,
    text_of,
    to_qt,
)

NODE_ID_PROPERTY = "_cbcsNodeId"

_PAGE_CLASSES = frozenset(
    {
        "QTabWidget",
        "QStackedWidget",
        "QToolBox",
        "QSplitter",
        "QWizard",
        "QMdiArea",
        "QScrollArea",
    }
)
_MENU_CLASSES = frozenset({"QMenuBar", "QMenu", "QToolBar"})
_DIRECT = Qt.FindDirectChildrenOnly


class _Structure:
    """Methods mixed into ``Realizer``. Attributes live on the realizer."""

    def _qt_class_name(self, class_name: str) -> str:
        doc = self._session.document
        for node in doc.ui.children("customwidgets"):
            if isinstance(node, CustomWidgetNode) and node.class_name == class_name and node.extends:
                return node.extends.split("::")[-1]
        return class_name.split("::")[-1]

    def _widget_type(self, class_name: str) -> type:
        short = self._qt_class_name(class_name)
        cls = getattr(QtWidgets, short, None)
        if cls is None:
            cls = getattr(QtGui, short, None)
        if cls is None or not isinstance(cls, type):
            self._problems.append("class %s is not a Qt widget; using QWidget" % class_name)
            return QWidget
        return cls

    def _construct(self, node: WidgetNode, parent: Optional[QWidget]) -> QWidget:
        cls = self._widget_type(node.class_name)
        try:
            widget = cls(parent)
        except (TypeError, RuntimeError) as exc:
            self._problems.append("class %s: %s" % (node.class_name, exc))
            widget = QWidget(parent)
        self._tag(widget, node.id)
        widget.setObjectName(node.object_name)
        widget.setFocusPolicy(Qt.NoFocus)
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if isinstance(widget, QMenuBar):
            widget.setNativeMenuBar(False)
        self._widgets[node.id] = widget
        self._objects[node.id] = widget
        self._created += 1
        is_root = parent is None and self._root is None
        self._apply_node_properties(node, widget, is_root=is_root or widget is self._root)
        return widget

    def _create_widget(self, node: WidgetNode, parent: Optional[QWidget]) -> QWidget:
        widget = self._construct(node, parent)
        self._ensure_actions(node, widget)
        self._fill_widget(node, widget)
        return widget

    def _obtain_widget(self, node: WidgetNode, parent: Optional[QWidget]) -> QWidget:
        pooled = self._pool.pop(node.id, None)
        if isinstance(pooled, QWidget):
            if pooled.parentWidget() is not parent:
                pooled.setParent(parent)
            self._widgets[node.id] = pooled
            return pooled
        return self._create_widget(node, parent)

    def _fill_widget(self, node: WidgetNode, widget: QWidget) -> None:
        kind = self._qt_class_name(node.class_name)
        if kind == "QMainWindow" and isinstance(widget, QMainWindow):
            self._fill_main_window(node, widget)
        elif kind == "QDockWidget" and isinstance(widget, QDockWidget):
            self._fill_dock(node, widget)
        elif kind in _PAGE_CLASSES:
            self._fill_pages(node, widget)
        elif kind in _MENU_CLASSES:
            self._fill_menu(node, widget)
        else:
            layout = node.layout
            if isinstance(layout, LayoutNode):
                self._ensure_layout(layout, widget)
                self._fill_layout(layout)
            else:
                self._drop_layout(widget)
                self._fill_loose(node, widget)
        self._sync_items(node, widget)
        self._apply_late(node, widget)

    def _fill_loose(self, node: WidgetNode, widget: QWidget) -> None:
        for child in node.child_widgets:
            self._obtain_widget(child, widget)

    def _fill_pages(self, node: WidgetNode, widget: QWidget) -> None:
        self._drain_pages(widget)
        children = node.child_widgets
        if isinstance(widget, QScrollArea):
            if children:
                child = self._obtain_widget(children[0], None)
                widget.setWidget(child)
            return
        if isinstance(widget, QMdiArea):
            self._clear_mdi(widget)
            for child_node in children:
                child = self._obtain_widget(child_node, None)
                sub = widget.addSubWindow(child)
                self._mdi[child_node.id] = sub
            return
        if isinstance(widget, QWizard):
            for child_node in children:
                page = self._obtain_widget(child_node, None)
                widget.addPage(page)
                title = _page_title(child_node)
                if title and hasattr(page, "setTitle"):
                    page.setTitle(title)
            return
        for child_node in children:
            page = self._obtain_widget(child_node, None)
            title = _page_title(child_node)
            if isinstance(widget, QTabWidget):
                index = widget.addTab(page, title)
                _apply_page_attrs(widget, index, child_node)
            elif isinstance(widget, QToolBox):
                index = widget.addItem(page, title)
                tip = _attr_text(child_node, "toolTip")
                if tip:
                    widget.setItemToolTip(index, tip)
            else:
                widget.addWidget(page)

    def _fill_dock(self, node: WidgetNode, widget: QDockWidget) -> None:
        children = node.child_widgets
        if not children:
            return
        child = self._obtain_widget(children[0], None)
        current = widget.widget()
        if current is not None and current is not child:
            current.setParent(None)
        widget.setWidget(child)

    def _fill_main_window(self, node: WidgetNode, widget: QMainWindow) -> None:
        central = None
        for child in node.child_widgets:
            kind = self._qt_class_name(child.class_name)
            if kind == "QMenuBar":
                bar = self._obtain_widget(child, widget)
                if isinstance(bar, QMenuBar):
                    widget.setMenuBar(bar)
            elif kind == "QStatusBar":
                bar = self._obtain_widget(child, widget)
                widget.setStatusBar(bar)
            elif kind == "QToolBar":
                bar = self._obtain_widget(child, widget)
                if isinstance(bar, QToolBar):
                    widget.addToolBar(bar)
            elif kind == "QDockWidget":
                dock = self._obtain_widget(child, widget)
                if isinstance(dock, QDockWidget):
                    widget.addDockWidget(Qt.LeftDockWidgetArea, dock)
            elif central is None:
                central = child
                body = self._obtain_widget(child, widget)
                widget.setCentralWidget(body)
        self._fill_menu(node, widget)

    def _fill_menu(self, node: WidgetNode, widget: QWidget) -> None:
        if isinstance(widget, (QMenu, QMenuBar, QToolBar)):
            widget.clear()
        menus: Dict[str, QMenu] = {}
        for child in node.child_widgets:
            if self._qt_class_name(child.class_name) != "QMenu":
                continue
            menu = self._obtain_widget(child, widget)
            if isinstance(menu, QMenu) and child.object_name:
                menus[child.object_name] = menu
        actions = self._actions_by_name()
        added = set()
        for ref in node.children("add_actions"):
            if not isinstance(ref, ActionRefNode):
                continue
            name = ref.field("name")
            if not isinstance(name, str):
                continue
            if name == "separator" and hasattr(widget, "addSeparator"):
                widget.addSeparator()
                continue
            menu = menus.get(name)
            if menu is not None:
                widget.addAction(menu.menuAction())
                added.add(name)
                continue
            action = actions.get(name)
            if action is not None:
                widget.addAction(action)
        for name, menu in menus.items():
            if name not in added:
                widget.addAction(menu.menuAction())

    def _ensure_actions(self, node: WidgetNode, widget: QWidget) -> None:
        for child in node.children("action_groups"):
            if isinstance(child, ActionGroupNode) and child.id not in self._actions:
                group = QActionGroup(widget)
                group.setObjectName(child.name)
                self._tag(group, child.id)
                self._actions[child.id] = group
                self._objects[child.id] = group
                self._apply_node_properties(child, group, is_root=False)
        for child in node.children("actions"):
            if not isinstance(child, ActionNode) or child.id in self._actions:
                continue
            action = QAction(widget)
            action.setObjectName(child.name)
            self._tag(action, child.id)
            self._actions[child.id] = action
            self._objects[child.id] = action
            self._apply_node_properties(child, action, is_root=False)

    def _ensure_layout(self, node: LayoutNode, host: Optional[QWidget]) -> QLayout:
        existing = self._layouts.get(node.id)
        short = self._qt_class_name(node.class_name)
        if existing is not None and type(existing).__name__ == short and wrapper_is_valid(existing):
            if host is not None and host.layout() is not existing:
                self._release_layout(existing)
                if host.layout() is not None:
                    self._drop_layout(host)
                host.setLayout(existing)
            return existing
        if existing is not None:
            self._detach_layout(existing)
            self._forget_layout(node.id)
            _delete_layout(existing)
        cls = getattr(QtWidgets, short, QtWidgets.QVBoxLayout)
        if host is not None:
            if host.layout() is not None:
                self._drop_layout(host)
            if host.layout() is None:
                qlayout = cls(host)
            else:
                qlayout = cls()
                self._problems.append(
                    "class %s keeps its own layout; the document layout was not installed"
                    % type(host).__name__
                )
        else:
            qlayout = cls()
        qlayout.setObjectName(node.object_name)
        self._tag(qlayout, node.id)
        self._layouts[node.id] = qlayout
        self._objects[node.id] = qlayout
        self._apply_node_properties(node, qlayout, is_root=False)
        return qlayout

    def _fill_layout(self, node: LayoutNode) -> None:
        host = None
        owner_id = node.owner_widget_id()
        if owner_id is not None:
            host = self._widgets.get(owner_id)
        qlayout = self._ensure_layout(node, host)
        self._detach_layout(qlayout)
        if node.class_name == "QFormLayout" and isinstance(qlayout, QFormLayout):
            for item in _form_order(node):
                self._place_form(qlayout, item)
        elif node.class_name == "QGridLayout" and isinstance(qlayout, QGridLayout):
            for item in node.items:
                self._place_grid(qlayout, item)
        else:
            for item in node.items:
                self._place_box(qlayout, item)
        self._apply_stretches(node, qlayout)

    def _place_box(self, qlayout: QLayout, item: LayoutItemNode) -> None:
        content = item.content
        if isinstance(content, WidgetNode):
            widget = self._obtain_widget(content, qlayout.parentWidget())
            qlayout.addWidget(widget)
            _align(qlayout, widget, item)
        elif isinstance(content, LayoutNode):
            nested = self._ensure_layout(content, None)
            self._fill_layout(content)
            self._release_layout(nested)
            qlayout.addLayout(nested)
        elif isinstance(content, SpacerNode):
            qlayout.addItem(self._spacer(content))

    def _place_grid(self, qlayout: QGridLayout, item: LayoutItemNode) -> None:
        content = item.content
        row = item.row or 0
        column = item.column or 0
        rowspan = item.rowspan or 1
        colspan = item.colspan or 1
        if isinstance(content, WidgetNode):
            widget = self._obtain_widget(content, qlayout.parentWidget())
            qlayout.addWidget(widget, row, column, rowspan, colspan)
            _align(qlayout, widget, item)
        elif isinstance(content, LayoutNode):
            nested = self._ensure_layout(content, None)
            self._fill_layout(content)
            self._release_layout(nested)
            qlayout.addLayout(nested, row, column, rowspan, colspan)
        elif isinstance(content, SpacerNode):
            qlayout.addItem(self._spacer(content), row, column, rowspan, colspan)

    def _place_form(self, qlayout: QFormLayout, item: LayoutItemNode) -> None:
        content = item.content
        row = item.row or 0
        role = _form_role(item)
        if isinstance(content, WidgetNode):
            widget = self._obtain_widget(content, qlayout.parentWidget())
            qlayout.setWidget(row, role, widget)
        elif isinstance(content, LayoutNode):
            nested = self._ensure_layout(content, None)
            self._fill_layout(content)
            self._release_layout(nested)
            qlayout.setLayout(row, role, nested)
        elif isinstance(content, SpacerNode):
            qlayout.setItem(row, role, self._spacer(content))

    def _spacer(self, node: SpacerNode) -> object:
        pooled = self._pool.pop(node.id, None)
        if isinstance(pooled, QSpacerItem):
            self._spacers[node.id] = pooled
            return pooled
        width, height = 40, 20
        hint = node.prop("sizeHint")
        if hint is not None and isinstance(hint.value, SizeValue):
            width, height = hint.value.width, hint.value.height
        orient = ""
        prop = node.prop("orientation")
        if prop is not None and isinstance(prop.value, EnumValue):
            orient = prop.value.text
        grow = QSizePolicy_expanding()
        fixed = QSizePolicy_minimum()
        if "Vertical" in orient:
            item = QSpacerItem(width, height, fixed, grow)
        else:
            item = QSpacerItem(width, height, grow, fixed)
        self._spacers[node.id] = item
        return item

    def _sync_items(self, node: WidgetNode, widget: QWidget) -> None:
        items = node.children("items")
        if isinstance(widget, QComboBox):
            if not items and widget.count() == 0:
                return
            widget.clear()
            for item in items:
                widget.addItem(_node_text(item))
            return
        if isinstance(widget, QListWidget):
            widget.clear()
            for item in items:
                widget.addItem(_node_text(item))
            return
        if isinstance(widget, QTreeWidget):
            widget.clear()
            for item in items:
                widget.addTopLevelItem(_tree_item(item))
            return
        if isinstance(widget, QTableWidget):
            rows = node.children("rows")
            cols = node.children("columns")
            row_count = len(rows)
            col_count = len(cols)
            for item in items:
                row = item.field("row")
                column = item.field("column")
                if isinstance(row, int):
                    row_count = max(row_count, row + 1)
                if isinstance(column, int):
                    col_count = max(col_count, column + 1)
            if row_count:
                widget.setRowCount(row_count)
            if col_count:
                widget.setColumnCount(col_count)
            for index, header in enumerate(rows):
                widget.setVerticalHeaderItem(index, QTableWidgetItem(_node_text(header)))
            for index, header in enumerate(cols):
                widget.setHorizontalHeaderItem(index, QTableWidgetItem(_node_text(header)))
            for item in items:
                row = item.field("row") if isinstance(item.field("row"), int) else 0
                column = item.field("column") if isinstance(item.field("column"), int) else 0
                widget.setItem(row, column, QTableWidgetItem(_node_text(item)))

    def _apply_late(self, node: WidgetNode, widget: QWidget) -> None:
        current = node.prop("currentIndex")
        if current is not None and hasattr(widget, "setCurrentIndex"):
            apply_entry(widget, current, is_root=False, resolve_path=self._resolve_path, problems=self._problems)
        sizes = node.prop("cbcsSplitterSizes")
        if sizes is not None and isinstance(widget, QSplitter):
            values = splitter_sizes(sizes.value)
            if values:
                widget.setSizes(list(values))
        if node.child_widgets:
            self._restack(node.id)

    def _restack(self, parent_id: NodeId) -> None:
        widget = self._widgets.get(parent_id)
        if widget is None:
            return
        order = child_stack_order(self._session.document, parent_id)
        if not order:
            return
        by_name = {}
        for child in widget.findChildren(QWidget, options=_DIRECT):
            if child.objectName():
                by_name[child.objectName()] = child
        for name in order:
            child = by_name.get(name)
            if child is not None:
                child.raise_()

    def _detach_moved(self, node_id: NodeId) -> None:
        node = self._session.document.get(node_id)
        if isinstance(node, LayoutItemNode):
            content = node.content
            if content is not None:
                self._detach_moved(content.id)
            return
        widget = self._widgets.get(node_id)
        if isinstance(widget, QWidget):
            self._detach_widget(widget)
            self._pool[node_id] = widget
            return
        layout = self._layouts.get(node_id)
        if layout is not None:
            self._detach_layout(layout)
            self._release_layout(layout)
            self._pool[node_id] = layout

    def _release_layout(self, qlayout: QLayout) -> None:
        """Detach a layout so the next parent can adopt it.

        ``setParent(None)`` drops a layout from a parent layout. A widget keeps
        a stale ``layout()`` pointer, so that widget gets an empty stand-in
        first. The stand-in is deleted when the real layout is installed again.
        """
        if not wrapper_is_valid(qlayout):
            return
        parent = qlayout.parent()
        if parent is None:
            return
        qlayout.setParent(None)
        if isinstance(parent, QWidget) and wrapper_is_valid(parent) and parent.layout() is qlayout:
            parent.setLayout(QtWidgets.QVBoxLayout())

    def _reconcile_node(self, node_id: NodeId) -> None:
        doc = self._session.document
        node = doc.get(node_id)
        if node is None:
            return
        if isinstance(node, LayoutNode):
            self._fill_layout(node)
            self._reconciled += 1
            return
        if isinstance(node, LayoutItemNode) and node.parent_id is not None:
            self._reconcile_node(node.parent_id)
            return
        if isinstance(node, WidgetNode):
            widget = self._widgets.get(node.id)
            if widget is None:
                return
            self._park_children(node, widget)
            self._fill_widget(node, widget)
            self._reconciled += 1

    def _park_children(self, node: WidgetNode, widget: QWidget) -> None:
        """Detach this container's live children into the pool. The container stays."""
        kind = self._qt_class_name(node.class_name)
        if kind in _PAGE_CLASSES:
            self._drain_pages(widget)
            return
        if kind in ("QMainWindow", "QDockWidget") or kind in _MENU_CLASSES:
            self._park_known_children(node)
            self._park_direct(widget)
            return
        if isinstance(node.layout, LayoutNode):
            qlayout = self._layouts.get(node.layout.id)
            if qlayout is None and widget.layout() is not None:
                qlayout = widget.layout()
            if qlayout is not None:
                self._detach_layout(qlayout)
            return
        self._park_direct(widget)

    def _drain_pages(self, widget: QWidget) -> None:
        if isinstance(widget, QScrollArea):
            inner = widget.takeWidget()
            self._park_page(inner)
            return
        if isinstance(widget, QMdiArea):
            for sub in list(widget.subWindowList()):
                inner = sub.widget()
                self._park_page(inner)
                widget.removeSubWindow(sub)
                delete_now(sub)
            return
        if isinstance(widget, QTabWidget):
            while widget.count():
                self._park_page(widget.widget(0))
                widget.removeTab(0)
            return
        if isinstance(widget, QToolBox):
            while widget.count():
                self._park_page(widget.widget(0))
                widget.removeItem(0)
            return
        if isinstance(widget, QStackedWidget):
            while widget.count():
                page = widget.widget(0)
                widget.removeWidget(page)
                self._park_page(page)
            return
        if isinstance(widget, QWizard):
            for page_id in list(widget.pageIds()):
                self._park_page(widget.page(page_id))
                widget.removePage(page_id)
            return
        if isinstance(widget, QSplitter):
            pages = [widget.widget(index) for index in range(widget.count())]
            for page in pages:
                self._park_page(page)
            return

    def _park_page(self, widget: Optional[QWidget]) -> None:
        if widget is None:
            return
        node_id = _node_id(widget)
        widget.setParent(None)
        if node_id is not None:
            self._pool[node_id] = widget

    def _park_known_children(self, node: WidgetNode) -> None:
        for child in node.child_widgets:
            widget = self._widgets.get(child.id)
            if widget is None or child.id in self._pool:
                continue
            self._detach_widget(widget)
            self._pool[child.id] = widget

    def _park_direct(self, widget: QWidget) -> None:
        for child in list(widget.findChildren(QWidget, options=_DIRECT)):
            node_id = _node_id(child)
            if node_id is None or node_id in self._pool:
                continue
            if child is widget:
                continue
            self._detach_widget(child)
            self._pool[node_id] = child

    def _detach_widget(self, widget: QWidget) -> None:
        parent = widget.parentWidget()
        if isinstance(parent, QTabWidget):
            index = parent.indexOf(widget)
            if index >= 0:
                parent.removeTab(index)
        elif isinstance(parent, QToolBox):
            index = parent.indexOf(widget)
            if index >= 0:
                parent.removeItem(index)
        elif isinstance(parent, QStackedWidget):
            parent.removeWidget(widget)
        elif isinstance(parent, QWizard):
            for page_id in parent.pageIds():
                if parent.page(page_id) is widget:
                    parent.removePage(page_id)
                    break
        elif isinstance(parent, QScrollArea) and parent.widget() is widget:
            parent.takeWidget()
        elif isinstance(parent, QDockWidget) and parent.widget() is widget:
            widget.setParent(None)
        elif isinstance(parent, QMainWindow):
            widget.setParent(None)
        elif isinstance(parent, QMdiArea):
            sub = self._mdi.pop(_node_id(widget), None)
            if sub is not None:
                parent.removeSubWindow(sub)
                delete_now(sub)
        else:
            host = parent
            # A page inside a tab can be parented to the stack, not the tab widget.
            tab = _owning_tab(widget)
            if tab is not None:
                index = tab.indexOf(widget)
                if index >= 0:
                    tab.removeTab(index)
            elif host is not None and host.layout() is not None:
                host.layout().removeWidget(widget)
        widget.setParent(None)

    def _detach_layout(self, qlayout: QLayout) -> None:
        if isinstance(qlayout, QFormLayout):
            while qlayout.rowCount():
                taken = qlayout.takeRow(0)
                for item in (taken.labelItem, taken.fieldItem):
                    if item is not None:
                        self._pool_taken_item(item)
            return
        while qlayout.count():
            item = qlayout.takeAt(0)
            if item is None:
                break
            self._pool_taken_item(item)

    def _pool_taken_item(self, item: object) -> None:
        child = item.widget() if hasattr(item, "widget") else None
        nested = item.layout() if hasattr(item, "layout") else None
        if child is not None:
            node_id = _node_id(child)
            if node_id is not None:
                self._pool[node_id] = child
            child.setParent(None)
            return
        if nested is not None:
            node_id = _node_id(nested)
            self._release_layout(nested)
            if node_id is not None:
                self._pool[node_id] = nested
            return
        spacer_id = self._spacer_of(item)
        if spacer_id is not None:
            self._pool[spacer_id] = item

    def _drop_layout(self, widget: QWidget) -> None:
        """Remove a layout this realizer installed.

        QDialogButtonBox and a few other widgets own a layout we never
        created. Taking that layout and deleting it leaves a dangling
        pointer, and the next setStyle segfaults.
        """
        qlayout = widget.layout()
        if qlayout is None:
            return
        node_id = _node_id(qlayout)
        if node_id is None:
            return
        self._detach_layout(qlayout)
        self._forget_layout(node_id)
        _delete_layout(qlayout)

    def _forget_layout(self, node_id: NodeId) -> None:
        self._layouts.pop(node_id, None)
        self._objects.pop(node_id, None)

    def _spacer_of(self, item: object) -> Optional[NodeId]:
        for node_id, spacer in self._spacers.items():
            if spacer is item:
                return node_id
        return None

    def _morph_widget(self, node: WidgetNode) -> None:
        old = self._widgets.get(node.id)
        if old is None:
            self._create_widget(node, None)
            return
        parent = old.parentWidget()
        self._park_children(node, old)
        layout_node = node.layout
        if isinstance(layout_node, LayoutNode):
            self._forget_layout(layout_node.id)
        self._widgets.pop(node.id, None)
        self._objects.pop(node.id, None)
        new = self._construct(node, parent)
        _swap_widget(old, new)
        delete_now(old)
        self._widgets[node.id] = new
        self._objects[node.id] = new
        if self._root is old:
            self._root = new
        self._ensure_actions(node, new)
        self._fill_widget(node, new)

    def _morph_layout(self, node: LayoutNode) -> None:
        self._layouts.pop(node.id, None)
        self._fill_layout(node)

    def _actions_by_name(self) -> Dict[str, QAction]:
        found: Dict[str, QAction] = {}
        for action in self._actions.values():
            if isinstance(action, QAction) and action.objectName():
                found.setdefault(action.objectName(), action)
        return found

    def _clear_mdi(self, area: QMdiArea) -> None:
        for sub in list(area.subWindowList()):
            area.removeSubWindow(sub)
            delete_now(sub)
        self._mdi = {key: value for key, value in self._mdi.items() if value.parent() is not None}

    def _order_key(self, node_id: NodeId) -> Tuple[int, ...]:
        doc = self._session.document
        indexes: List[int] = []
        current: Optional[NodeId] = node_id
        seen = set()
        while current is not None and current not in seen:
            seen.add(current)
            node = doc.get(current)
            if node is None:
                break
            indexes.append(node.slot_index)
            current = node.parent_id
        indexes.reverse()
        return tuple(indexes)

    def _tag(self, obj: object, node_id: NodeId) -> None:
        obj.setProperty(NODE_ID_PROPERTY, int(node_id))  # type: ignore[attr-defined]

    def _apply_node_properties(self, node: object, obj: object, *, is_root: bool) -> None:
        for entry in node.properties():  # type: ignore[attr-defined]
            if apply_entry(obj, entry, is_root=is_root, resolve_path=self._resolve_path, problems=self._problems):
                self._patched += 1

    def _apply_stretches(self, node: LayoutNode, qlayout: QLayout) -> None:
        mapping = (
            ("stretch", "setStretch"),
            ("rowstretch", "setRowStretch"),
            ("columnstretch", "setColumnStretch"),
            ("rowminimumheight", "setRowMinimumHeight"),
            ("columnminimumwidth", "setColumnMinimumWidth"),
        )
        for field_name, method_name in mapping:
            raw = node.field(field_name)
            setter = getattr(qlayout, method_name, None)
            if not isinstance(raw, str) or setter is None:
                continue
            for index, piece in enumerate(part.strip() for part in raw.split(",")):
                if not piece:
                    continue
                try:
                    setter(index, int(piece))
                except (TypeError, ValueError):
                    continue


def _node_id(obj: object) -> Optional[NodeId]:
    if obj is None or not hasattr(obj, "property"):
        return None
    raw = obj.property(NODE_ID_PROPERTY)  # type: ignore[attr-defined]
    if raw is None or raw == "":
        return None
    try:
        return NodeId(int(raw))
    except (TypeError, ValueError):
        return None


def _page_title(node: WidgetNode) -> str:
    for name in ("title", "label"):
        text = _attr_text(node, name)
        if text:
            return text
    return ""


def _attr_text(node: WidgetNode, name: str) -> str:
    entry = node.attr(name)
    if entry is None:
        entry = node.prop(name)
    if entry is None:
        return ""
    return text_of(entry.value)


def _apply_page_attrs(tabs: QTabWidget, index: int, node: WidgetNode) -> None:
    icon = node.attr("icon")
    if icon is not None:
        qicon = to_qt(icon.value, lambda path: path)
        if isinstance(qicon, QIcon):
            tabs.setTabIcon(index, qicon)
    tip = _attr_text(node, "toolTip")
    if tip:
        tabs.setTabToolTip(index, tip)
    whats = _attr_text(node, "whatsThis")
    if whats:
        tabs.setTabWhatsThis(index, whats)


def _node_text(node: object) -> str:
    prop = node.prop("text") if hasattr(node, "prop") else None
    if prop is None:
        return ""
    return text_of(prop.value)


def _tree_item(node: object) -> object:
    item = QTreeWidgetItem([_node_text(node)])
    for child in node.children("subitems"):  # type: ignore[attr-defined]
        item.addChild(_tree_item(child))
    return item


def _form_order(node: LayoutNode) -> Tuple[LayoutItemNode, ...]:
    return tuple(sorted(node.items, key=lambda item: (item.row or 0, item.column or 0)))


def _form_role(item: LayoutItemNode) -> object:
    role_type = getattr(QFormLayout, "ItemRole", QFormLayout)
    colspan = item.colspan or 1
    column = item.column or 0
    if colspan > 1 or column >= 2:
        return getattr(role_type, "SpanningRole")
    if column == 1:
        return getattr(role_type, "FieldRole")
    return getattr(role_type, "LabelRole")


def _align(qlayout: QLayout, widget: QWidget, item: LayoutItemNode) -> None:
    if not item.alignment:
        return
    flag = resolve_enum(item.alignment)
    if flag is None:
        return
    try:
        qlayout.setAlignment(widget, flag)
    except (TypeError, AttributeError):
        return


def _owning_tab(widget: QWidget) -> Optional[QTabWidget]:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QTabWidget):
            return parent
        parent = parent.parentWidget()
    return None


def _swap_widget(old: QWidget, new: QWidget) -> None:
    parent = old.parentWidget()
    if parent is None:
        return
    layout = parent.layout()
    if layout is not None and layout.indexOf(old) >= 0:
        index = layout.indexOf(old)
        layout.removeWidget(old)
        if isinstance(layout, QGridLayout):
            row, column, rowspan, colspan = layout.getItemPosition(index)
            layout.addWidget(new, row, column, rowspan, colspan)
        elif isinstance(layout, QFormLayout):
            layout.insertRow(index, new)
        else:
            layout.insertWidget(index, new)
        return
    if isinstance(parent, QTabWidget):
        index = parent.indexOf(old)
        if index >= 0:
            title = parent.tabText(index)
            parent.removeTab(index)
            parent.insertTab(index, new, title)
            return
    new.setParent(parent)


def _delete_layout(qlayout: QLayout) -> None:
    holder = QWidget()
    holder.setLayout(qlayout)
    delete_now(holder)


def QSizePolicy_expanding() -> object:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(policy, "Expanding")


def QSizePolicy_minimum() -> object:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(policy, "Minimum")
