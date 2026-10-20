"""In-memory ui4 document. No Qt types."""

from __future__ import annotations

import copy
import keyword
from dataclasses import dataclass, field
from typing import Iterator, Optional, Union


@dataclass
class XmlNode:
    tag: str
    attrib: dict[str, str] = field(default_factory=dict)
    text: str = ""
    children: list["XmlNode"] = field(default_factory=list)


@dataclass
class Property:
    attrib: dict[str, str]
    body: XmlNode

    @property
    def name(self) -> str:
        return self.attrib.get("name", "")


@dataclass
class Attribute:
    attrib: dict[str, str]
    body: XmlNode

    @property
    def name(self) -> str:
        return self.attrib.get("name", "")


@dataclass
class ActionRef:
    name: str


@dataclass
class ZOrder:
    name: str


@dataclass
class ItemEntry:
    """A combo box, list, or tree item stored on a widget."""

    body: list = field(default_factory=list)


@dataclass
class Spacer:
    id: str
    name: str
    attrib: dict[str, str] = field(default_factory=dict)
    body: list = field(default_factory=list)


@dataclass
class LayoutItem:
    id: str
    attrib: dict[str, str] = field(default_factory=dict)
    body: list = field(default_factory=list)


@dataclass
class Layout:
    id: str
    class_name: str
    object_name: str
    attrib: dict[str, str] = field(default_factory=dict)
    body: list = field(default_factory=list)


@dataclass
class Action:
    id: str
    name: str
    attrib: dict[str, str] = field(default_factory=dict)
    body: list = field(default_factory=list)


@dataclass
class Widget:
    id: str
    class_name: str
    object_name: str
    attrib: dict[str, str] = field(default_factory=dict)
    body: list = field(default_factory=list)


@dataclass
class ClassDecl:
    name: str


@dataclass
class TabStops:
    names: list[str] = field(default_factory=list)


@dataclass
class Connection:
    sender: str
    signal: str
    receiver: str
    slot: str
    hints: list[XmlNode] = field(default_factory=list)
    extras: list[XmlNode] = field(default_factory=list)


@dataclass
class ConnectionList:
    items: list[Connection] = field(default_factory=list)
    attrib: dict[str, str] = field(default_factory=dict)


Node = Union[Widget, Layout, LayoutItem, Spacer, Action]


@dataclass
class Document:
    ui_attrib: dict[str, str]
    header: list
    root: Widget
    footer: list
    next_id: int = 1

    def alloc(self) -> str:
        value = f"id{self.next_id}"
        self.next_id += 1
        return value


INPUT_CLASSES = {
    "QLineEdit",
    "QPlainTextEdit",
    "QTextEdit",
    "QTextBrowser",
    "QSpinBox",
    "QDoubleSpinBox",
    "QComboBox",
    "QFontComboBox",
    "QDateEdit",
    "QDateTimeEdit",
    "QTimeEdit",
    "QCheckBox",
    "QRadioButton",
    "QSlider",
    "QDial",
    "QPushButton",
    "QToolButton",
    "QCommandLinkButton",
    "QListWidget",
    "QTableWidget",
    "QTreeWidget",
    "QListView",
    "QTableView",
    "QTreeView",
    "QColumnView",
    "QKeySequenceEdit",
}

CONTAINER_CLASSES = {
    "QWidget",
    "QFrame",
    "QGroupBox",
    "QScrollArea",
    "QTabWidget",
    "QStackedWidget",
    "QSplitter",
    "QMainWindow",
    "QDialog",
    "QWizardPage",
    "QToolBox",
    "QMdiArea",
}

_NAME_OVERRIDES = {
    "QPushButton": "pushButton",
    "QToolButton": "toolButton",
    "QRadioButton": "radioButton",
    "QCheckBox": "checkBox",
    "QCommandLinkButton": "commandLinkButton",
    "QLineEdit": "lineEdit",
    "QPlainTextEdit": "plainTextEdit",
    "QTextEdit": "textEdit",
    "QSpinBox": "spinBox",
    "QDoubleSpinBox": "doubleSpinBox",
    "QComboBox": "comboBox",
    "QDateEdit": "dateEdit",
    "QDateTimeEdit": "dateTimeEdit",
    "QTimeEdit": "timeEdit",
    "QLabel": "label",
    "QDialogButtonBox": "buttonBox",
    "QGroupBox": "groupBox",
    "QFrame": "frame",
    "QTabWidget": "tabWidget",
    "QStackedWidget": "stackedWidget",
    "QScrollArea": "scrollArea",
    "QSplitter": "splitter",
    "QListWidget": "listWidget",
    "QTableWidget": "tableWidget",
    "QTreeWidget": "treeWidget",
    "QSlider": "slider",
    "QProgressBar": "progressBar",
    "QDial": "dial",
    "QVBoxLayout": "verticalLayout",
    "QHBoxLayout": "horizontalLayout",
    "QGridLayout": "gridLayout",
    "QFormLayout": "formLayout",
    "QMenuBar": "menubar",
    "QMenu": "menu",
    "QToolBar": "toolBar",
    "QStatusBar": "statusbar",
    "QWidget": "widget",
    "QMainWindow": "MainWindow",
    "QDialog": "Dialog",
}


def default_object_name(class_name: str) -> str:
    if class_name in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[class_name]
    if class_name.startswith("Q") and len(class_name) > 1:
        rest = class_name[1:]
        return rest[0].lower() + rest[1:]
    return class_name


def valid_identifier(name: str) -> bool:
    return bool(name) and name.isidentifier() and not keyword.iskeyword(name)


def prop_string(name: str, text: str, notr: bool = False) -> Property:
    attrib = {"notr": "true"} if notr else {}
    return Property({"name": name}, XmlNode("string", attrib, text))


def prop_bool(name: str, value: bool) -> Property:
    return Property({"name": name}, XmlNode("bool", {}, "true" if value else "false"))


def prop_number(name: str, value: int) -> Property:
    return Property({"name": name}, XmlNode("number", {}, str(int(value))))


def prop_double(name: str, value: float) -> Property:
    return Property({"name": name}, XmlNode("double", {}, repr(float(value))))


def prop_enum(name: str, value: str) -> Property:
    return Property({"name": name}, XmlNode("enum", {}, value))


def prop_set(name: str, value: str) -> Property:
    return Property({"name": name}, XmlNode("set", {}, value))


def prop_cstring(name: str, value: str) -> Property:
    return Property({"name": name}, XmlNode("cstring", {}, value))


def prop_rect(name: str, x: int, y: int, w: int, h: int) -> Property:
    body = XmlNode(
        "rect",
        {},
        "",
        [
            XmlNode("x", {}, str(x)),
            XmlNode("y", {}, str(y)),
            XmlNode("width", {}, str(w)),
            XmlNode("height", {}, str(h)),
        ],
    )
    return Property({"name": name}, body)


def prop_size(name: str, w: int, h: int) -> Property:
    body = XmlNode(
        "size",
        {},
        "",
        [XmlNode("width", {}, str(w)), XmlNode("height", {}, str(h))],
    )
    return Property({"name": name}, body)


def simple_body(prop: Property) -> Optional[tuple[str, str]]:
    if prop.body.children:
        return None
    return prop.body.tag, prop.body.text


def properties_of(node) -> list[Property]:
    return [part for part in getattr(node, "body", []) if isinstance(part, Property)]


def get_property(node, name: str) -> Optional[Property]:
    for prop in properties_of(node):
        if prop.name == name:
            return prop
    return None


def set_property(node, prop: Optional[Property], name: str) -> None:
    body = node.body
    index = next(
        (i for i, part in enumerate(body) if isinstance(part, Property) and part.name == name),
        None,
    )
    if prop is None:
        if index is not None:
            body.pop(index)
        return
    if index is None:
        insert_at = 0
        for i, part in enumerate(body):
            if isinstance(part, Property):
                insert_at = i + 1
        body.insert(insert_at, prop)
    else:
        body[index] = prop


def widget_layout(widget: Widget) -> Optional[Layout]:
    for part in widget.body:
        if isinstance(part, Layout):
            return part
    return None


def child_widgets(widget: Widget) -> list[Widget]:
    return [part for part in widget.body if isinstance(part, Widget)]


def layout_items(layout: Layout) -> list[LayoutItem]:
    return [part for part in layout.body if isinstance(part, LayoutItem)]


def item_content(item: LayoutItem):
    for part in item.body:
        if isinstance(part, (Widget, Layout, Spacer)):
            return part
    return None


def attributes_of(widget: Widget) -> list[Attribute]:
    return [part for part in widget.body if isinstance(part, Attribute)]


def get_attribute(widget: Widget, name: str) -> Optional[Attribute]:
    for attr in attributes_of(widget):
        if attr.name == name:
            return attr
    return None


def set_attribute(widget: Widget, name: str, text: str, kind: str = "string") -> None:
    body = XmlNode(kind, {}, text)
    for index, part in enumerate(widget.body):
        if isinstance(part, Attribute) and part.name == name:
            widget.body[index] = Attribute({"name": name}, body)
            return
    widget.body.append(Attribute({"name": name}, body))


def iter_nodes(doc: Document) -> Iterator[Node]:
    def walk_widget(widget: Widget) -> Iterator[Node]:
        yield widget
        for part in widget.body:
            if isinstance(part, Layout):
                yield from walk_layout(part)
            elif isinstance(part, Widget):
                yield from walk_widget(part)
            elif isinstance(part, Action):
                yield part

    def walk_layout(layout: Layout) -> Iterator[Node]:
        yield layout
        for part in layout.body:
            if isinstance(part, LayoutItem):
                yield part
                for child in part.body:
                    if isinstance(child, Widget):
                        yield from walk_widget(child)
                    elif isinstance(child, Layout):
                        yield from walk_layout(child)
                    elif isinstance(child, Spacer):
                        yield child

    yield from walk_widget(doc.root)


def find_node(doc: Document, node_id: str):
    for node in iter_nodes(doc):
        if getattr(node, "id", None) == node_id:
            return node
    return None


def locate(doc: Document, node_id: str):
    """Return (parent_node, index) for a node that lives in some body list."""

    found = []

    def scan(parent) -> None:
        body = getattr(parent, "body", None)
        if not isinstance(body, list) or found:
            return
        for index, part in enumerate(body):
            if getattr(part, "id", None) == node_id:
                found.append((parent, index))
                return
            scan(part)
            if found:
                return

    scan(doc.root)
    if not found:
        return None
    return found[0]


def iter_widgets(doc: Document) -> Iterator[Widget]:
    for node in iter_nodes(doc):
        if isinstance(node, Widget):
            yield node


def all_names(doc: Document) -> set[str]:
    names = set()
    for node in iter_nodes(doc):
        if isinstance(node, Widget) and node.object_name:
            names.add(node.object_name)
        elif isinstance(node, Layout) and node.object_name:
            names.add(node.object_name)
        elif isinstance(node, Spacer) and node.name:
            names.add(node.name)
        elif isinstance(node, Action) and node.name:
            names.add(node.name)
    return names


def unique_name(doc: Document, base: str) -> str:
    names = all_names(doc)
    if base not in names:
        return base
    index = 2
    while f"{base}_{index}" in names:
        index += 1
    return f"{base}_{index}"


def class_decl(doc: Document) -> Optional[ClassDecl]:
    for part in list(doc.header) + list(doc.footer):
        if isinstance(part, ClassDecl):
            return part
    return None


def form_class_name(doc: Document) -> str:
    decl = class_decl(doc)
    if decl and decl.name:
        return decl.name
    return doc.root.object_name or "Form"


def tabstops_of(doc: Document) -> Optional[TabStops]:
    for part in doc.footer:
        if isinstance(part, TabStops):
            return part
    return None


def connections_of(doc: Document) -> Optional[ConnectionList]:
    for part in doc.footer:
        if isinstance(part, ConnectionList):
            return part
    return None


def ensure_tabstops(doc: Document) -> TabStops:
    existing = tabstops_of(doc)
    if existing is not None:
        return existing
    block = TabStops([])
    doc.footer.insert(0, block)
    return block


def ensure_connections(doc: Document) -> ConnectionList:
    existing = connections_of(doc)
    if existing is not None:
        return existing
    block = ConnectionList([])
    doc.footer.append(block)
    return block


def insert_layout_item(layout: Layout, index: int, item: LayoutItem) -> None:
    items = layout_items(layout)
    if index >= len(items) or not items:
        layout.body.append(item)
        return
    target = items[min(max(index, 0), len(items) - 1)]
    layout.body.insert(layout.body.index(target), item)


def visual_children(widget: Widget) -> list:
    """Widgets, spacers, and nested layouts in visual order."""

    layout = widget_layout(widget)
    ordered = []
    if layout is not None:
        for item in layout_items(layout):
            content = item_content(item)
            if content is not None:
                ordered.append(content)
    else:
        ordered.extend(child_widgets(widget))
    return ordered


def reading_order(widget: Widget) -> list[str]:
    names: list[str] = []

    def visit_widget(node: Widget) -> None:
        if node.class_name in INPUT_CLASSES and node.object_name:
            names.append(node.object_name)
        layout = widget_layout(node)
        if layout is not None:
            visit_layout(layout)
        else:
            for child in child_widgets(node):
                visit_widget(child)

    def visit_layout(layout: Layout) -> None:
        for item in layout_items(layout):
            content = item_content(item)
            if isinstance(content, Widget):
                visit_widget(content)
            elif isinstance(content, Layout):
                visit_layout(content)

    visit_widget(widget)
    return names


def effective_tab_order(doc: Document) -> list[str]:
    stops = tabstops_of(doc)
    if stops and stops.names:
        return list(stops.names)
    return reading_order(doc.root)


def problems(doc: Document) -> list[str]:
    found = []
    seen: dict[str, int] = {}
    for widget in iter_widgets(doc):
        name = widget.object_name
        if not valid_identifier(name):
            found.append(f"'{name or '(blank)'}' is not a Python identifier")
        seen[name] = seen.get(name, 0) + 1
        buddy = get_property(widget, "buddy")
        if buddy is not None and buddy.body.tag == "cstring":
            target = buddy.body.text
            if target and not any(w.object_name == target for w in iter_widgets(doc)):
                found.append(f"'{name}' buddies missing widget '{target}'")
    for name, count in seen.items():
        if name and count > 1:
            found.append(f"'{name}' is used {count} times")
    known = {w.object_name for w in iter_widgets(doc)}
    stops = tabstops_of(doc)
    if stops:
        for name in stops.names:
            if name not in known:
                found.append(f"tab stop '{name}' does not match a widget")
    links = connections_of(doc)
    if links:
        for link in links.items:
            if link.sender not in known and link.sender != doc.root.object_name:
                found.append(f"connection sender '{link.sender}' is missing")
            if link.receiver not in known and link.receiver != doc.root.object_name:
                found.append(f"connection receiver '{link.receiver}' is missing")
    return found


def structure(widget: Widget):
    """Observable tree used by command tests. Ids are not part of it."""

    layout = widget_layout(widget)
    props = tuple(
        (prop.name, prop.body.tag, prop.body.text, tuple(sorted(prop.body.attrib.items())))
        for prop in properties_of(widget)
    )
    attrs = tuple((attr.name, attr.body.tag, attr.body.text) for attr in attributes_of(widget))
    children = []
    if layout is not None:
        for item in layout_items(layout):
            content = item_content(item)
            cell = tuple(sorted(item.attrib.items()))
            if isinstance(content, Widget):
                children.append(("widget", cell, structure(content)))
            elif isinstance(content, Spacer):
                children.append(("spacer", cell, content.name))
            elif isinstance(content, Layout):
                children.append(("layout", cell, content.class_name, content.object_name))
            else:
                children.append(("empty", cell))
    for child in child_widgets(widget):
        children.append(("child", structure(child)))
    layout_name = None if layout is None else (layout.class_name, layout.object_name)
    return (widget.class_name, widget.object_name, props, attrs, layout_name, tuple(children))


def document_signature(doc: Document):
    stops = tabstops_of(doc)
    links = connections_of(doc)
    link_sig = ()
    if links:
        link_sig = tuple((c.sender, c.signal, c.receiver, c.slot) for c in links.items)
    stop_sig = tuple(stops.names) if stops else ()
    return (form_class_name(doc), structure(doc.root), stop_sig, link_sig)


def _take_name(reserved: set[str], base: str) -> str:
    if base not in reserved:
        reserved.add(base)
        return base
    index = 2
    while f"{base}_{index}" in reserved:
        index += 1
    name = f"{base}_{index}"
    reserved.add(name)
    return name


def _clone_part(doc: Document, part, renames: dict[str, str], reserved: set[str]):
    if isinstance(part, Widget):
        return _clone_widget(doc, part, renames, reserved)
    if isinstance(part, Layout):
        old = part.object_name
        cloned = Layout(
            id=doc.alloc(),
            class_name=part.class_name,
            object_name=_take_name(reserved, old or default_object_name(part.class_name)),
            attrib=dict(part.attrib),
            body=[_clone_part(doc, child, renames, reserved) for child in part.body],
        )
        if old and old != cloned.object_name:
            renames[old] = cloned.object_name
        return cloned
    if isinstance(part, LayoutItem):
        return LayoutItem(
            id=doc.alloc(),
            attrib=dict(part.attrib),
            body=[_clone_part(doc, child, renames, reserved) for child in part.body],
        )
    if isinstance(part, Spacer):
        cloned = Spacer(
            id=doc.alloc(),
            name=_take_name(reserved, part.name or "spacer"),
            attrib=dict(part.attrib),
            body=copy.deepcopy(part.body),
        )
        return cloned
    if isinstance(part, Action):
        old = part.name
        cloned = Action(
            id=doc.alloc(),
            name=_take_name(reserved, old or "action"),
            attrib=dict(part.attrib),
            body=copy.deepcopy(part.body),
        )
        if old and old != cloned.name:
            renames[old] = cloned.name
        return cloned
    return copy.deepcopy(part)


def _clone_widget(doc: Document, widget: Widget, renames: dict[str, str], reserved: set[str]) -> Widget:
    old = widget.object_name
    cloned = Widget(
        id=doc.alloc(),
        class_name=widget.class_name,
        object_name=_take_name(reserved, old or default_object_name(widget.class_name)),
        attrib=dict(widget.attrib),
        body=[],
    )
    if old and old != cloned.object_name:
        renames[old] = cloned.object_name
    cloned.body = [_clone_part(doc, part, renames, reserved) for part in widget.body]
    return cloned


def _rewrite_names(node, renames: dict[str, str]) -> None:
    if not renames:
        return
    if isinstance(node, Widget):
        for part in node.body:
            _rewrite_names(part, renames)
    elif isinstance(node, Layout):
        for part in node.body:
            _rewrite_names(part, renames)
    elif isinstance(node, LayoutItem):
        for part in node.body:
            _rewrite_names(part, renames)
    elif isinstance(node, (Spacer, Action)):
        for part in node.body:
            if isinstance(part, Property) and part.body.tag == "cstring":
                part.body.text = renames.get(part.body.text, part.body.text)
    elif isinstance(node, Property) and node.body.tag == "cstring":
        node.body.text = renames.get(node.body.text, node.body.text)
    elif isinstance(node, ActionRef):
        node.name = renames.get(node.name, node.name)
    elif isinstance(node, ZOrder):
        node.name = renames.get(node.name, node.name)


def clone_widget(doc: Document, widget: Widget) -> Widget:
    renames: dict[str, str] = {}
    cloned = _clone_widget(doc, widget, renames, all_names(doc))
    _rewrite_names(cloned, renames)
    return cloned


def make_widget(doc: Document, class_name: str, name: Optional[str] = None) -> Widget:
    object_name = name or unique_name(doc, default_object_name(class_name))
    return Widget(id=doc.alloc(), class_name=class_name, object_name=object_name)


def make_layout(doc: Document, class_name: str, name: Optional[str] = None) -> Layout:
    object_name = name or unique_name(doc, default_object_name(class_name))
    return Layout(id=doc.alloc(), class_name=class_name, object_name=object_name)


def make_spacer(doc: Document, orientation: str) -> Spacer:
    vertical = orientation == "Qt::Vertical"
    name = unique_name(doc, "verticalSpacer" if vertical else "horizontalSpacer")
    spacer = Spacer(id=doc.alloc(), name=name)
    spacer.body.append(prop_enum("orientation", orientation))
    hint = prop_size("sizeHint", 20 if vertical else 40, 40 if vertical else 20)
    hint.attrib["stdset"] = "0"
    spacer.body.append(hint)
    return spacer


def make_item(doc: Document, content, **attrib: str) -> LayoutItem:
    item = LayoutItem(id=doc.alloc(), attrib={k: str(v) for k, v in attrib.items()})
    item.body.append(content)
    return item


def blank_widget(class_name: str = "QWidget", object_name: str = "Form") -> Document:
    doc = Document(ui_attrib={"version": "4.0"}, header=[], root=Widget("id0", "", ""), footer=[])
    doc.next_id = 1
    root = make_widget(doc, class_name, object_name)
    root.body.append(prop_rect("geometry", 0, 0, 640, 480))
    root.body.append(prop_string("windowTitle", object_name))
    doc.root = root
    doc.header.append(ClassDecl(object_name))
    doc.footer.append(XmlNode("resources"))
    doc.footer.append(ConnectionList())
    return doc


def widget_path(doc: Document, node_id: str) -> list[str]:
    path: list[str] = []

    def walk(widget: Widget, trail: list[str]) -> bool:
        here = trail + [widget.object_name or widget.class_name]
        if widget.id == node_id:
            path.extend(here)
            return True
        layout = widget_layout(widget)
        if layout is not None:
            layout_trail = here + [layout.object_name or layout.class_name]
            if layout.id == node_id:
                path.extend(layout_trail)
                return True
            for item in layout_items(layout):
                content = item_content(item)
                if isinstance(content, Widget) and walk(content, layout_trail):
                    return True
                if isinstance(content, Spacer) and content.id == node_id:
                    path.extend(layout_trail + [content.name])
                    return True
        for child in child_widgets(widget):
            if walk(child, here):
                return True
        return False

    walk(doc.root, [])
    return path


def is_container(widget: Widget) -> bool:
    if widget.class_name in CONTAINER_CLASSES:
        return True
    if widget_layout(widget) is not None:
        return True
    return widget.class_name in {"QMainWindow", "QDialog", "QWizard", "QDockWidget"}
