"""Build real PySide6 widgets from the form model."""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtWidgets import QSizePolicy, QWidget

from spikes.form_builder.model import (
    Action,
    Attribute,
    ItemEntry,
    Layout,
    LayoutItem,
    Property,
    Spacer,
    Widget,
    XmlNode,
    attributes_of,
    child_widgets,
    connections_of,
    get_property,
    item_content,
    iter_widgets,
    layout_items,
    locate,
    properties_of,
    tabstops_of,
    widget_layout,
)


class InputFilter(QObject):
    """Swallow real input so canvas widgets do not run their own behavior."""

    def eventFilter(self, watched, event):
        if event.type() in {
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
            QEvent.MouseButtonDblClick,
            QEvent.MouseMove,
            QEvent.Wheel,
            QEvent.KeyPress,
            QEvent.KeyRelease,
            QEvent.ContextMenu,
            QEvent.FocusIn,
            QEvent.Enter,
        }:
            return True
        return False


def custom_base(doc, class_name: str) -> str:
    pools = list(doc.header) + list(doc.footer)
    for part in pools:
        if not isinstance(part, XmlNode) or part.tag != "customwidgets":
            continue
        for custom in part.children:
            if custom.tag != "customwidget":
                continue
            found = {child.tag: child.text for child in custom.children}
            if found.get("class") == class_name and found.get("extends"):
                return found["extends"].split("::")[-1]
    return "QWidget"


def widget_class(doc, class_name: str):
    short = class_name.split("::")[-1]
    if hasattr(QtWidgets, short):
        return getattr(QtWidgets, short), False
    base = custom_base(doc, class_name)
    return getattr(QtWidgets, base, QWidget), True


def resolve_enum(text: str):
    value = None
    for piece in text.split("|"):
        piece = piece.strip()
        if "::" not in piece:
            continue
        scope, name = piece.split("::", 1)
        owner = _scope(scope)
        if owner is None:
            continue
        member = getattr(owner, name, None)
        if member is None:
            continue
        value = member if value is None else (value | member)
    return value


def _scope(name: str):
    if name == "Qt":
        return Qt
    for module in (QtWidgets, QtGui):
        if hasattr(module, name):
            return getattr(module, name)
    return None


def _child_text(node: XmlNode, tag: str) -> str:
    for child in node.children:
        if child.tag == tag:
            return child.text
    return ""


def apply_property(widget: QWidget, prop: Property, is_root: bool = False) -> None:
    kind = prop.body.tag
    name = prop.name
    if name == "buddy" or name == "geometry" and not is_root:
        if name == "geometry" and is_root and kind == "rect":
            widget.resize(int(_child_text(prop.body, "width") or 0), int(_child_text(prop.body, "height") or 0))
        return
    if kind == "sizepolicy":
        _apply_size_policy(widget, prop)
        return
    if kind == "size":
        size = QSize(int(_child_text(prop.body, "width") or 0), int(_child_text(prop.body, "height") or 0))
        setter = getattr(widget, "set" + name[0].upper() + name[1:], None)
        if setter is not None:
            setter(size)
        return
    if kind == "rect" and name == "geometry" and is_root:
        widget.resize(int(_child_text(prop.body, "width") or 0), int(_child_text(prop.body, "height") or 0))
        return
    setter = getattr(widget, "set" + name[0].upper() + name[1:], None)
    if setter is None:
        return
    if kind in {"string", "cstring"}:
        setter(prop.body.text)
    elif kind == "bool":
        setter(prop.body.text == "true")
    elif kind == "number":
        setter(int(float(prop.body.text or "0")))
    elif kind == "double":
        setter(float(prop.body.text or "0"))
    elif kind in {"enum", "set"}:
        value = resolve_enum(prop.body.text)
        if value is not None:
            setter(value)


def _apply_size_policy(widget: QWidget, prop: Property) -> None:
    horiz = getattr(QSizePolicy.Policy, prop.body.attrib.get("hsizetype", "Preferred"))
    vert = getattr(QSizePolicy.Policy, prop.body.attrib.get("vsizetype", "Preferred"))
    policy = QSizePolicy(horiz, vert)
    policy.setHorizontalStretch(int(_child_text(prop.body, "horstretch") or "0"))
    policy.setVerticalStretch(int(_child_text(prop.body, "verstretch") or "0"))
    policy.setHeightForWidth(widget.sizePolicy().hasHeightForWidth())
    widget.setSizePolicy(policy)


class Realization:
    def __init__(self):
        self.doc = None
        self.widgets: dict[str, QWidget] = {}
        self.layouts: dict[str, QtWidgets.QLayout] = {}
        self.root: QWidget | None = None
        self._filter = InputFilter()

    def build(self, doc) -> QWidget:
        self.doc = doc
        self.widgets.clear()
        self.layouts.clear()
        self.root = self._create_widget(doc.root, None, True)
        self._fill(doc.root, self.root, True)
        self._finish(doc)
        return self.root

    def refill(self, widget_id: str) -> None:
        node = next((widget for widget in iter_widgets(self.doc) if widget.id == widget_id), None)
        qwidget = self.widgets.get(widget_id)
        if node is None or qwidget is None:
            self.build(self.doc)
            return
        self._forget_descendants(qwidget)
        self._clear(qwidget)
        self._fill(node, qwidget, qwidget is self.root)
        self._finish(self.doc)

    def sync(self) -> bool:
        """Update the live tree to match the model when only layout membership changed."""
        if self.doc is None or self.root is None:
            return False
        model_layouts = {}
        for widget in iter_widgets(self.doc):
            layout = widget_layout(widget)
            if layout is not None:
                model_layouts[layout.id] = layout
        if set(model_layouts) != set(self.layouts):
            return False
        desired = {widget.id: widget for widget in iter_widgets(self.doc)}
        extra = [node_id for node_id in self.widgets if node_id not in desired and node_id != self.root.property("formId")]
        missing = [widget for widget_id, widget in desired.items() if widget_id not in self.widgets]
        if any(not self._direct_layout_child(node_id, extra_node=True) for node_id in extra):
            return False
        if any(not self._direct_layout_child(node.id, extra_node=False) for node in missing):
            return False
        for node_id in extra:
            self._detach(node_id)
        for node in missing:
            if not self._place_new(node):
                return False
        if not missing and not extra:
            index = self._membership()
            self._reparent_from(index)
            self._reorder_from(index)
        return True

    def _membership(self) -> dict:
        found = {}
        for widget in iter_widgets(self.doc):
            layout = widget_layout(widget)
            if layout is None:
                continue
            for slot, item in enumerate(layout_items(layout)):
                content = item_content(item)
                if isinstance(content, Widget):
                    found[content.id] = (layout, item, slot)
        return found

    def _reparent_from(self, index: dict) -> None:
        for node_id, (layout, item, _slot) in index.items():
            widget = self.widgets.get(node_id)
            qlayout = self.layouts.get(layout.id)
            if widget is None or qlayout is None or widget.parentWidget() is qlayout.parentWidget():
                continue
            widget.setParent(qlayout.parentWidget())
            self._insert_child(qlayout, layout, item, widget)

    def _reorder_from(self, index: dict) -> None:
        grouped: dict[str, list] = {}
        for node_id, (layout, _item, slot) in index.items():
            if layout.class_name not in {"QVBoxLayout", "QHBoxLayout"}:
                continue
            grouped.setdefault(layout.id, []).append((slot, self.widgets.get(node_id)))
        for layout_id, rows in grouped.items():
            qlayout = self.layouts.get(layout_id)
            if qlayout is None or any(child is None for _slot, child in rows):
                continue
            wanted = [child for _slot, child in sorted(rows)]
            current = [qlayout.itemAt(i).widget() for i in range(qlayout.count())]
            if current == wanted:
                continue
            while qlayout.count():
                qlayout.takeAt(0)
            for child in wanted:
                qlayout.addWidget(child)

    def _direct_layout_child(self, node_id: str, extra_node: bool) -> bool:
        if extra_node:
            widget = self.widgets.get(node_id)
            if widget is None:
                return False
            parent = widget.parentWidget()
            return parent is not None and parent.layout() is not None and parent is not widget
        located = locate(self.doc, node_id)
        if located is None or not isinstance(located[0], LayoutItem):
            return False
        owner = locate(self.doc, located[0].id)
        return owner is not None and isinstance(owner[0], Layout) and owner[0].id in self.layouts

    def _detach(self, node_id: str) -> None:
        widget = self.widgets.get(node_id)
        if widget is None:
            return
        self._forget_descendants(widget)
        self.widgets.pop(node_id, None)
        widget.setParent(None)
        widget.deleteLater()

    def _place_new(self, node: Widget) -> bool:
        layout, item = self._item_and_layout(node.id)
        if layout is None or item is None:
            return False
        qlayout = self.layouts.get(layout.id)
        if qlayout is None or qlayout.parentWidget() is None:
            return False
        child = self._create_widget(node, qlayout.parentWidget(), False)
        self._fill(node, child, False)
        self._insert_child(qlayout, layout, item, child)
        return True

    def _item_and_layout(self, node_id):
        located = locate(self.doc, node_id)
        if located is None or not isinstance(located[0], LayoutItem):
            return None, None
        owner = locate(self.doc, located[0].id)
        if owner is None or not isinstance(owner[0], Layout):
            return None, None
        return owner[0], located[0]

    def _insert_child(self, qlayout, layout: Layout, item, child: QWidget) -> None:
        if layout.class_name == "QFormLayout":
            row = int(item.attrib.get("row", "0"))
            column = item.attrib.get("column", "0")
            colspan = item.attrib.get("colspan")
            if (colspan and int(colspan) > 1) or column == "2":
                role = QtWidgets.QFormLayout.SpanningRole
            elif column == "1":
                role = QtWidgets.QFormLayout.FieldRole
            else:
                role = QtWidgets.QFormLayout.LabelRole
            qlayout.setWidget(row, role, child)
            return
        if layout.class_name == "QGridLayout":
            qlayout.addWidget(
                child,
                int(item.attrib.get("row", "0")),
                int(item.attrib.get("column", "0")),
                int(item.attrib.get("rowspan", "1")),
                int(item.attrib.get("colspan", "1")),
            )
            return
        slot = layout_items(layout).index(item)
        qlayout.insertWidget(slot, child)

    def apply_node_property(self, node_id: str, name: str) -> None:
        widget = self.widgets.get(node_id)
        node = self.widgets and next((item for item in iter_widgets(self.doc) if item.id == node_id), None)
        if widget is None or node is None:
            return
        prop = get_property(node, name)
        if prop is None:
            return
        apply_property(widget, prop, widget is self.root)
        if name == "buddy" and prop.body.tag == "cstring":
            target = self._named(prop.body.text)
            if target is not None and hasattr(widget, "setBuddy"):
                widget.setBuddy(target)

    def _finish(self, doc) -> None:
        for widget in iter_widgets(doc):
            buddy = get_property(widget, "buddy")
            qwidget = self.widgets.get(widget.id)
            if buddy is None or qwidget is None or not hasattr(qwidget, "setBuddy"):
                continue
            target = self._named(buddy.body.text)
            if target is not None:
                qwidget.setBuddy(target)
        order = []
        stops = tabstops_of(doc)
        if stops and stops.names:
            order = stops.names
        for left, right in zip(order, order[1:]):
            a = self._named(left)
            b = self._named(right)
            if a is not None and b is not None:
                QWidget.setTabOrder(a, b)
        links = connections_of(doc)
        if links:
            for link in links.items:
                sender = self._named(link.sender)
                receiver = self._named(link.receiver)
                if sender is None or receiver is None:
                    continue
                signal = getattr(sender, link.signal.split("(")[0], None)
                slot = getattr(receiver, link.slot.split("(")[0], None)
                if signal is not None and slot is not None:
                    try:
                        signal.connect(slot)
                    except (RuntimeError, TypeError):
                        pass

    def _named(self, name: str):
        for widget in self.widgets.values():
            if widget.objectName() == name:
                return widget
        return None

    def _create_widget(self, node: Widget, parent, is_root: bool) -> QWidget:
        cls, custom = widget_class(self.doc, node.class_name)
        widget = cls(parent)
        widget.setObjectName(node.object_name)
        widget.setProperty("formId", node.id)
        if custom:
            widget.setToolTip(node.class_name)
        widget.installEventFilter(self._filter)
        self.widgets[node.id] = widget
        for prop in properties_of(node):
            apply_property(widget, prop, is_root)
        return widget

    def _fill(self, node: Widget, widget: QWidget, is_root: bool) -> None:
        self._actions(node, widget)
        if node.class_name == "QMainWindow":
            self._fill_main_window(node, widget)
        elif node.class_name == "QTabWidget":
            self._fill_pages(node, widget, tabs=True)
        elif node.class_name == "QStackedWidget":
            self._fill_pages(node, widget, tabs=False)
        elif node.class_name == "QScrollArea":
            pages = child_widgets(node)
            if pages:
                child = self._create_widget(pages[0], None, False)
                self._fill(pages[0], child, False)
                widget.setWidget(child)
        elif node.class_name == "QSplitter":
            for index, child_node in enumerate(child_widgets(node)):
                child = self._create_widget(child_node, widget, False)
                self._fill(child_node, child, False)
                widget.addWidget(child)
                stretch = _stretch_for(child_node, node)
                if stretch:
                    widget.setStretchFactor(index, stretch)
        elif node.class_name in {"QMenuBar", "QMenu", "QToolBar"}:
            self._fill_menuish(node, widget)
        else:
            layout = widget_layout(node)
            if layout is not None:
                self._fill_layout(layout, widget)
            else:
                for child_node in child_widgets(node):
                    child = self._create_widget(child_node, widget, False)
                    self._fill(child_node, child, False)
        self._combo_items(node, widget)
        self._design_min(node, widget)
        current = get_property(node, "currentIndex")
        if current is not None and current.body.tag == "number" and hasattr(widget, "setCurrentIndex"):
            widget.setCurrentIndex(int(float(current.body.text or "0")))

    def _design_min(self, node: Widget, widget: QWidget) -> None:
        layout = widget_layout(node)
        if layout is None or layout_items(layout):
            return
        if get_property(node, "minimumSize") is None:
            widget.setMinimumSize(max(widget.minimumWidth(), 36), max(widget.minimumHeight(), 28))

    def _combo_items(self, node: Widget, widget: QWidget) -> None:
        entries = [part for part in node.body if isinstance(part, ItemEntry)]
        if not entries or not hasattr(widget, "addItem"):
            return
        for entry in entries:
            text = ""
            for part in entry.body:
                if isinstance(part, Property) and part.name == "text":
                    text = part.body.text
            widget.addItem(text)

    def _actions(self, node: Widget, widget: QWidget) -> None:
        for part in node.body:
            if isinstance(part, Action):
                action = QtGui.QAction(widget)
                action.setObjectName(part.name)
                for prop in properties_of(part):
                    apply_property(action, prop, False)
                widget.addAction(action)

    def _fill_main_window(self, node: Widget, widget: QWidget) -> None:
        central = None
        for child in child_widgets(node):
            if child.class_name == "QMenuBar":
                bar = self._create_widget(child, widget, False)
                self._fill(child, bar, False)
                widget.setMenuBar(bar)
            elif child.class_name == "QStatusBar":
                bar = self._create_widget(child, widget, False)
                self._fill(child, bar, False)
                widget.setStatusBar(bar)
            elif child.class_name == "QToolBar":
                bar = self._create_widget(child, widget, False)
                self._fill(child, bar, False)
                widget.addToolBar(bar)
            elif central is None:
                central = child
                body = self._create_widget(child, widget, False)
                self._fill(child, body, False)
                widget.setCentralWidget(body)

    def _fill_pages(self, node: Widget, widget: QWidget, tabs: bool) -> None:
        for child in child_widgets(node):
            page = self._create_widget(child, widget if not tabs else None, False)
            self._fill(child, page, False)
            title = ""
            for attr in attributes_of(child):
                if attr.name == "title":
                    title = attr.body.text
            if tabs:
                widget.addTab(page, title)
            else:
                widget.addWidget(page)

    def _fill_menuish(self, node: Widget, widget: QWidget) -> None:
        actions = {action.objectName(): action for action in widget.actions()}
        parent = widget.parentWidget()
        if parent is not None:
            for action in parent.actions():
                actions.setdefault(action.objectName(), action)
        for child in child_widgets(node):
            if child.class_name == "QMenu":
                menu = self._create_widget(child, widget, False)
                self._fill(child, menu, False)
                if hasattr(widget, "addMenu"):
                    widget.addMenu(menu)
                elif hasattr(widget, "addAction"):
                    widget.addAction(menu.menuAction())
        for part in node.body:
            from spikes.form_builder.model import ActionRef

            if isinstance(part, ActionRef) and part.name in actions:
                widget.addAction(actions[part.name])

    def _fill_layout(self, layout: Layout, parent: QWidget) -> None:
        cls = getattr(QtWidgets, layout.class_name, QtWidgets.QVBoxLayout)
        qlayout = cls(parent)
        qlayout.setObjectName(layout.object_name)
        self.layouts[layout.id] = qlayout
        for prop in properties_of(layout):
            apply_property(qlayout, prop, False)
        if layout.class_name == "QFormLayout":
            for item in layout_items(layout):
                self._place_form(qlayout, item, parent)
        elif layout.class_name == "QGridLayout":
            for item in layout_items(layout):
                self._place_grid(qlayout, item, parent)
        else:
            for item in layout_items(layout):
                self._place_box(qlayout, item, parent)
        rows = [part for part in layout.body if isinstance(part, XmlNode) and part.tag == "row"]
        cols = [part for part in layout.body if isinstance(part, XmlNode) and part.tag == "column"]
        for index, part in enumerate(rows):
            if "stretch" in part.attrib and hasattr(qlayout, "setRowStretch"):
                qlayout.setRowStretch(index, int(part.attrib["stretch"]))
        for index, part in enumerate(cols):
            if "stretch" in part.attrib and hasattr(qlayout, "setColumnStretch"):
                qlayout.setColumnStretch(index, int(part.attrib["stretch"]))

    def _place_box(self, qlayout, item, parent: QWidget) -> None:
        content = item_content(item)
        if isinstance(content, Widget):
            child = self._create_widget(content, parent, False)
            self._fill(content, child, False)
            qlayout.addWidget(child)
        elif isinstance(content, Layout):
            holder = QWidget(parent)
            self._fill_layout(content, holder)
            qlayout.addWidget(holder)
        elif isinstance(content, Spacer):
            qlayout.addItem(_spacer(content))

    def _place_grid(self, qlayout, item, parent: QWidget) -> None:
        content = item_content(item)
        row = int(item.attrib.get("row", "0"))
        col = int(item.attrib.get("column", "0"))
        rowspan = int(item.attrib.get("rowspan", "1"))
        colspan = int(item.attrib.get("colspan", "1"))
        if isinstance(content, Widget):
            child = self._create_widget(content, parent, False)
            self._fill(content, child, False)
            qlayout.addWidget(child, row, col, rowspan, colspan)
        elif isinstance(content, Spacer):
            qlayout.addItem(_spacer(content), row, col)

    def _place_form(self, qlayout, item, parent: QWidget) -> None:
        content = item_content(item)
        if not isinstance(content, Widget):
            return
        child = self._create_widget(content, parent, False)
        self._fill(content, child, False)
        row = int(item.attrib.get("row", "0"))
        column = item.attrib.get("column", "0")
        colspan = item.attrib.get("colspan")
        if (colspan and int(colspan) > 1) or column == "2":
            role = QtWidgets.QFormLayout.SpanningRole
        elif column == "1":
            role = QtWidgets.QFormLayout.FieldRole
        else:
            role = QtWidgets.QFormLayout.LabelRole
        qlayout.setWidget(row, role, child)

    def _clear(self, widget: QWidget) -> None:
        layout = widget.layout()
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                child = item.widget()
                if child is not None:
                    child.setParent(None)
                    child.deleteLater()
            QWidget().setLayout(layout)
        if isinstance(widget, QtWidgets.QTabWidget):
            while widget.count():
                page = widget.widget(0)
                widget.removeTab(0)
                page.setParent(None)
                page.deleteLater()
        elif isinstance(widget, QtWidgets.QStackedWidget):
            while widget.count():
                page = widget.widget(0)
                widget.removeWidget(page)
                page.deleteLater()
        elif isinstance(widget, QtWidgets.QSplitter):
            for index in range(widget.count() - 1, -1, -1):
                child = widget.widget(index)
                child.setParent(None)
                child.deleteLater()
        else:
            for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                if child.objectName().startswith("qt_"):
                    continue
                child.setParent(None)
                child.deleteLater()

    def _forget_descendants(self, widget: QWidget) -> None:
        doomed = {child.property("formId") for child in widget.findChildren(QWidget)}
        doomed.discard(None)
        for node_id in list(self.widgets):
            if node_id in doomed:
                self.widgets.pop(node_id, None)
        for node_id, layout in list(self.layouts.items()):
            host = layout.parentWidget()
            if host is not None and (host is widget or widget.isAncestorOf(host) or host.property("formId") in doomed):
                self.layouts.pop(node_id, None)


def _spacer(spacer: Spacer) -> QtWidgets.QSpacerItem:
    width, height = 40, 20
    hint = get_property(spacer, "sizeHint")
    if hint is not None and hint.body.tag == "size":
        width = int(_child_text(hint.body, "width") or width)
        height = int(_child_text(hint.body, "height") or height)
    orient = ""
    prop = get_property(spacer, "orientation")
    if prop is not None:
        orient = prop.body.text
    if "Vertical" in orient:
        return QtWidgets.QSpacerItem(width, height, QSizePolicy.Minimum, QSizePolicy.Expanding)
    return QtWidgets.QSpacerItem(width, height, QSizePolicy.Expanding, QSizePolicy.Minimum)


def _stretch_for(child: Widget, splitter: Widget) -> int:
    orient = ""
    prop = get_property(splitter, "orientation")
    if prop is not None:
        orient = prop.body.text
    policy = get_property(child, "sizePolicy")
    if policy is None or policy.body.tag != "sizepolicy":
        return 0
    tag = "verstretch" if "Vertical" in orient else "horstretch"
    try:
        return int(_child_text(policy.body, tag) or "0")
    except ValueError:
        return 0
