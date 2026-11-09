"""Actions, menus, toolbars and where an action is used (UX-MAIN-003 ... 012).

Pure: reads the document and never edits it. A "host" is a widget that holds
``<addaction>`` references: a menu bar, a menu, a toolbar, or any widget whose
context menu lists actions (UX-MAIN-017).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb03x_main as _fb03x_main  # noqa: F401
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import ActionNode, ActionRefNode, Node, WidgetNode
from app.features.form_builder.engine.ui4.values import StringValue

SEPARATOR = "separator"

_SYMBOLS = re.compile(r"[^0-9A-Za-z]+")


@dataclass(frozen=True)
class Place:
    """One reference to an action: the host and the reference node."""

    host: NodeId
    host_name: str
    label: str
    ref: NodeId


@dataclass(frozen=True)
class ActionInfo:
    id: NodeId
    name: str
    text: str
    shortcut: str
    has_icon: bool
    places: Tuple[Place, ...]
    in_connection: bool
    group: Optional[str]

    @property
    def used(self) -> bool:
        return bool(self.places) or self.in_connection

    @property
    def used_line(self) -> str:
        """The caption under an action row: "File menu, toolBar" or "Not used"."""
        if not self.places:
            return "" if self.in_connection else "Not used"
        labels: List[str] = []
        for place in self.places:
            if place.label not in labels:
                labels.append(place.label)
        return ", ".join(labels)


@dataclass(frozen=True)
class Entry:
    """One row of a menu, menu bar or toolbar, in visual order.

    ``kind`` is ``action``, ``menu`` or ``separator``. ``target`` is the action
    or the menu widget (None for a separator or a dangling reference).
    """

    ref: NodeId
    kind: str
    name: str
    target: Optional[NodeId]
    text: str


def plain_text(text: str) -> str:
    """Text without mnemonic marks: ``&File`` is File, ``&&`` is one ampersand."""
    out: List[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "&":
            if index + 1 < len(text) and text[index + 1] == "&":
                out.append("&")
                index += 2
                continue
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def name_from_text(prefix: str, text: str) -> str:
    """``action`` + UpperCamel of the text: ``actionPrint_receipt`` (UX-MAIN-006)."""
    words = _SYMBOLS.sub("_", plain_text(text)).strip("_")
    if not words:
        return prefix
    return prefix + words[0].upper() + words[1:]


def is_main_window(doc: UiDocument) -> bool:
    return doc.root.class_name == "QMainWindow"


def root_class(doc: UiDocument) -> str:
    return doc.root.class_name


def text_of(node: Node, prop: str = "text") -> str:
    value = node.value(prop)
    if isinstance(value, StringValue):
        return value.text
    return ""


def widget_class(node: Node) -> str:
    return node.field("class_name") if isinstance(node.field("class_name"), str) else ""  # type: ignore[return-value]


def parts(doc: UiDocument) -> Dict[str, Tuple[WidgetNode, ...]]:
    """The main-window parts under the root: menubar, toolbar, statusbar, central."""
    found: Dict[str, List[WidgetNode]] = {"menubar": [], "toolbar": [], "statusbar": [], "central": []}
    for child in doc.root.child_widgets:
        cls = child.class_name
        if cls == "QMenuBar":
            found["menubar"].append(child)
        elif cls == "QToolBar":
            found["toolbar"].append(child)
        elif cls == "QStatusBar":
            found["statusbar"].append(child)
        elif cls == "QDockWidget":
            continue
        else:
            found["central"].append(child)
    return {key: tuple(value) for key, value in found.items()}


def is_host(node: Node) -> bool:
    return isinstance(node, WidgetNode)


def host_label(doc: UiDocument, host: NodeId) -> str:
    """How a place is named in the used-in line: "File menu", "toolBar", "ok button"."""
    node = doc.node(host)
    if not isinstance(node, WidgetNode):
        return ""
    if node.class_name == "QMenu":
        title = plain_text(text_of(node, "title"))
        return "%s menu" % title if title else "%s menu" % node.object_name
    if node.class_name == "QToolBar":
        title = text_of(node, "windowTitle")
        return title if title else node.object_name
    return node.object_name


def host_phrase(doc: UiDocument, host: NodeId) -> str:
    """The place in an undo name: "the File menu" or "toolBar"."""
    node = doc.node(host)
    if isinstance(node, WidgetNode) and node.class_name in ("QMenu", "QMenuBar"):
        return "the %s" % host_label(doc, host) if node.class_name == "QMenu" else "the menu bar"
    return host_label(doc, host)


def refs_of(doc: UiDocument, host: NodeId) -> Tuple[ActionRefNode, ...]:
    node = doc.node(host)
    return tuple(ref for ref in node.children("add_actions") if isinstance(ref, ActionRefNode))


def _nodes_of(doc: UiDocument, ids: Tuple[NodeId, ...]) -> Tuple[Node, ...]:
    return tuple(node for node in (doc.get(item) for item in ids) if node is not None)


def all_actions(doc: UiDocument) -> Tuple[ActionNode, ...]:
    """Every action in document order: root actions first, then those inside groups.

    The walk is kept until the structure moves. Its answer is ids, read back as nodes.
    """
    ids = doc.structure_memo(
        "actions.all_actions",
        lambda: tuple(node.id for node in doc.iter_preorder() if isinstance(node, ActionNode)),
    )
    return tuple(node for node in _nodes_of(doc, ids) if isinstance(node, ActionNode))


def group_of(doc: UiDocument, action: ActionNode) -> Optional[str]:
    parent = doc.parent(action.id)
    if parent is not None and parent.kind == "actiongroup":
        name = parent.field("name")
        return name if isinstance(name, str) else None
    return None


def action_groups(doc: UiDocument) -> Tuple[Node, ...]:
    ids = doc.structure_memo(
        "actions.action_groups",
        lambda: tuple(node.id for node in doc.iter_preorder() if node.kind == "actiongroup"),
    )
    return _nodes_of(doc, ids)


def _places_by_name(doc: UiDocument) -> Dict[str, List[Place]]:
    """Kept until the structure moves. Callers copy what they keep."""
    return doc.structure_memo("actions.places_by_name", lambda: _walk_places(doc))


def _walk_places(doc: UiDocument) -> Dict[str, List[Place]]:
    found: Dict[str, List[Place]] = {}
    for node in doc.iter_preorder():
        if not isinstance(node, ActionRefNode):
            continue
        host = doc.parent(node.id)
        if host is None:
            continue
        found.setdefault(node.name, []).append(
            Place(host.id, host.field("object_name") if isinstance(host.field("object_name"), str) else "", host_label(doc, host.id), node.id)  # type: ignore[arg-type]
        )
    return found


def _connected_names(doc: UiDocument) -> frozenset:
    names = set()
    for node in doc.connections():
        for field in ("sender", "receiver"):
            value = node.field(field)
            if isinstance(value, str):
                names.add(value)
    return frozenset(names)


def list_actions(doc: UiDocument) -> Tuple[ActionInfo, ...]:
    places = _places_by_name(doc)
    connected = _connected_names(doc)
    out: List[ActionInfo] = []
    for node in all_actions(doc):
        shortcut = node.value("shortcut")
        out.append(
            ActionInfo(
                id=node.id,
                name=node.name,
                text=text_of(node),
                shortcut=shortcut.text if isinstance(shortcut, StringValue) else "",
                has_icon=node.prop("icon") is not None,
                places=tuple(places.get(node.name, ())),
                in_connection=node.name in connected,
                group=group_of(doc, node),
            )
        )
    return tuple(out)


def action_info(doc: UiDocument, action: NodeId) -> Optional[ActionInfo]:
    for info in list_actions(doc):
        if info.id == action:
            return info
    return None


def places_of(doc: UiDocument, name: str) -> Tuple[Place, ...]:
    return tuple(_places_by_name(doc).get(name, ()))


def is_used(doc: UiDocument, name: str) -> bool:
    if name in _connected_names(doc):
        return True
    return bool(_places_by_name(doc).get(name))


def entries(doc: UiDocument, host: NodeId) -> Tuple[Entry, ...]:
    """The references of ``host`` in visual order, resolved to what they name."""
    out: List[Entry] = []
    for ref in refs_of(doc, host):
        if ref.name == SEPARATOR:
            out.append(Entry(ref.id, "separator", SEPARATOR, None, ""))
            continue
        found = doc.by_name(ref.name)
        target = doc.get(found[0]) if found else None
        if isinstance(target, ActionNode):
            out.append(Entry(ref.id, "action", ref.name, target.id, text_of(target)))
        elif isinstance(target, WidgetNode) and target.class_name == "QMenu":
            out.append(Entry(ref.id, "menu", ref.name, target.id, text_of(target, "title")))
        else:
            out.append(Entry(ref.id, "action", ref.name, None, ref.name))
    return tuple(out)


def menu_widgets(doc: UiDocument) -> Tuple[WidgetNode, ...]:
    ids = doc.structure_memo(
        "actions.menu_widgets",
        lambda: tuple(node.id for node in doc.iter_widgets() if node.class_name == "QMenu"),
    )
    return tuple(node for node in _nodes_of(doc, ids) if isinstance(node, WidgetNode))


def menus_below(doc: UiDocument, menu: NodeId) -> Tuple[NodeId, ...]:
    """``menu`` and every submenu under it, depth first."""
    out: List[NodeId] = [menu]
    for entry in entries(doc, menu):
        if entry.kind == "menu" and entry.target is not None:
            out.extend(menus_below(doc, entry.target))
    return tuple(out)


def button_groups(doc: UiDocument) -> Tuple[Tuple[str, NodeId, Tuple[NodeId, ...]], ...]:
    """``(name, group node, member buttons)`` for each form button group."""
    members: Dict[str, List[NodeId]] = {}
    for widget in doc.iter_widgets():
        attr = widget.attr("buttonGroup")
        if attr is not None and isinstance(attr.value, StringValue):
            members.setdefault(attr.value.text, []).append(widget.id)
    out = []
    for node in doc.ui.children("buttongroups"):
        name = node.field("name")
        if isinstance(name, str):
            out.append((name, node.id, tuple(members.get(name, ()))))
    return tuple(out)


def action_wrong_hosts(doc: UiDocument) -> Tuple[Tuple[WidgetNode, WidgetNode], ...]:
    """``(widget, holder)`` for each real widget inside a toolbar or status bar (FB037)."""
    pairs = doc.structure_memo("actions.wrong_hosts", lambda: _wrong_host_ids(doc))
    found: List[Tuple[WidgetNode, WidgetNode]] = []
    for child_id, holder_id in pairs:
        child = doc.get(child_id)
        holder = doc.get(holder_id)
        if isinstance(child, WidgetNode) and isinstance(holder, WidgetNode):
            found.append((child, holder))
    return tuple(found)


def _wrong_host_ids(doc: UiDocument) -> Tuple[Tuple[NodeId, NodeId], ...]:
    found: List[Tuple[NodeId, NodeId]] = []
    for holder in doc.iter_widgets():
        if holder.class_name not in ("QToolBar", "QStatusBar"):
            continue
        for child in holder.child_widgets:
            found.append((child.id, holder.id))
    return tuple(found)


def main_window_diagnostics(doc: UiDocument) -> Tuple[FormDiagnostic, ...]:
    """FB036 for each unused action and FB037 for each widget inside a toolbar or status bar."""
    found: List[FormDiagnostic] = []
    info36 = CODES["FB036"]
    for info in list_actions(doc):
        if info.used:
            continue
        shown = plain_text(info.text) or info.name
        found.append(
            FormDiagnostic(
                code=info36.code,
                severity=info36.severity,
                message="The action %s isn't on any menu, toolbar or widget." % shown,
                location=DiagnosticLocation(node_id=info.id, object_name=info.name),
                source="main_window",
            )
        )
    info37 = CODES["FB037"]
    for widget, holder in action_wrong_hosts(doc):
        word = "toolbar" if holder.class_name == "QToolBar" else "status bar"
        found.append(
            FormDiagnostic(
                code=info37.code,
                severity=info37.severity,
                message="%s is inside a %s. It won't show where you see it here." % (widget.object_name, word),
                location=DiagnosticLocation(node_id=widget.id, object_name=widget.object_name),
                source="main_window",
            )
        )
    return tuple(found)
