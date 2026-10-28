"""Container reconcile. Live widgets move through a pool keyed by node id.

Phase 1 detaches every moved object before any container is rebuilt. Phase 2
then walks dirty containers shallow-first, so a widget that moved into an
earlier container is already in the pool when that container asks for it.

The pool lives for one patch. A pooled widget that no container asked for is
one a fresh build would not create, and ``_sweep_pool`` deletes it. Layouts
never sit in the pool: ``_layouts`` names them, and a layout outside the live
tree is always empty (``slots.py``).
"""

from __future__ import annotations

import importlib
from functools import partial
from typing import Dict, List, Optional, Set, Tuple, Union

from app.qt import QtGui, QtWidgets
from app.qt.QtCore import QObject, Qt
from app.qt.QtGui import QAction, QActionGroup, QIcon
from app.qt.QtWidgets import (
    QMdiSubWindow,
    QComboBox,
    QDockWidget,
    QFrame,
    QGridLayout,
    QLabel,
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
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolBox,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
    QWizard,
    QWizardPage,
)
from app.qt.qt_compat import IS_QT6, delete_now, wrapper_is_valid
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
from app.features.form_builder.engine.logic.storage import splitter_sizes
from app.features.form_builder.engine.project.pictures import label_text_hides_picture
from app.features.form_builder.engine.ui4.values import EnumValue, SizeValue
from app.features.form_builder.qtside.realize.forced import CANVAS_OVERRIDES
from app.features.form_builder.qtside.realize.stand_in import StandInWidget, stand_in_name
from app.features.form_builder.qtside.realize.props import (
    apply_entry,
    apply_geometry,
    ordered_layout_metrics,
    text_of,
    to_qt,
)
from app.features.form_builder.qtside.realize.slots import (
    NODE_ID_PROPERTY,
    LayoutHints,
    _LayoutSlots,
    _form_role,  # noqa: F401  (kept importable from tree for existing scripts)
    _node_id,
    grid_extent as _grid_extent,
)

STAND_IN_PROPERTY = "_cbcsStandIn"

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
_GEOMETRY_PROPS = frozenset(
    {
        "geometry",
        "minimumSize",
        "maximumSize",
        "sizePolicy",
        "minimumWidth",
        "minimumHeight",
        "maximumWidth",
        "maximumHeight",
        "baseSize",
        "sizeIncrement",
    }
)
_DIRECT = Qt.FindDirectChildrenOnly


def _direct_widgets(widget: QWidget) -> List[QWidget]:
    """Direct QWidget children.

    PySide2 ``findChildren`` takes a type and an optional name. It has no
    ``FindChildOption`` argument, so the Qt6 ``options=`` keyword cannot be
    the shared call.
    """
    return [child for child in widget.children() if isinstance(child, QWidget)]


def _cpp_address(obj: object) -> int:
    """The C++ object's address. Stable where ``id()`` is not.

    A Qt-created object Python holds no wrapper for gets a new temporary
    wrapper from each ``topLevelWidgets`` call, so its ``id()`` changes.
    """
    shiboken = importlib.import_module("shiboken6" if IS_QT6 else "shiboken2")
    return int(shiboken.getCppPointer(obj)[0])


def _qt_places(widget: QWidget, parent: object) -> bool:
    """True when a layout sizes ``widget``: a layout item, or a host whose own
    layout places its content (a dock's widget, a main window's central widget)."""
    if isinstance(parent, LayoutItemNode):
        return True
    host = widget.parentWidget()
    return host is not None and host.layout() is not None


def _toplevel_menu_bar_ids() -> Set[int]:
    """C++ addresses of the parentless menu bars. Python ids change per call."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return set()
    return {
        _cpp_address(widget)
        for widget in app.topLevelWidgets()
        if isinstance(widget, QMenuBar) and wrapper_is_valid(widget)
    }


class _Structure(_LayoutSlots):
    """Methods mixed into ``Realizer``. Attributes live on the realizer."""

    def _qt_class_name(self, class_name: str) -> str:
        doc = self._session.document
        for node in doc.ui.children("customwidgets"):
            if isinstance(node, CustomWidgetNode) and node.class_name == class_name and node.extends:
                return node.extends.split("::")[-1]
        return class_name.split("::")[-1]

    def _widget_type(self, class_name: str) -> type:
        short = self._qt_class_name(class_name)
        # Designer stores a line as class ``Line`` and uic builds a QFrame.
        if short == "Line":
            return QFrame
        cls = getattr(QtWidgets, short, None)
        if cls is None:
            cls = getattr(QtGui, short, None)
        if cls is None or not isinstance(cls, type):
            self._problems.append("class %s is not a Qt widget; using QWidget" % class_name)
            return QWidget
        return cls

    def _construct(self, node: WidgetNode, parent: Optional[QWidget]) -> QWidget:
        friendly = stand_in_name(self._qt_class_name(node.class_name))
        if friendly is not None:
            # Never build these in the editor: no GL context, no QML engine (UX-CONT-017).
            cls: type = partial(StandInWidget, friendly=friendly)  # type: ignore[assignment]
        else:
            cls = self._widget_type(node.class_name)
        try:
            widget = cls(parent)
        except (TypeError, RuntimeError) as exc:
            self._problems.append("class %s: %s" % (node.class_name, exc))
            widget = QWidget(parent)
        self._tag(widget, node.id)
        widget.setObjectName(node.object_name)
        if node.class_name == "Line" and isinstance(widget, QFrame):
            widget.setProperty("_cbcs_line", True)
            shape = getattr(getattr(QFrame, "Shape", QFrame), "HLine")
            shadow = getattr(getattr(QFrame, "Shadow", QFrame), "Sunken")
            widget.setFrameShape(shape)
            widget.setFrameShadow(shadow)
        widget.setFocusPolicy(Qt.NoFocus)
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if isinstance(widget, QMenuBar):
            widget.setNativeMenuBar(False)
        self._widgets[node.id] = widget
        self._objects[node.id] = widget
        self._created += 1
        self._touched.add(node.id)
        self._fresh.add(node.id)
        is_root = parent is None and self._root is None
        self._apply_node_properties(node, widget, is_root=is_root or widget is self._root)
        if isinstance(widget, QWizard) and parent is not None:
            # A wizard is a dialog. Inside a form it has to be an ordinary child
            # or the canvas never sees it (UX-CONT-013).
            widget.setWindowFlag(Qt.Window, False)
            widget.setParent(parent)
            widget.setVisible(True)
        if parent is not None and parent.isVisible() and not isinstance(widget, QMenu):
            # Qt leaves a child hidden when it is created after its parent is shown.
            widget.show()
        return widget

    def _create_widget(self, node: WidgetNode, parent: Optional[QWidget]) -> QWidget:
        if parent is None and node is not self._session.document.root:
            # A container page (splitter, tab, stack, scroll area, MDI,
            # wizard) is inserted after it is built. Built parentless it is a
            # window, and a window's layout pins its minimum size (QStatusBar
            # does that in its constructor), which a patched copy never gets.
            parent = self._nursery()
        widget = self._construct(node, parent)
        self._ensure_actions(node, widget)
        self._fill_widget(node, widget)
        return widget

    def _obtain_widget(self, node: WidgetNode, parent: Optional[QWidget]) -> QWidget:
        self._touched.add(node.id)
        pooled = self._pool.pop(node.id, None)
        if isinstance(pooled, QWidget):
            if not wrapper_is_valid(pooled):
                self._wipe(node.id)
            else:
                # ``parent`` None means the container reparents on insert, so
                # a widget parked in place keeps its parent until then.
                if parent is not None and pooled.parentWidget() is not parent:
                    _reparent(pooled, parent)
                self._widgets[node.id] = pooled
                self._objects[node.id] = pooled
                self._apply_node_properties(node, pooled, is_root=pooled is self._root)
                if node.id in self._needs_fill:
                    # A morph's new widget is empty until something fills it.
                    # A parked widget keeps its subtree, so it is not refilled.
                    self._needs_fill.discard(node.id)
                    self._fill_widget(node, pooled)
                return pooled
        current = self._widgets.get(node.id)
        if isinstance(current, QWidget) and current is not pooled:
            if wrapper_is_valid(current):
                if parent is not None and current.parentWidget() is not parent:
                    _reparent(current, parent)
                return current
            self._wipe(node.id)
        return self._create_widget(node, parent)

    def _fill_widget(self, node: WidgetNode, widget: QWidget) -> None:
        self._ensure_actions(node, widget)
        kind = self._qt_class_name(node.class_name)
        before_bars: Set[int] = set()
        if kind == "QMainWindow" and isinstance(widget, QMainWindow):
            before_bars = _toplevel_menu_bar_ids()
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
        if kind == "QMainWindow" and isinstance(widget, QMainWindow):
            bar = widget.menuWidget()
            if isinstance(bar, QMenuBar):
                self._drop_replaced_chrome(None, bar, before_bars)

    def _note_managed_children(self, node: WidgetNode) -> None:
        layout = node.layout
        if not isinstance(layout, LayoutNode):
            return
        pending = [layout]
        while pending:
            current = pending.pop()
            for item in current.items:
                content = item.content
                if isinstance(content, WidgetNode):
                    self._geometry_targets.add(content.id)
                elif isinstance(content, LayoutNode):
                    pending.append(content)

    def _fill_loose(self, node: WidgetNode, widget: QWidget) -> None:
        for child in node.child_widgets:
            self._obtain_widget(child, widget)

    def _fill_pages(self, node: WidgetNode, widget: QWidget) -> None:
        if isinstance(widget, (QTabWidget, QToolBox, QStackedWidget)):
            self._sync_stack_pages(node, widget)
            return
        self._drain_pages(widget)
        children = node.child_widgets
        # Adding a pane shows it, and show() activates its layout, which moves
        # the widgets it manages off their document rects.
        for child_node in children:
            self._note_managed_children(child_node)
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
                if not isinstance(page, QWizardPage):
                    problem = "class %s is not a wizard page" % child_node.class_name
                    if problem not in self._problems:
                        self._problems.append(problem)
                    # A fresh build leaves it parentless. A page parked in
                    # place would otherwise stay under its old parent.
                    if page.parentWidget() is not None:
                        page.setParent(None)
                    continue
                title = _page_title(child_node)
                if title and hasattr(page, "setTitle"):
                    page.setTitle(title)
                widget.addPage(page)
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

    def _sync_stack_pages(self, node: WidgetNode, widget: QWidget) -> None:
        """Insert and remove only the pages that differ.

        Draining a tab widget hides and re-shows the current page, which walks
        its whole subtree. Pages the document keeps in order stay where they are.
        """
        children = node.child_widgets
        wanted = {child.id: self._widgets.get(child.id) for child in children}
        shown: Set[NodeId] = set()

        def note_current() -> None:
            current = widget.currentWidget()  # type: ignore[attr-defined]
            current_id = _node_id(current) if current is not None else None
            if current_id is not None:
                shown.add(current_id)

        for index in range(widget.count() - 1, -1, -1):  # type: ignore[attr-defined]
            page = widget.widget(index)  # type: ignore[attr-defined]
            page_id = _node_id(page)
            if page_id is not None and wanted.get(page_id) is page:
                continue
            _remove_stack_page(widget, index, page)
            if page_id is not None and wrapper_is_valid(page):
                self._hold_widget(page_id, page)
            note_current()
        kept = [_node_id(widget.widget(index)) for index in range(widget.count())]  # type: ignore[attr-defined]
        if kept != [child.id for child in children if child.id in set(kept)]:
            self._drain_pages(widget)
        position = 0
        for child_node in children:
            if position < widget.count() and _node_id(widget.widget(position)) == child_node.id:  # type: ignore[attr-defined]
                position += 1
                continue
            page = self._obtain_widget(child_node, None)
            title = _page_title(child_node)
            if isinstance(widget, QTabWidget):
                index = widget.insertTab(position, page, title)
                _apply_page_attrs(widget, index, child_node)
            elif isinstance(widget, QToolBox):
                index = widget.insertItem(position, page, title)
                tip = _attr_text(child_node, "toolTip")
                if tip:
                    widget.setItemToolTip(index, tip)
            else:
                widget.insertWidget(position, page)  # type: ignore[attr-defined]
            position += 1
            note_current()
        if node.prop("currentIndex") is None and widget.count() and widget.currentIndex() != 0:  # type: ignore[attr-defined]
            # A fresh build leaves the first page added current.
            widget.setCurrentIndex(0)  # type: ignore[attr-defined]
            note_current()
        current = _current_index(node)
        if 0 <= current < len(children):
            shown.add(children[current].id)
        document = self._session.document
        for page_id in shown:
            # Showing a page activates its layout, which moves the widgets it
            # manages off their document rects.
            page_node = document.get(page_id)
            if isinstance(page_node, WidgetNode):
                self._note_managed_children(page_node)

    def _fill_dock(self, node: WidgetNode, widget: QDockWidget) -> None:
        children = node.child_widgets
        if not children:
            return
        child = self._obtain_widget(children[0], None)
        current = widget.widget()
        if current is not None and current is not child:
            current_id = _node_id(current)
            current.setParent(None)
            if current_id is not None:
                self._hold_widget(current_id, current)
        widget.setWidget(child)

    def _fill_main_window(self, node: WidgetNode, widget: QMainWindow) -> None:
        """Install the chrome and the central widget. Parts already in place stay.

        A toolbar edit reconciles the window, and the central subtree is most
        of the form. Leaving installed parts alone keeps that edit O(chrome).
        """
        parts: List[Tuple[WidgetNode, str]] = []
        central = None
        for child in node.child_widgets:
            kind = self._qt_class_name(child.class_name)
            if kind in ("QMenuBar", "QStatusBar", "QToolBar", "QDockWidget", "QMenu"):
                parts.append((child, kind))
            elif central is None:
                central = child
                parts.append((child, "central"))
        installed = set()
        for child, role in parts:
            live = self._widgets.get(child.id)
            if isinstance(live, QWidget) and wrapper_is_valid(live) and _installed(widget, live, role):
                installed.add(child.id)
        for stale in _direct_widgets(widget):
            stale_id = _node_id(stale)
            if stale_id is None or stale_id in installed or stale is widget or stale_id in self._pool:
                continue
            self._detach_widget(stale)
            self._hold_widget(stale_id, stale)
        for child, role in parts:
            if child.id in installed:
                continue
            part = self._obtain_widget(child, widget)
            if role == "QMenuBar" and isinstance(part, QMenuBar):
                previous = widget.menuWidget()
                if previous is not part:
                    # Only the bar this call unparents is ours to delete. A
                    # parentless bar that already existed belongs to another window.
                    before = _toplevel_menu_bar_ids()
                    widget.setMenuBar(part)
                    self._drop_replaced_chrome(previous, part, before)
            elif role == "QStatusBar":
                widget.setStatusBar(part)
            elif role == "QToolBar" and isinstance(part, QToolBar):
                widget.addToolBar(part)
            elif role == "QDockWidget" and isinstance(part, QDockWidget):
                widget.addDockWidget(Qt.LeftDockWidgetArea, part)
            elif role == "central":
                widget.setCentralWidget(part)
            self._note_managed_children(child)
        self._fill_menu(node, widget)

    def _drop_replaced_chrome(
        self, previous: Optional[QWidget], installed: QWidget, before: Set[int]
    ) -> None:
        """Delete the untagged menu bar ``setMenuBar`` left without a parent.

        ``before`` is the top-level menu bars that existed before this call.
        A tagged bar is a document widget. It stays in the pool so the container
        that took it can install it again.
        """
        if previous is not None and previous is not installed and wrapper_is_valid(previous):
            node_id = _node_id(previous)
            if node_id is not None and previous.parent() is None:
                self._hold_widget(node_id, previous)
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            if not wrapper_is_valid(widget) or _cpp_address(widget) in before:
                continue
            if _cpp_address(widget) == _cpp_address(installed):
                continue
            if not isinstance(widget, QMenuBar) or _node_id(widget) is not None:
                continue
            delete_now(widget)

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
            if isinstance(child, ActionGroupNode):
                self._ensure_action_object(child, widget, QActionGroup)
        for child in node.children("actions"):
            if isinstance(child, ActionNode):
                self._ensure_action_object(child, widget, QAction)

    def _ensure_action_object(
        self,
        child: Union[ActionNode, ActionGroupNode],
        widget: QWidget,
        cls: type,
    ) -> None:
        existing = self._actions.get(child.id)
        if existing is not None:
            if wrapper_is_valid(existing):
                if self._pool.get(child.id) is existing:
                    del self._pool[child.id]
                if existing.parent() is not widget:
                    existing.setParent(widget)
                return
            self._wipe(child.id)
        created = cls(widget)
        created.setObjectName(child.name)  # type: ignore[attr-defined]
        self._tag(created, child.id)
        self._actions[child.id] = created
        self._objects[child.id] = created
        self._apply_node_properties(child, created, is_root=False)

    def _ensure_layout(self, node: LayoutNode, host: Optional[QWidget]) -> QLayout:
        existing = self._layouts.get(node.id)
        short = self._qt_class_name(node.class_name)
        if existing is not None and type(existing).__name__ == short and wrapper_is_valid(existing):
            if host is not None and host.layout() is not existing:
                self._release_layout(existing)
                if not wrapper_is_valid(existing):
                    existing = None
                else:
                    self._install_on_host(host, existing)
                    return existing
            else:
                return existing
        if existing is not None and wrapper_is_valid(existing):
            self._delete_layout_object(existing)
        elif existing is not None:
            self._forget_layout(node.id)
        cls = getattr(QtWidgets, short, QtWidgets.QVBoxLayout)
        qlayout = cls()
        if host is not None:
            self._install_on_host(host, qlayout)
        qlayout.setObjectName(node.object_name)
        self._tag(qlayout, node.id)
        self._layouts[node.id] = qlayout
        self._objects[node.id] = qlayout
        self._apply_node_properties(node, qlayout, is_root=False)
        return qlayout

    def _spacer(self, node: SpacerNode) -> object:
        pooled = self._pool.pop(node.id, None)
        if isinstance(pooled, QSpacerItem):
            self._remember_spacer(node.id, pooled)
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
        self._remember_spacer(node.id, item)
        return item

    def _remember_spacer(self, node_id: NodeId, item: object) -> None:
        previous = self._spacers.get(node_id)
        if previous is not None and previous is not item:
            self._spacer_ids.pop(id(previous), None)
        self._spacers[node_id] = item
        self._spacer_ids[id(item)] = node_id

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
            apply_entry(
                widget,
                current,
                is_root=False,
                resolve_path=self._resolve_path,
                problems=self._problems,
                refusals=self._refusals,
            )
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
        for child in _direct_widgets(widget):
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
            # Reconcile runs before destroy, so the old host is still alive
            # when the new container takes the widget back.
            self._detach_widget(widget, unparent=False)
            self._hold_widget(node_id, widget)
            return
        layout = self._layouts.get(node_id)
        if layout is not None and wrapper_is_valid(layout):
            self._detach_layout(layout)
            self._release_layout(layout)
            return
        spacer = self._spacers.get(node_id)
        if spacer is not None and self._take_from_slot(node_id, spacer):
            self._pool[node_id] = spacer

    def _release_layout(self, qlayout: QLayout) -> None:
        """Unparent a nested layout. Delete a layout a widget owns.

        ``setParent(None)`` on a widget's layout leaves ``layout()`` dangling,
        and the next ``setLayout`` segfaults. Deleting that layout through a
        temporary holder clears the pointer. A nested layout is taken out of
        its parent layout first, so the parent never keeps an item for it.
        """
        if not wrapper_is_valid(qlayout):
            return
        parent = qlayout.parent()
        if parent is None:
            return
        if isinstance(parent, QWidget) and wrapper_is_valid(parent) and parent.layout() is qlayout:
            # Keeping this object would leave a holder with a stale layout
            # pointer, and destroying that holder at shutdown segfaults.
            self._delete_layout_object(qlayout)
            return
        node_id = _node_id(qlayout)
        taken = node_id is not None and self._take_from_slot(node_id, qlayout)
        if not taken and isinstance(parent, QLayout) and wrapper_is_valid(parent):
            parent.removeItem(qlayout)
        if wrapper_is_valid(qlayout) and qlayout.parent() is not None:
            qlayout.setParent(None)

    def _delete_layout_object(self, qlayout: QLayout) -> None:
        """Delete a layout after clearing the widget pointer that would dangle."""
        if not wrapper_is_valid(qlayout):
            return
        node_id = None if _is_stand_in(qlayout) else _node_id(qlayout)
        if node_id is not None:
            self._detach_layout(qlayout)
            self._settle_descendants(qlayout, replacing=node_id)
        if not wrapper_is_valid(qlayout):
            if node_id is not None:
                self._forget_layout(node_id)
            return
        parent = qlayout.parent()
        if isinstance(parent, QWidget) and wrapper_is_valid(parent) and parent.layout() is qlayout:
            holder = QWidget()
            holder.setLayout(qlayout)
            delete_now(holder)
        else:
            if node_id is not None:
                self._take_from_slot(node_id, qlayout)
            if wrapper_is_valid(qlayout) and isinstance(qlayout.parent(), QLayout):
                qlayout.parent().removeItem(qlayout)
            if wrapper_is_valid(qlayout):
                qlayout.setParent(None)
                delete_now(qlayout)
        if node_id is not None:
            self._forget_layout(node_id)

    def _reconcile_node(self, node_id: NodeId) -> None:
        doc = self._session.document
        node = doc.get(node_id)
        if node is None:
            return
        if isinstance(node, LayoutNode):
            owner_id = node.owner_widget_id()
            if owner_id is None:
                live = self._layouts.get(node.id)
                if live is None or not wrapper_is_valid(live) or live.parent() is None:
                    # A nested layout outside the tree. Its parent layout fills
                    # it when it places it, and an unplaced one stays empty.
                    return
            elif owner_id not in self._widgets:
                # The owner is pooled or not realized. Filling the layout now
                # would leave a hostless layout holding items. The owner's
                # fill installs and fills it when a container takes it back.
                return
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
            kind = self._qt_class_name(node.class_name)
            # A layout reconciles by difference and a main window keeps parts
            # already in place. Everything else parks its children first.
            keeps_children = (
                isinstance(node.layout, LayoutNode)
                or (kind == "QMainWindow" and isinstance(widget, QMainWindow))
                or isinstance(widget, (QTabWidget, QToolBox, QStackedWidget))
            )
            if not keeps_children:
                self._park_children(node, widget)
            self._geometry_targets.add(node.id)
            for child in node.child_widgets:
                self._geometry_targets.add(child.id)
            self._fill_widget(node, widget)
            self._reconciled += 1

    def _target_laid_out_rects(self) -> None:
        """Write again every stored rect that a layout places.

        Any patch can re-run a layout (items moved in or out, a page shown,
        a host re-inserted), which moves its widgets off their stored rects.
        A fresh build writes every stored rect last. Designer writes no rect
        for a laid-out widget, so this set is small.
        """
        document = self._session.document
        for node_id in tuple(self._laid_out_rects):
            if document.contains(node_id):
                self._geometry_targets.add(node_id)
            else:
                self._laid_out_rects.discard(node_id)

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
            if qlayout is not None and wrapper_is_valid(qlayout):
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
                if isinstance(inner, QWidget) and wrapper_is_valid(inner):
                    self._retire_subwindow(widget, sub, inner)
                    self._park_page(inner)
                elif wrapper_is_valid(sub):
                    widget.removeSubWindow(sub)
                    sub.setParent(None)
                    sub.hide()
                    self._retired_windows.append(sub)
            return
        # Pages come off the end so the current page changes only once, and
        # they stay parented: the container takes them back in the same window.
        if isinstance(widget, QTabWidget):
            while widget.count():
                last = widget.count() - 1
                self._park_page(widget.widget(last), keep_parent=True)
                widget.removeTab(last)
            return
        if isinstance(widget, QToolBox):
            while widget.count():
                last = widget.count() - 1
                self._park_page(widget.widget(last), keep_parent=True)
                widget.removeItem(last)
            return
        if isinstance(widget, QStackedWidget):
            while widget.count():
                page = widget.widget(widget.count() - 1)
                widget.removeWidget(page)
                self._park_page(page, keep_parent=True)
            return
        if isinstance(widget, QWizard):
            for page_id in list(widget.pageIds()):
                self._park_page(widget.page(page_id), keep_parent=True)
                widget.removePage(page_id)
            return
        if isinstance(widget, QSplitter):
            # addWidget moves a pane that is already in the splitter.
            pages = [widget.widget(index) for index in range(widget.count())]
            for page in pages:
                self._park_page(page, keep_parent=True)
            return

    def _park_page(self, widget: Optional[QWidget], *, keep_parent: bool = False) -> None:
        if widget is None:
            return
        node_id = _node_id(widget)
        if not keep_parent:
            widget.setParent(None)
        if node_id is not None:
            self._hold_widget(node_id, widget)

    def _park_known_children(self, node: WidgetNode) -> None:
        for child in node.child_widgets:
            widget = self._widgets.get(child.id)
            if widget is None or child.id in self._pool:
                continue
            self._detach_widget(widget)
            self._hold_widget(child.id, widget)

    def _park_direct(self, widget: QWidget) -> None:
        for child in _direct_widgets(widget):
            node_id = _node_id(child)
            if node_id is None or node_id in self._pool:
                continue
            if child is widget:
                continue
            self._detach_widget(child, unparent=False)
            self._hold_widget(node_id, child)

    def _detach_widget(self, widget: QWidget, *, unparent: bool = True) -> None:
        """Take ``widget`` out of its container.

        ``unparent=False`` keeps a layout item's widget under its old host. A
        move uses that: the new container reparents it within the same window,
        which skips the focus-chain walk Qt does when a widget leaves a window.
        """
        node_id = _node_id(widget)
        if node_id is not None and self._take_from_slot(node_id, widget):
            if unparent:
                widget.setParent(None)
            return
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
            if sub is not None and wrapper_is_valid(sub):
                self._retire_subwindow(parent, sub, widget)
                return
        elif isinstance(parent, QMdiSubWindow):
            self._retire_subwindow(parent.mdiArea(), parent, widget)
            return
        else:
            host = parent
            # A page's parentWidget() is the container's internal stack, frame
            # or viewport, not the container the document names.
            tab = _owning_tab(widget)
            box = _owning_toolbox(widget)
            wizard = _owning_wizard(widget)
            removed = False
            if tab is not None and tab.indexOf(widget) >= 0:
                tab.removeTab(tab.indexOf(widget))
                removed = True
            elif box is not None and box.indexOf(widget) >= 0:
                box.removeItem(box.indexOf(widget))
                removed = True
            elif wizard is not None and _wizard_has_page(wizard, widget):
                _remove_wizard_page(wizard, widget)
                removed = True
            host_layout = host.layout() if host is not None else None
            if not removed and host_layout is not None and wrapper_is_valid(host_layout) and not self._mirrors_without(host_layout):
                host_layout.removeWidget(widget)
        if unparent:
            widget.setParent(None)

    def _mirrors_without(self, qlayout: QLayout) -> bool:
        """True when ``qlayout`` is ours and its trusted mirror says it holds only
        what ``_slot_of`` names, so a widget missing there is not in it."""
        layout_id = _node_id(qlayout)
        mirror = None if layout_id is None else self._mirror(layout_id, qlayout)
        # removeWidget also searches nested layouts, so those must be absent.
        return mirror is not None and mirror.nested == 0

    def _drop_layout(self, widget: QWidget) -> None:
        """Remove a layout this realizer installed, including a tagged stand-in.

        QDialogButtonBox and a few other widgets own a layout we never
        created. That layout is untagged and not a stand-in, so it stays.
        Deleting it leaves a dangling pointer, and the next setStyle segfaults.
        """
        qlayout = widget.layout()
        if qlayout is None or not wrapper_is_valid(qlayout):
            return
        stand_in = _is_stand_in(qlayout)
        node_id = None if stand_in else _node_id(qlayout)
        if node_id is None and not stand_in:
            return
        self._delete_layout_object(qlayout)

    def _install_on_host(self, host: QWidget, qlayout: QLayout) -> bool:
        """Install ``qlayout`` only after the previous layout was deleted.

        Do not read ``host.layout()`` after that delete. The C++ pointer dangles
        until ``setLayout`` replaces it.
        """
        if not wrapper_is_valid(host) or not wrapper_is_valid(qlayout):
            return False
        existing = host.layout()
        if existing is qlayout:
            return True
        if existing is not None:
            if not _is_stand_in(existing) and _node_id(existing) is None:
                problem = "class %s keeps its own layout; the document layout was not installed" % type(host).__name__
                if problem not in self._problems:
                    self._problems.append(problem)
                return False
            self._drop_layout(host)
        host.setLayout(qlayout)
        return True

    def _forget_layout(self, node_id: NodeId) -> None:
        self._forget_slots(node_id)
        self._layouts.pop(node_id, None)
        self._objects.pop(node_id, None)
        self._pool.pop(node_id, None)

    def _morph_widget(self, node: WidgetNode) -> None:
        """Replace the live widget.

        A widget in a realized layout swaps in place through
        ``QLayout.replaceWidget``, which keeps the grid cell, form role or box
        index and leaves the layout untouched. Any other widget goes to the
        pool, and its parent container is queued so ``_reconcile_node``
        installs it.
        """
        old = self._widgets.get(node.id)
        was_root = self._root is old
        if old is None or not wrapper_is_valid(old):
            self._widgets.pop(node.id, None)
            self._objects.pop(node.id, None)
            self._discard_pooled(node.id)
            if was_root:
                self._root = None
            becomes_root = was_root or self._root is None and node.parent_id is None
            created = self._construct(node, None if becomes_root else self._nursery())
            self._adopt_morphed(node, created, was_root=becomes_root)
            self._remember_morph_buddies(node)
            return
        self._park_children(node, old)
        self._settle_descendants(old, replacing=node.id)
        self._widgets.pop(node.id, None)
        self._objects.pop(node.id, None)
        self._pool.pop(node.id, None)
        if was_root:
            self._root = None
        host = None if was_root else self._swap_host(node.id, old)
        created = self._construct(node, None if was_root else host or self._nursery())
        swapped = host is not None and self._swap_in_layout(node.id, old, created)
        if not swapped:
            self._detach_widget(old)
        if wrapper_is_valid(old):
            # A swapped-out widget is already out of its layout. Deleting it
            # under its host skips the focus-chain walk of leaving the window.
            delete_now(old)
        if swapped:
            self._pending_containers.add(node.id)
        else:
            self._adopt_morphed(node, created, was_root=was_root)
        self._remember_morph_buddies(node)

    def _nursery(self) -> QWidget:
        """A hidden parent for a morph's new widget until a container takes it.

        A parentless widget is a window, and a window's layout pins its minimum
        size when it activates (QStatusBar does that on construction). Neither
        a build nor a patch makes a form part a window, even for a moment.
        """
        nursery = self._nursery_widget
        if nursery is None or not wrapper_is_valid(nursery):
            nursery = QWidget()
            nursery.setObjectName("_cbcsNursery")
            self._nursery_widget = nursery
        return nursery

    def _swap_host(self, node_id: NodeId, old: QWidget) -> Optional[QWidget]:
        """The host widget when ``old`` sits in a realized layout, else None."""
        layout_id = self._slot_of.get(node_id)
        qlayout = None if layout_id is None else self._layouts.get(layout_id)
        mirror = None if qlayout is None or layout_id is None else self._mirror(layout_id, qlayout)
        if mirror is None or qlayout is None:
            return None
        index = mirror.find(node_id)
        if index < 0 or mirror.objects[index] is not old:
            return None
        return qlayout.parentWidget()

    def _swap_in_layout(self, node_id: NodeId, old: QWidget, created: QWidget) -> bool:
        layout_id = self._slot_of.get(node_id)
        qlayout = None if layout_id is None else self._layouts.get(layout_id)
        mirror = None if qlayout is None or layout_id is None else self._mirror(layout_id, qlayout)
        if mirror is None or qlayout is None:
            return False
        index = mirror.find(node_id)
        if index < 0 or mirror.objects[index] is not old:
            return False
        if qlayout.replaceWidget(old, created, _DIRECT) is None:
            return False
        mirror.objects[index] = created
        return True

    def _adopt_morphed(self, node: WidgetNode, created: QWidget, *, was_root: bool) -> None:
        if was_root:
            self._root = created
            self._fill_widget(node, created)
            return
        # A main-window child that is no longer a toolbar, dock or menu is not
        # created on a fresh build. Leave the new object in the pool so it
        # becomes visible only when a container asks for it.
        self._widgets.pop(node.id, None)
        self._objects.pop(node.id, None)
        self._discard_pooled(node.id)
        self._pool[node.id] = created
        self._needs_fill.add(node.id)
        self._queue_widget_host(node)
        self._pending_containers.add(node.id)

    def _hold_widget(self, node_id: NodeId, widget: QWidget) -> None:
        """Park a widget until a container asks for it during this patch.

        Its subtree stays inside it. ``_sweep_pool`` deletes a widget no
        container asked for, since a fresh build would not create it either.
        """
        prior = self._pool.get(node_id)
        if prior is not None and prior is not widget and isinstance(prior, QWidget):
            if self._widgets.get(node_id) is widget or not wrapper_is_valid(prior):
                self._pool.pop(node_id, None)
                self._delete_widget(prior)
            else:
                # ``widget`` is a stale object for this id. The pooled one wins.
                self._delete_widget(widget)
                return
        self._pool[node_id] = widget
        self._widgets.pop(node_id, None)
        if self._objects.get(node_id) is widget:
            self._objects.pop(node_id, None)

    def _discard_pooled(self, node_id: NodeId) -> None:
        discarded = self._pool.pop(node_id, None)
        if isinstance(discarded, QWidget):
            self._delete_widget(discarded)
        elif discarded is not None and isinstance(discarded, QObject) and wrapper_is_valid(discarded):
            delete_now(discarded)

    def _delete_widget(self, widget: QWidget) -> None:
        """Delete a widget nothing else names.

        Map entries for it and its tagged descendants go first, and it leaves
        any realized layout through its mirror, so no layout item outlives it.
        """
        if not wrapper_is_valid(widget):
            return
        self._wipe_objects_under(widget)
        # Delete in place: leaving the window first costs a focus-chain walk.
        self._detach_widget(widget, unparent=False)
        if wrapper_is_valid(widget):
            delete_now(widget)

    def _wipe_objects_under(self, root: QObject) -> None:
        """Drop map entries that point at ``root`` or a tagged descendant."""
        objects = [root]
        if hasattr(root, "findChildren"):
            objects.extend(root.findChildren(QObject))
        for obj in objects:
            node_id = _node_id(obj)
            if node_id is None:
                continue
            for table in (self._widgets, self._layouts, self._actions, self._objects):
                if table.get(node_id) is obj:
                    del table[node_id]
            if isinstance(obj, QLayout):
                self._forget_slots(node_id)
            if self._pool.get(node_id) is obj:
                del self._pool[node_id]

    def _sweep_pool(self) -> None:
        """Delete what this patch pooled and no container took back."""
        while self._pool:
            node_id, obj = self._pool.popitem()
            if isinstance(obj, QWidget):
                if self._widgets.get(node_id) is obj:
                    continue
                self._delete_widget(obj)
            elif isinstance(obj, QObject):
                if self._actions.get(node_id) is obj and obj.parent() is not None:
                    continue
                if wrapper_is_valid(obj):
                    self._wipe_objects_under(obj)
                    delete_now(obj)
            elif self._spacers.get(node_id) is obj:
                # A spacer nothing placed again. The wrapper owns it now.
                self._spacers.pop(node_id, None)
                self._spacer_ids.pop(id(obj), None)

    def _drop_oversized_grid(self, node: LayoutNode) -> List[Tuple[Optional[NodeId], object]]:
        """QGridLayout.rowCount never shrinks. A fresh layout does.

        The items come out first and stay parented to the host, so the fresh
        grid takes them back without a reparent.
        """
        existing = self._layouts.get(node.id)
        if not isinstance(existing, QGridLayout) or not wrapper_is_valid(existing):
            return []
        rows, columns = _grid_extent(node)
        if existing.rowCount() <= rows and existing.columnCount() <= columns:
            return []
        nested = isinstance(existing.parent(), QLayout)
        taken = self._take_all(node.id, existing)
        self._delete_layout_object(existing)
        # The new grid is created unparented. The layout that contained this
        # one has to run again, or the nested grid stays out of the tree.
        if nested:
            self._requeue_host_of(node)
        return taken

    def _reapply_document_geometry(self, targets: Optional[Set[NodeId]] = None) -> None:
        """Write the document rect again after Qt has inserted the widget.

        A fresh build applies geometry before ``addTab`` or ``addWidget``, and
        those calls replace it. A patch applies geometry after the widget is
        already in place, so Qt does not get a second chance. Doing this last
        on both paths leaves the live rect equal to the document. ``build``
        passes no targets. A patch passes the widgets it placed, the children
        of the containers it reconciled and the owners of geometry edits.
        """
        document = self._session.document
        if targets is None:
            self._laid_out_rects.clear()
            nodes = (node for node in document.iter_preorder() if isinstance(node, WidgetNode))
        else:
            nodes = (document.get(node_id) for node_id in targets)
        for node in nodes:
            if not isinstance(node, WidgetNode):
                continue
            entry = node.prop("geometry")
            if entry is None:
                self._laid_out_rects.discard(node.id)
                continue
            widget = self._widgets.get(node.id)
            if not isinstance(widget, QWidget) or not wrapper_is_valid(widget):
                self._laid_out_rects.discard(node.id)
                continue
            if _qt_places(widget, document.parent(node.id)):
                self._laid_out_rects.add(node.id)
            else:
                self._laid_out_rects.discard(node.id)
            apply_geometry(widget, entry.value, widget is self._root)

    def _queue_widget_host(self, node: WidgetNode) -> None:
        parent_id = node.parent_id
        if parent_id is None:
            return
        parent = self._session.document.get(parent_id)
        if isinstance(parent, LayoutItemNode):
            self._requeue_host_of(node)
            return
        self._pending_containers.add(parent_id)

    def _requeue_host_of(self, node: object) -> None:
        """Reconcile the layout whose item holds ``node``, hinting that item.

        A layout already filled in this patch runs again only for its hints.
        """
        parent_id = getattr(node, "parent_id", None)
        item = self._session.document.get(parent_id) if parent_id is not None else None
        if not isinstance(item, LayoutItemNode) or item.parent_id is None:
            return
        hints = self._layout_hints.get(item.parent_id)
        if hints is None:
            hints = self._layout_hints[item.parent_id] = LayoutHints()
        hints.items.add(item.id)
        self._pending_containers.add(item.parent_id)

    def _remember_morph_buddies(self, node: WidgetNode) -> None:
        self._morph_buddies.add(node.id)
        for user_id in self._buddy_users.get(node.object_name, ()):
            self._morph_buddies.add(user_id)

    def _morph_layout(self, node: LayoutNode) -> None:
        """Drop the old layout object, then reconcile whoever installs the new one."""
        old = self._layouts.get(node.id)
        if old is not None and wrapper_is_valid(old):
            self._delete_layout_object(old)
        else:
            self._forget_layout(node.id)
        if node.owner_widget_id() is not None:
            self._pending_containers.add(node.id)
            return
        self._requeue_host_of(node)

    def _settle_descendants(self, root_obj: object, *, replacing: NodeId) -> None:
        """Pool the tagged children the document still has. Delete the ones that die.

        Shallow first: a kept object takes its own subtree along, so nothing
        under it is taken apart. A dead object is deleted wherever it sits.
        """
        if not wrapper_is_valid(root_obj) or not hasattr(root_obj, "findChildren"):
            return
        children = [
            child
            for child in root_obj.findChildren(QObject)  # type: ignore[attr-defined]
            if wrapper_is_valid(child) and _node_id(child) is not None
        ]
        children.sort(key=self._object_depth)
        document = self._session.document
        for child in children:
            if not wrapper_is_valid(child):
                continue
            node_id = _node_id(child)
            if node_id is None or node_id == replacing:
                continue
            if not document.contains(node_id):
                self._wipe(node_id)
                self._delete_dead(child)
                continue
            if not _under(child, root_obj):
                continue
            if isinstance(child, QLayout):
                # Layouts are not pooled. ``_layouts`` keeps the object, emptied.
                self._detach_layout(child)
                self._release_layout(child)
                continue
            self._rehome(child)
            if not wrapper_is_valid(child):
                continue
            if isinstance(child, QWidget):
                self._hold_widget(node_id, child)
            else:
                self._pool[node_id] = child

    def _delete_dead(self, obj: object) -> None:
        if isinstance(obj, QWidget):
            self._delete_widget(obj)
        elif isinstance(obj, QLayout):
            self._delete_layout_object(obj)
        elif wrapper_is_valid(obj):
            obj.setParent(None)  # type: ignore[attr-defined]
            delete_now(obj)

    def _rehome(self, obj: object) -> None:
        if isinstance(obj, QWidget):
            self._detach_widget(obj)
            return
        if isinstance(obj, QLayout):
            self._release_layout(obj)
            return
        if hasattr(obj, "setParent"):
            obj.setParent(None)  # type: ignore[attr-defined]

    def _object_depth(self, obj: object) -> int:
        depth = 0
        current = obj
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            depth += 1
            parent = current.parent() if hasattr(current, "parent") else None
            current = parent
        return depth

    def _actions_by_name(self) -> Dict[str, QAction]:
        found: Dict[str, QAction] = {}
        for action in self._actions.values():
            if isinstance(action, QAction) and action.objectName():
                found.setdefault(action.objectName(), action)
        return found

    def _retire_subwindow(self, area: Optional[QMdiArea], sub: QWidget, widget: QWidget) -> None:
        """Take ``sub`` off ``area`` without deleting the page it was showing."""
        if hasattr(sub, "setWidget"):
            sub.setWidget(None)
        widget.setParent(self._nursery())
        if area is not None and wrapper_is_valid(area):
            area.removeSubWindow(sub)
        sub.setParent(None)
        sub.hide()
        self._retired_windows.append(sub)

    def _clear_mdi(self, area: QMdiArea) -> None:
        """Drop the subwindows. The page widgets stay alive under the nursery.

        Deleting a subwindow deletes the widget it still holds. The next fill
        would then use a freed wrapper and disposing the form crashes.
        """
        for sub in list(area.subWindowList()):
            if not wrapper_is_valid(sub):
                continue
            inner = sub.widget() if hasattr(sub, "widget") else None
            if isinstance(inner, QWidget) and wrapper_is_valid(inner):
                self._retire_subwindow(area, sub, inner)
            else:
                area.removeSubWindow(sub)
                sub.setParent(None)
                sub.hide()
                self._retired_windows.append(sub)
        self._mdi = {}

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

    def _apply_entry(self, obj: object, entry: object, is_root: bool) -> bool:
        return apply_entry(
            obj,
            entry,  # type: ignore[arg-type]
            is_root=is_root,
            resolve_path=self._resolve_path,
            problems=self._problems,
            refusals=self._refusals,
        )

    def _apply_node_properties(self, node: object, obj: object, *, is_root: bool) -> None:
        entries = list(node.properties())  # type: ignore[attr-defined]
        deferred = ordered_layout_metrics(entries) if isinstance(node, LayoutNode) else ()
        skip = {entry.name for entry in deferred}
        for entry in entries:
            if entry.name in skip:
                continue
            if self._apply_entry(obj, entry, is_root):
                self._patched += 1
        # QLabel text and pixmap clear each other. Generated code sets a
        # translatable text last (retranslateUi), so the canvas does too.
        if isinstance(obj, QLabel) and label_text_hides_picture(node):
            text = node.prop("text")  # type: ignore[attr-defined]
            if text is not None and self._apply_entry(obj, text, is_root):
                self._patched += 1
        for entry in deferred:
            if self._apply_entry(obj, entry, is_root):
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


def _remove_stack_page(widget: QWidget, index: int, page: QWidget) -> None:
    if isinstance(widget, QTabWidget):
        widget.removeTab(index)
    elif isinstance(widget, QToolBox):
        widget.removeItem(index)
    elif isinstance(widget, QStackedWidget):
        widget.removeWidget(page)


def _current_index(node: WidgetNode) -> int:
    entry = node.prop("currentIndex")
    value = getattr(entry.value, "value", None) if entry is not None else None
    return value if isinstance(value, int) else 0


def _under(obj: object, root: object) -> bool:
    current = obj.parent() if hasattr(obj, "parent") else None  # type: ignore[attr-defined]
    seen = set()
    while current is not None and id(current) not in seen:
        if current is root:
            return True
        seen.add(id(current))
        current = current.parent() if hasattr(current, "parent") else None
    return False


def _installed(window: QMainWindow, part: QWidget, role: str) -> bool:
    """Whether ``part`` already fills ``role`` on ``window``.

    The status bar, toolbars, docks and loose menus have no getter that does
    not create one, so being the window's child of the right class counts.
    """
    if role == "central":
        return window.centralWidget() is part
    if role == "QMenuBar":
        return window.menuWidget() is part
    kinds = {"QStatusBar": QStatusBar, "QToolBar": QToolBar, "QDockWidget": QDockWidget, "QMenu": QMenu}
    return part.parentWidget() is window and isinstance(part, kinds[role])


def _owning_tab(widget: QWidget) -> Optional[QTabWidget]:
    return _owning(widget, QTabWidget)


def _owning_toolbox(widget: QWidget) -> Optional[QToolBox]:
    return _owning(widget, QToolBox)


def _owning_wizard(widget: QWidget) -> Optional[QWizard]:
    return _owning(widget, QWizard)


def _owning(widget: QWidget, kind: type) -> Optional[QWidget]:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, kind):
            return parent
        parent = parent.parentWidget()
    return None


def _wizard_has_page(wizard: QWizard, widget: QWidget) -> bool:
    for page_id in wizard.pageIds():
        if wizard.page(page_id) is widget:
            return True
    return False


def _remove_wizard_page(wizard: QWizard, widget: QWidget) -> None:
    for page_id in list(wizard.pageIds()):
        if wizard.page(page_id) is widget:
            wizard.removePage(page_id)
            return


def _is_stand_in(qlayout: QLayout) -> bool:
    if not wrapper_is_valid(qlayout):
        return False
    return bool(qlayout.property(STAND_IN_PROPERTY))


def QSizePolicy_expanding() -> object:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(policy, "Expanding")


def QSizePolicy_minimum() -> object:
    policy = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(policy, "Minimum")


def _reparent(widget: QWidget, parent: QWidget) -> None:
    """Move ``widget`` under ``parent``. A menu stays a popup window.

    ``setParent(parent)`` resets the window flags, so a moved QMenu would turn
    into an inline child widget while a fresh build keeps it a popup.
    """
    if isinstance(widget, QMenu):
        widget.setParent(parent, widget.windowFlags() | Qt.Popup)
        return
    if isinstance(widget, QWizard):
        widget.setWindowFlag(Qt.Window, False)
    widget.setParent(parent)
    if isinstance(widget, QWizard) and parent.isVisible():
        widget.show()
