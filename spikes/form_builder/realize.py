"""Build real PySide6 widgets from the form model, and keep them in step.

`build` creates the whole tree once. After a structural edit, `reconcile`
compares a small signature per container (a layout's item list, a tab widget's
pages) with the one it built, takes the existing QWidgets out of the containers
that changed, and puts them back where the model now says. Only widgets that are
new to the model are constructed, so wrap, unwrap, nest, and first-layout-on-an-
empty-container move live widgets instead of rebuilding a subtree.
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtWidgets import QSizePolicy, QWidget

from spikes.form_builder.model import (
    Action,
    ActionRef,
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
    iter_nodes,
    iter_widgets,
    layout_items,
    properties_of,
    tabstops_of,
    widget_layout,
)

PAGE_CLASSES = {"QTabWidget", "QStackedWidget", "QSplitter", "QScrollArea", "QToolBox"}
CHROME_CLASSES = {"QMainWindow", "QMenuBar", "QMenu", "QToolBar", "QStatusBar", "QDockWidget"}
MARGINS = ("leftMargin", "topMargin", "rightMargin", "bottomMargin")


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
            QEvent.HoverEnter,
            QEvent.HoverMove,
        }:
            return True
        return False


def custom_base(doc, class_name: str) -> str:
    for custom in custom_widgets(doc):
        if custom.get("class") == class_name and custom.get("extends"):
            return custom["extends"].split("::")[-1]
    return "QWidget"


def custom_widgets(doc) -> list[dict]:
    found = []
    for part in list(doc.header) + list(doc.footer):
        if not isinstance(part, XmlNode) or part.tag != "customwidgets":
            continue
        for custom in part.children:
            if custom.tag == "customwidget":
                found.append({child.tag: child.text for child in custom.children})
    return found


def widget_class(doc, class_name: str):
    short = class_name.split("::")[-1]
    if "::" not in class_name and hasattr(QtWidgets, short):
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


def apply_property(widget, prop: Property, is_root: bool = False) -> None:
    kind = prop.body.tag
    name = prop.name
    if name == "buddy":
        return
    if name == "geometry":
        if is_root and kind == "rect":
            widget.resize(int(_child_text(prop.body, "width") or 0), int(_child_text(prop.body, "height") or 0))
        return
    if isinstance(widget, QtWidgets.QLayout) and name in MARGINS + ("margin",):
        _apply_margin(widget, name, int(float(prop.body.text or "0")))
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
    setter = getattr(widget, "set" + name[0].upper() + name[1:], None)
    if setter is None:
        return
    try:
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
    except (TypeError, ValueError, OverflowError):
        pass


def _apply_margin(layout, name: str, value: int) -> None:
    margins = layout.contentsMargins()
    left, top, right, bottom = margins.left(), margins.top(), margins.right(), margins.bottom()
    if name == "margin":
        left = top = right = bottom = value
    elif name == "leftMargin":
        left = value
    elif name == "topMargin":
        top = value
    elif name == "rightMargin":
        right = value
    elif name == "bottomMargin":
        bottom = value
    layout.setContentsMargins(left, top, right, bottom)


def _apply_size_policy(widget: QWidget, prop: Property) -> None:
    horiz = getattr(QSizePolicy.Policy, prop.body.attrib.get("hsizetype", "Preferred"), QSizePolicy.Preferred)
    vert = getattr(QSizePolicy.Policy, prop.body.attrib.get("vsizetype", "Preferred"), QSizePolicy.Preferred)
    policy = QSizePolicy(horiz, vert)
    policy.setHorizontalStretch(int(_child_text(prop.body, "horstretch") or "0"))
    policy.setVerticalStretch(int(_child_text(prop.body, "verstretch") or "0"))
    policy.setHeightForWidth(widget.sizePolicy().hasHeightForWidth())
    widget.setSizePolicy(policy)


def _csv(text: str) -> list[int]:
    values = []
    for piece in (text or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            values.append(int(piece))
        except ValueError:
            values.append(0)
    return values


def apply_layout_attrib(qlayout, layout: Layout) -> None:
    """The ui4 layout attributes Designer writes: stretch, rowstretch, and friends."""
    attrib = layout.attrib
    if "stretch" in attrib and hasattr(qlayout, "setStretch"):
        for index, value in enumerate(_csv(attrib["stretch"])):
            if index < qlayout.count():
                qlayout.setStretch(index, value)
    setters = (
        ("rowstretch", "setRowStretch"),
        ("columnstretch", "setColumnStretch"),
        ("rowminimumheight", "setRowMinimumHeight"),
        ("columnminimumwidth", "setColumnMinimumWidth"),
    )
    for key, setter_name in setters:
        setter = getattr(qlayout, setter_name, None)
        if key in attrib and setter is not None:
            for index, value in enumerate(_csv(attrib[key])):
                setter(index, value)


def form_rows(layout: Layout) -> dict[int, int]:
    """Map stored form rows to dense rows, the way QFormLayout will show them."""
    rows = sorted({int(item.attrib.get("row", "0") or 0) for item in layout_items(layout)})
    return {row: index for index, row in enumerate(rows)}


def _item_sig(item: LayoutItem):
    content = item_content(item)
    kind = type(content).__name__ if content is not None else "Empty"
    attrib = item.attrib
    return (
        kind,
        getattr(content, "id", ""),
        attrib.get("row", ""),
        attrib.get("column", ""),
        attrib.get("rowspan", ""),
        attrib.get("colspan", ""),
    )


def _chrome_sig(node: Widget):
    parts = []
    for part in node.body:
        if isinstance(part, Widget):
            parts.append(("w", part.id, part.class_name))
        elif isinstance(part, ActionRef):
            parts.append(("a", part.name))
        elif isinstance(part, Action):
            parts.append(("act", part.id, part.name))
    return tuple(parts)


def units(doc):
    """Containers in document order: (key, signature, host_kind, host_id, model node)."""
    found = []
    for node in iter_nodes(doc):
        if isinstance(node, Layout):
            sig = (node.class_name,) + tuple(_item_sig(item) for item in layout_items(node))
            found.append((("L", node.id), sig, node))
        elif isinstance(node, Widget):
            if node.class_name in CHROME_CLASSES:
                found.append((("M", node.id), _chrome_sig(node), node))
            elif node.class_name in PAGE_CLASSES:
                pages = []
                for child in child_widgets(node):
                    title = ""
                    for attr in attributes_of(child):
                        if attr.name in ("title", "label"):
                            title = attr.body.text
                    pages.append((child.id, title))
                found.append((("P", node.id), tuple(pages), node))
            elif widget_layout(node) is None and child_widgets(node):
                found.append((("C", node.id), tuple(child.id for child in child_widgets(node)), node))
    return found


class Realization:
    def __init__(self):
        self.doc = None
        self.widgets: dict[str, QWidget] = {}
        self.layouts: dict[str, QtWidgets.QLayout] = {}
        self.holders: dict[str, QWidget] = {}
        self.order: dict[str, list[str]] = {}
        self.sigs: dict = {}
        self.root: QWidget | None = None
        self.connect_signals = True
        self._pool: dict[str, QWidget] = {}
        self._fresh: set[str] = set()
        self._names: dict[str, QWidget] | None = None
        self._filter = InputFilter()

    # ------------------------------------------------------------------ build
    def build(self, doc) -> QWidget:
        self.doc = doc
        self.widgets.clear()
        self.layouts.clear()
        self.holders.clear()
        self.order.clear()
        self._pool = {}
        self.root = self._create_widget(doc.root, None, True)
        self._fill(doc.root, self.root, True)
        self._finish(doc, connect=self.connect_signals)
        self.sigs = {key: sig for key, sig, _node in units(doc)}
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
        self._finish(self.doc, connect=False)
        self.sigs = {key: sig for key, sig, _node in units(self.doc)}

    # -------------------------------------------------------------- reconcile
    def sync(self) -> bool:
        return self.reconcile()

    def reconcile(self) -> bool:
        """Patch the live tree to match the model. False means: rebuild everything."""
        if self.doc is None or self.root is None:
            return False
        model_units = units(self.doc)
        model_keys = {key for key, _sig, _node in model_units}
        dirty = [(key, sig, node) for key, sig, node in model_units if self.sigs.get(key) != sig]
        gone = [key for key in self.sigs if key not in model_keys]
        if not dirty and not gone:
            return True
        if any(key[0] == "M" for key, _sig, _node in dirty) or any(key[0] == "M" for key in gone):
            return False
        if self.root.property("formId") != self.doc.root.id:
            return False
        self._pool = {}
        self._fresh = set()
        # Phase 1: take the live children out of every container that changed or vanished.
        for key, _sig, node in dirty:
            self._detach_unit(key, node)
        for key in gone:
            self._detach_unit(key, None)
        # Phase 2: put them back, top-down, constructing only what is new.
        for key, sig, node in dirty:
            if self.sigs.get(key) == sig and key[0] == "L" and key[1] in self.layouts:
                continue
            if key[0] in ("C", "P") and key[1] in self._fresh:
                continue
            host = self._host_for(key, node)
            if host is None:
                continue
            if key[0] == "L":
                if key[1] in self.layouts:
                    continue
                self._fill_layout(node, host)
                self._design_min_reset(host, node)
            elif key[0] == "C":
                for child_node in child_widgets(node):
                    self._obtain(child_node, host)
            elif key[0] == "P":
                self._fill_pages_of(node, host)
        # Phase 3: whatever nobody claimed is gone from the model.
        for leftover in list(self._pool.values()):
            self._forget_descendants(leftover)
            self.widgets.pop(str(leftover.property("formId") or ""), None)
            holder_id = leftover.property("formLayoutHolder")
            if holder_id:
                self.holders.pop(str(holder_id), None)
                self.layouts.pop(str(holder_id), None)
            leftover.setParent(None)
            leftover.deleteLater()
        self._pool = {}
        live = {node.id for node in iter_nodes(self.doc) if isinstance(node, Layout)}
        for layout_id in [layout_id for layout_id in self.layouts if layout_id not in live]:
            self.layouts.pop(layout_id, None)
            self.holders.pop(layout_id, None)
        self._finish(self.doc, connect=False)
        self.sigs = {key: sig for key, sig, _node in model_units}
        return True

    def _host_for(self, key, node):
        kind, node_id = key
        if kind == "L":
            if node_id in self.holders:
                return self.holders[node_id]
            owner = _owner_of(self.doc, node_id)
            if owner is not None:
                return self.widgets.get(owner.id)
            return None
        return self.widgets.get(node_id)

    def _detach_unit(self, key, node) -> None:
        kind, node_id = key
        if kind == "L":
            qlayout = self.layouts.get(node_id)
            if qlayout is None:
                host = self._host_for(key, node) if node is not None else None
                if host is not None and host.layout() is not None:
                    self._detach_layout(host.layout())
                return
            self._detach_layout(qlayout)
            self.layouts.pop(node_id, None)
            return
        widget = self.widgets.get(node_id)
        if widget is None:
            return
        if kind == "C":
            if widget.layout() is not None:
                stale = widget.layout()
                for layout_id, qlayout in list(self.layouts.items()):
                    if qlayout is stale:
                        self.layouts.pop(layout_id, None)
                self._detach_layout(stale)
            for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                form_id = child.property("formId")
                if form_id:
                    self._pool[str(form_id)] = child
        elif kind == "P":
            for page in self._take_pages(widget):
                form_id = page.property("formId")
                if form_id:
                    self._pool[str(form_id)] = page

    def _detach_layout(self, qlayout) -> None:
        while qlayout.count():
            item = qlayout.takeAt(0)
            child = item.widget()
            if child is None:
                continue
            form_id = child.property("formId")
            holder = child.property("formLayoutHolder")
            if form_id:
                self._pool[str(form_id)] = child
            elif holder:
                self._pool["L:" + str(holder)] = child
            else:
                child.setParent(None)
                child.deleteLater()
        QWidget().setLayout(qlayout)

    def _take_pages(self, widget: QWidget) -> list[QWidget]:
        pages = []
        if isinstance(widget, QtWidgets.QTabWidget):
            while widget.count():
                page = widget.widget(0)
                widget.removeTab(0)
                pages.append(page)
        elif isinstance(widget, QtWidgets.QToolBox):
            while widget.count():
                page = widget.widget(0)
                widget.removeItem(0)
                pages.append(page)
        elif isinstance(widget, QtWidgets.QStackedWidget):
            while widget.count():
                page = widget.widget(0)
                widget.removeWidget(page)
                pages.append(page)
        elif isinstance(widget, QtWidgets.QSplitter):
            pages = [widget.widget(index) for index in range(widget.count())]
            for page in pages:
                page.setParent(None)
        elif isinstance(widget, QtWidgets.QScrollArea):
            page = widget.takeWidget()
            if page is not None:
                pages.append(page)
        return pages

    def _obtain(self, node: Widget, parent) -> QWidget:
        existing = self._pool.pop(node.id, None)
        if existing is not None:
            if existing.parentWidget() is not parent:
                existing.setParent(parent)
            visible = get_property(node, "visible")
            if visible is None or visible.body.text != "false":
                existing.show()
            return existing
        child = self._create_widget(node, parent, False)
        self._fill(node, child, False)
        return child

    # ------------------------------------------------------------- properties
    def apply_node_property(self, node_id: str, name: str) -> None:
        qlayout = self.layouts.get(node_id)
        if qlayout is not None:
            node = next((item for item in iter_nodes(self.doc) if isinstance(item, Layout) and item.id == node_id), None)
            if node is None:
                return
            prop = get_property(node, name)
            if prop is None:
                if name in MARGINS or name == "margin":
                    style = qlayout.parentWidget().style() if qlayout.parentWidget() else None
                    default = style.pixelMetric(QtWidgets.QStyle.PM_LayoutLeftMargin) if style else 9
                    _apply_margin(qlayout, name, default)
                elif name == "spacing":
                    qlayout.setSpacing(-1)
                return
            apply_property(qlayout, prop, False)
            return
        widget = self.widgets.get(node_id)
        node = next((item for item in iter_widgets(self.doc) if item.id == node_id), None) if widget is not None else None
        if widget is None or node is None:
            return
        prop = get_property(node, name)
        if prop is None:
            self._reset_property(widget, node, name)
            return
        apply_property(widget, prop, widget is self.root)
        if name == "buddy" and prop.body.tag == "cstring":
            target = self.named(prop.body.text)
            if target is not None and hasattr(widget, "setBuddy"):
                widget.setBuddy(target)

    def _reset_property(self, widget: QWidget, node: Widget, name: str) -> None:
        """A property was removed from the file: put the class default back."""
        fresh_cls, _custom = widget_class(self.doc, node.class_name)
        try:
            fresh = fresh_cls()
        except TypeError:
            return
        if name in ("minimumSize", "maximumSize", "sizePolicy"):
            widget.setMinimumSize(fresh.minimumSize())
            widget.setMaximumSize(fresh.maximumSize())
            if name == "sizePolicy":
                widget.setSizePolicy(fresh.sizePolicy())
            for prop in properties_of(node):
                if prop.name in ("minimumSize", "maximumSize", "sizePolicy"):
                    apply_property(widget, prop, widget is self.root)
        else:
            value = fresh.property(name)
            if value is not None:
                widget.setProperty(name, value)
        fresh.deleteLater()

    def named(self, name: str):
        if self._names is not None:
            return self._names.get(name)
        for widget in self.widgets.values():
            if widget.objectName() == name:
                return widget
        return None

    _named = named

    def _finish(self, doc, connect: bool = True) -> None:
        self._names = {widget.objectName(): widget for widget in self.widgets.values()}
        try:
            self._finish_with_names(doc, connect)
        finally:
            self._names = None

    def _finish_with_names(self, doc, connect: bool) -> None:
        for widget in iter_widgets(doc):
            buddy = get_property(widget, "buddy")
            qwidget = self.widgets.get(widget.id)
            if buddy is None or qwidget is None or not hasattr(qwidget, "setBuddy"):
                continue
            target = self.named(buddy.body.text)
            if target is not None:
                qwidget.setBuddy(target)
        if not connect:
            return
        order = []
        stops = tabstops_of(doc)
        if stops and stops.names:
            order = stops.names
        for left, right in zip(order, order[1:]):
            a = self.named(left)
            b = self.named(right)
            if a is not None and b is not None:
                QWidget.setTabOrder(a, b)
        links = connections_of(doc)
        if links:
            for link in links.items:
                sender = self.named(link.sender)
                receiver = self.named(link.receiver)
                if sender is None or receiver is None:
                    continue
                signal = getattr(sender, link.signal.split("(")[0], None)
                slot = getattr(receiver, link.slot.split("(")[0], None)
                if signal is not None and slot is not None:
                    try:
                        signal.connect(slot)
                    except (RuntimeError, TypeError, AttributeError):
                        pass

    # ------------------------------------------------------------------- fill
    def _create_widget(self, node: Widget, parent, is_root: bool) -> QWidget:
        cls, custom = widget_class(self.doc, node.class_name)
        widget = cls(parent)
        widget.setObjectName(node.object_name)
        widget.setProperty("formId", node.id)
        if custom:
            widget.setProperty("formCustomClass", node.class_name)
            widget.setToolTip(node.class_name)
        if isinstance(widget, QtWidgets.QMenuBar):
            widget.setNativeMenuBar(False)
        # The canvas overlay takes every pointer event, so the widgets only need to
        # stay out of the focus chain. A Python event filter per widget cost ~20 ms
        # per open on the 302-widget form.
        widget.setFocusPolicy(Qt.NoFocus)
        self.widgets[node.id] = widget
        self._fresh.add(node.id)
        for prop in properties_of(node):
            apply_property(widget, prop, is_root)
        return widget

    def _fill(self, node: Widget, widget: QWidget, is_root: bool) -> None:
        self._actions(node, widget)
        if node.class_name == "QMainWindow":
            self._fill_main_window(node, widget)
        elif node.class_name in PAGE_CLASSES:
            self._fill_pages_of(node, widget)
        elif node.class_name in {"QMenuBar", "QMenu", "QToolBar"}:
            self._fill_menuish(node, widget)
        else:
            layout = widget_layout(node)
            if layout is not None:
                self._fill_layout(layout, widget)
            else:
                for child_node in child_widgets(node):
                    self._obtain(child_node, widget)
        self._combo_items(node, widget)
        self._design_min(node, widget)
        current = get_property(node, "currentIndex")
        if current is not None and current.body.tag == "number" and hasattr(widget, "setCurrentIndex"):
            widget.setCurrentIndex(int(float(current.body.text or "0")))

    def _fill_pages_of(self, node: Widget, widget: QWidget) -> None:
        if node.class_name == "QTabWidget":
            self._fill_pages(node, widget, "tabs")
        elif node.class_name == "QToolBox":
            self._fill_pages(node, widget, "toolbox")
        elif node.class_name == "QStackedWidget":
            self._fill_pages(node, widget, "stack")
        elif node.class_name == "QScrollArea":
            pages = child_widgets(node)
            if pages:
                child = self._obtain(pages[0], None)
                widget.setWidget(child)
        elif node.class_name == "QSplitter":
            for index, child_node in enumerate(child_widgets(node)):
                child = self._obtain(child_node, widget)
                widget.addWidget(child)
                stretch = _stretch_for(child_node, node)
                if stretch:
                    widget.setStretchFactor(index, stretch)
        current = get_property(node, "currentIndex")
        if current is not None and current.body.tag == "number" and hasattr(widget, "setCurrentIndex"):
            widget.setCurrentIndex(int(float(current.body.text or "0")))

    def _design_min(self, node: Widget, widget: QWidget) -> None:
        layout = widget_layout(node)
        if layout is None or layout_items(layout):
            return
        if get_property(node, "minimumSize") is None:
            widget.setMinimumSize(max(widget.minimumWidth(), 48), max(widget.minimumHeight(), 36))
            widget.setProperty("formDesignMin", True)

    def _design_min_reset(self, host: QWidget, layout: Layout) -> None:
        node_id = host.property("formId")
        if not node_id:
            return
        node = next((item for item in iter_widgets(self.doc) if item.id == node_id), None)
        if node is None:
            return
        if layout_items(layout):
            if host.property("formDesignMin"):
                host.setProperty("formDesignMin", False)
                host.setMinimumSize(0, 0)
                prop = get_property(node, "minimumSize")
                if prop is not None:
                    apply_property(host, prop, False)
        else:
            self._design_min(node, host)

    def _combo_items(self, node: Widget, widget: QWidget) -> None:
        entries = [part for part in node.body if isinstance(part, ItemEntry)]
        if not entries or not hasattr(widget, "addItem"):
            return
        if isinstance(widget, QtWidgets.QComboBox):
            widget.clear()
        for entry in entries:
            text = ""
            for part in entry.body:
                if isinstance(part, Property) and part.name == "text":
                    text = part.body.text
            try:
                widget.addItem(text)
            except TypeError:
                return

    def _actions(self, node: Widget, widget: QWidget) -> None:
        for part in node.body:
            if isinstance(part, Action):
                action = QtGui.QAction(widget)
                action.setObjectName(part.name)
                action.setProperty("formId", part.id)
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
            elif child.class_name == "QDockWidget":
                continue
            elif central is None:
                central = child
                body = self._create_widget(child, widget, False)
                self._fill(child, body, False)
                widget.setCentralWidget(body)

    def _fill_pages(self, node: Widget, widget: QWidget, kind: str) -> None:
        for child in child_widgets(node):
            page = self._obtain(child, widget if kind == "stack" else None)
            title = ""
            for attr in attributes_of(child):
                if attr.name in ("title", "label"):
                    title = attr.body.text
            if kind == "tabs":
                widget.addTab(page, title)
            elif kind == "toolbox":
                widget.addItem(page, title)
            else:
                widget.addWidget(page)

    def _fill_menuish(self, node: Widget, widget: QWidget) -> None:
        actions = {}
        top = self.root
        if top is not None:
            for action in top.actions():
                actions.setdefault(action.objectName(), action)
        for action in widget.actions():
            actions.setdefault(action.objectName(), action)
        menus = {}
        for child in child_widgets(node):
            if child.class_name == "QMenu":
                menu = self._create_widget(child, widget, False)
                self._fill(child, menu, False)
                menus[child.object_name] = menu
        for part in node.body:
            if not isinstance(part, ActionRef):
                continue
            if part.name == "separator":
                widget.addSeparator()
            elif part.name in menus:
                widget.addAction(menus[part.name].menuAction())
            elif part.name in actions:
                widget.addAction(actions[part.name])
        for name, menu in menus.items():
            if menu.menuAction() not in widget.actions():
                widget.addAction(menu.menuAction())

    def _fill_layout(self, layout: Layout, parent: QWidget) -> None:
        cls = getattr(QtWidgets, layout.class_name, QtWidgets.QVBoxLayout)
        qlayout = cls(parent)
        qlayout.setObjectName(layout.object_name)
        self.layouts[layout.id] = qlayout
        order = []
        self.order[layout.id] = order
        for prop in properties_of(layout):
            apply_property(qlayout, prop, False)
        items = layout_items(layout)
        if layout.class_name == "QFormLayout":
            dense = form_rows(layout)
            ranked = sorted(items, key=lambda item: (int(item.attrib.get("row", "0") or 0), item.attrib.get("column", "0")))
            for item in ranked:
                self._place_form(qlayout, item, parent, dense, order)
        elif layout.class_name == "QGridLayout":
            for item in items:
                self._place_grid(qlayout, item, parent, order)
        else:
            for item in items:
                self._place_box(qlayout, item, parent, order)
        apply_layout_attrib(qlayout, layout)
        rows = [part for part in layout.body if isinstance(part, XmlNode) and part.tag == "row"]
        cols = [part for part in layout.body if isinstance(part, XmlNode) and part.tag == "column"]
        for index, part in enumerate(rows):
            if "stretch" in part.attrib and hasattr(qlayout, "setRowStretch"):
                qlayout.setRowStretch(index, int(part.attrib["stretch"]))
        for index, part in enumerate(cols):
            if "stretch" in part.attrib and hasattr(qlayout, "setColumnStretch"):
                qlayout.setColumnStretch(index, int(part.attrib["stretch"]))

    def _nested(self, content: Layout, parent: QWidget) -> QWidget:
        holder = self._pool.pop("L:" + content.id, None)
        if holder is not None:
            if holder.parentWidget() is not parent:
                holder.setParent(parent)
            holder.show()
            return holder
        holder = QWidget(parent)
        holder.setProperty("formLayoutHolder", content.id)
        self.holders[content.id] = holder
        self._fill_layout(content, holder)
        margins = self.layouts[content.id].contentsMargins()
        if not any(get_property(content, name) for name in MARGINS + ("margin",)) and margins.left() > 0:
            # A nested layout has no margins in a real app; a holder widget would add them.
            self.layouts[content.id].setContentsMargins(0, 0, 0, 0)
        return holder

    def _place_box(self, qlayout, item, parent: QWidget, order: list) -> None:
        content = item_content(item)
        if isinstance(content, Widget):
            qlayout.addWidget(self._obtain(content, parent))
            order.append(content.id)
        elif isinstance(content, Layout):
            qlayout.addWidget(self._nested(content, parent))
            order.append(content.id)
        elif isinstance(content, Spacer):
            qlayout.addItem(_spacer(content))
            order.append(content.id)

    def _place_grid(self, qlayout, item, parent: QWidget, order: list) -> None:
        content = item_content(item)
        row = int(item.attrib.get("row", "0") or 0)
        col = int(item.attrib.get("column", "0") or 0)
        rowspan = int(item.attrib.get("rowspan", "1") or 1)
        colspan = int(item.attrib.get("colspan", "1") or 1)
        if isinstance(content, Widget):
            qlayout.addWidget(self._obtain(content, parent), row, col, rowspan, colspan)
            order.append(content.id)
        elif isinstance(content, Layout):
            qlayout.addWidget(self._nested(content, parent), row, col, rowspan, colspan)
            order.append(content.id)
        elif isinstance(content, Spacer):
            qlayout.addItem(_spacer(content), row, col, rowspan, colspan)
            order.append(content.id)

    def _place_form(self, qlayout, item, parent: QWidget, dense: dict, order: list) -> None:
        content = item_content(item)
        row = dense.get(int(item.attrib.get("row", "0") or 0), 0)
        column = item.attrib.get("column", "0")
        colspan = item.attrib.get("colspan")
        if (colspan and int(colspan) > 1) or column == "2":
            role = QtWidgets.QFormLayout.SpanningRole
        elif column == "1":
            role = QtWidgets.QFormLayout.FieldRole
        else:
            role = QtWidgets.QFormLayout.LabelRole
        if isinstance(content, Widget):
            qlayout.setWidget(row, role, self._obtain(content, parent))
            order.append(content.id)
        elif isinstance(content, Layout):
            qlayout.setWidget(row, role, self._nested(content, parent))
            order.append(content.id)
        elif isinstance(content, Spacer):
            qlayout.setItem(row, role, _spacer(content))
            order.append(content.id)

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
        for page in self._take_pages(widget):
            page.setParent(None)
            page.deleteLater()
        for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            if child.objectName().startswith("qt_"):
                continue
            if child.property("formId") or child.property("formLayoutHolder"):
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
            if host is not None and (host is widget or widget.isAncestorOf(host)):
                self.layouts.pop(node_id, None)
                self.holders.pop(node_id, None)


def _owner_of(doc, layout_id: str):
    for widget in iter_widgets(doc):
        layout = widget_layout(widget)
        if layout is not None and layout.id == layout_id:
            return widget
    return None


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
    size_type = get_property(spacer, "sizeType")
    grow = QSizePolicy.Expanding
    if size_type is not None:
        grow = resolve_enum(size_type.body.text) or grow
    if "Vertical" in orient:
        return QtWidgets.QSpacerItem(width, height, QSizePolicy.Minimum, grow)
    return QtWidgets.QSpacerItem(width, height, grow, QSizePolicy.Minimum)


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
