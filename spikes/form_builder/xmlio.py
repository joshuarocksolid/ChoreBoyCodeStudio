"""Load and save standard Qt 6 .ui XML.

The parser is the boundary. Callers after this module see dataclasses.
Unknown elements stay in the tree and come back out on save.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from spikes.form_builder.defaults import is_default_property
from spikes.form_builder.model import (
    Action,
    ActionRef,
    Attribute,
    ClassDecl,
    Connection,
    ConnectionList,
    Document,
    ItemEntry,
    Layout,
    LayoutItem,
    Property,
    Spacer,
    TabStops,
    Widget,
    XmlNode,
    ZOrder,
)


def _norm_text(text: str | None) -> str:
    if text is None:
        return ""
    if text.strip() == "":
        return ""
    return text


def _parse_xml(el: ET.Element) -> XmlNode:
    return XmlNode(
        tag=el.tag,
        attrib={key: value for key, value in el.attrib.items()},
        text=_norm_text(el.text),
        children=[_parse_xml(child) for child in list(el)],
    )


def _parse_property(el: ET.Element) -> Property:
    children = list(el)
    body = _parse_xml(children[0]) if children else XmlNode("string")
    return Property(attrib={key: value for key, value in el.attrib.items()}, body=body)


def _parse_attribute(el: ET.Element) -> Attribute:
    children = list(el)
    body = _parse_xml(children[0]) if children else XmlNode("string")
    return Attribute(attrib={key: value for key, value in el.attrib.items()}, body=body)


def _parse_spacer(doc: Document, el: ET.Element) -> Spacer:
    spacer = Spacer(
        id=doc.alloc(),
        name=el.attrib.get("name", ""),
        attrib={key: value for key, value in el.attrib.items() if key != "name"},
    )
    for child in list(el):
        if child.tag == "property":
            spacer.body.append(_parse_property(child))
        else:
            spacer.body.append(_parse_xml(child))
    return spacer


def _parse_item(doc: Document, el: ET.Element) -> LayoutItem:
    item = LayoutItem(
        id=doc.alloc(),
        attrib={key: value for key, value in el.attrib.items()},
    )
    for child in list(el):
        if child.tag == "widget":
            item.body.append(_parse_widget(doc, child))
        elif child.tag == "layout":
            item.body.append(_parse_layout(doc, child))
        elif child.tag == "spacer":
            item.body.append(_parse_spacer(doc, child))
        else:
            item.body.append(_parse_xml(child))
    return item


def _parse_layout(doc: Document, el: ET.Element) -> Layout:
    layout = Layout(
        id=doc.alloc(),
        class_name=el.attrib.get("class", "QVBoxLayout"),
        object_name=el.attrib.get("name", ""),
        attrib={key: value for key, value in el.attrib.items() if key not in ("class", "name")},
    )
    for child in list(el):
        if child.tag == "property":
            layout.body.append(_parse_property(child))
        elif child.tag == "item":
            layout.body.append(_parse_item(doc, child))
        else:
            layout.body.append(_parse_xml(child))
    return layout


def _parse_action(doc: Document, el: ET.Element) -> Action:
    action = Action(
        id=doc.alloc(),
        name=el.attrib.get("name", ""),
        attrib={key: value for key, value in el.attrib.items() if key != "name"},
    )
    for child in list(el):
        if child.tag == "property":
            action.body.append(_parse_property(child))
        else:
            action.body.append(_parse_xml(child))
    return action


def _parse_combo_item(el: ET.Element) -> ItemEntry:
    entry = ItemEntry()
    for child in list(el):
        if child.tag == "property":
            entry.body.append(_parse_property(child))
        else:
            entry.body.append(_parse_xml(child))
    return entry


def _parse_widget(doc: Document, el: ET.Element) -> Widget:
    widget = Widget(
        id=doc.alloc(),
        class_name=el.attrib.get("class", "QWidget"),
        object_name=el.attrib.get("name", ""),
        attrib={key: value for key, value in el.attrib.items() if key not in ("class", "name")},
    )
    for child in list(el):
        if child.tag == "property":
            widget.body.append(_parse_property(child))
        elif child.tag == "attribute":
            widget.body.append(_parse_attribute(child))
        elif child.tag == "layout":
            widget.body.append(_parse_layout(doc, child))
        elif child.tag == "widget":
            widget.body.append(_parse_widget(doc, child))
        elif child.tag == "action":
            widget.body.append(_parse_action(doc, child))
        elif child.tag == "addaction":
            widget.body.append(ActionRef(child.attrib.get("name", "")))
        elif child.tag == "zorder":
            widget.body.append(ZOrder(_norm_text(child.text)))
        elif child.tag == "item":
            widget.body.append(_parse_combo_item(child))
        else:
            widget.body.append(_parse_xml(child))
    return widget


def _parse_connections(el: ET.Element) -> ConnectionList:
    block = ConnectionList(attrib={key: value for key, value in el.attrib.items()})
    for child in list(el):
        if child.tag != "connection":
            block.items.append(
                Connection("", "", "", "", extras=[_parse_xml(child)])
            )
            continue
        fields = {part.tag: _norm_text(part.text) for part in list(child) if part.tag != "hints"}
        hints = []
        extras = []
        for part in list(child):
            if part.tag == "hints":
                hints = [_parse_xml(hint) for hint in list(part)]
            elif part.tag not in ("sender", "signal", "receiver", "slot"):
                extras.append(_parse_xml(part))
        block.items.append(
            Connection(
                sender=fields.get("sender", ""),
                signal=fields.get("signal", ""),
                receiver=fields.get("receiver", ""),
                slot=fields.get("slot", ""),
                hints=hints,
                extras=extras,
            )
        )
    return block


def load_ui(text: str) -> Document:
    root_el = ET.fromstring(text)
    if root_el.tag != "ui":
        raise ValueError("root element is not <ui>")
    doc = Document(
        ui_attrib={key: value for key, value in root_el.attrib.items()},
        header=[],
        root=Widget("pending", "QWidget", ""),
        footer=[],
    )
    seen_root = False
    for child in list(root_el):
        if child.tag == "widget" and not seen_root:
            doc.root = _parse_widget(doc, child)
            seen_root = True
        elif child.tag == "class":
            target = doc.footer if seen_root else doc.header
            target.append(ClassDecl(_norm_text(child.text)))
        elif child.tag == "tabstops":
            names = [_norm_text(stop.text) for stop in list(child) if stop.tag == "tabstop"]
            doc.footer.append(TabStops(names))
        elif child.tag == "connections":
            doc.footer.append(_parse_connections(child))
        else:
            target = doc.footer if seen_root else doc.header
            target.append(_parse_xml(child))
    if not seen_root:
        raise ValueError("ui file has no root widget")
    return doc


def load_path(path: str) -> Document:
    with open(path, "r", encoding="utf-8") as handle:
        return load_ui(handle.read())


def _attr_text(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _text(value: str) -> str:
    return escape(value)


def _format_attrs(pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return ""
    return "".join(f' {key}="{_attr_text(value)}"' for key, value in pairs)


def _ordered_attrs(attrib: dict[str, str], first: list[str]) -> list[tuple[str, str]]:
    pairs = []
    used = set()
    for key in first:
        if key in attrib:
            pairs.append((key, attrib[key]))
            used.add(key)
    for key in sorted(attrib):
        if key not in used:
            pairs.append((key, attrib[key]))
    return pairs


def _write_xml(node: XmlNode, indent: int) -> str:
    pad = " " * indent
    attrs = _format_attrs(_ordered_attrs(node.attrib, []))
    if not node.children and node.text == "":
        return f"{pad}<{node.tag}{attrs}/>\n"
    if not node.children:
        return f"{pad}<{node.tag}{attrs}>{_text(node.text)}</{node.tag}>\n"
    inner = "".join(_write_xml(child, indent + 1) for child in node.children)
    text = f"{_text(node.text)}" if node.text else ""
    if text and not node.text.startswith("\n"):
        return f"{pad}<{node.tag}{attrs}>{text}\n{inner}{pad}</{node.tag}>\n"
    return f"{pad}<{node.tag}{attrs}>\n{inner}{pad}</{node.tag}>\n"


def _write_property(prop: Property, indent: int, class_name: str = "") -> str:
    if class_name and is_default_property(class_name, prop):
        return ""
    pad = " " * indent
    attrs = _format_attrs(_ordered_attrs(prop.attrib, ["name", "stdset"]))
    inner = _write_xml(prop.body, indent + 1)
    return f"{pad}<property{attrs}>\n{inner}{pad}</property>\n"


def _write_attribute(attr: Attribute, indent: int) -> str:
    pad = " " * indent
    attrs = _format_attrs(_ordered_attrs(attr.attrib, ["name"]))
    inner = _write_xml(attr.body, indent + 1)
    return f"{pad}<attribute{attrs}>\n{inner}{pad}</attribute>\n"


def _write_part(part, indent: int, class_name: str = "") -> str:
    if isinstance(part, Property):
        return _write_property(part, indent, class_name)
    if isinstance(part, Attribute):
        return _write_attribute(part, indent)
    if isinstance(part, Layout):
        return _write_layout(part, indent)
    if isinstance(part, Widget):
        return _write_widget(part, indent)
    if isinstance(part, LayoutItem):
        return _write_item(part, indent)
    if isinstance(part, Spacer):
        return _write_spacer(part, indent)
    if isinstance(part, Action):
        return _write_action(part, indent)
    if isinstance(part, ActionRef):
        pad = " " * indent
        return f'{pad}<addaction name="{_attr_text(part.name)}"/>\n'
    if isinstance(part, ZOrder):
        pad = " " * indent
        return f"{pad}<zorder>{_text(part.name)}</zorder>\n"
    if isinstance(part, ItemEntry):
        pad = " " * indent
        inner = "".join(_write_part(child, indent + 1, class_name) for child in part.body)
        return f"{pad}<item>\n{inner}{pad}</item>\n"
    if isinstance(part, XmlNode):
        return _write_xml(part, indent)
    raise TypeError(f"cannot write {type(part).__name__}")


def _write_spacer(spacer: Spacer, indent: int) -> str:
    pad = " " * indent
    pairs = [("name", spacer.name)] + _ordered_attrs(spacer.attrib, [])
    attrs = _format_attrs(pairs)
    inner = "".join(_write_part(part, indent + 1, "") for part in spacer.body)
    if not inner:
        return f"{pad}<spacer{attrs}/>\n"
    return f"{pad}<spacer{attrs}>\n{inner}{pad}</spacer>\n"


def _write_item(item: LayoutItem, indent: int) -> str:
    pad = " " * indent
    attrs = _format_attrs(
        _ordered_attrs(item.attrib, ["row", "column", "rowspan", "colspan", "alignment"])
    )
    inner = "".join(_write_part(part, indent + 1) for part in item.body)
    if not inner:
        return f"{pad}<item{attrs}/>\n"
    return f"{pad}<item{attrs}>\n{inner}{pad}</item>\n"


def _write_layout(layout: Layout, indent: int) -> str:
    pad = " " * indent
    pairs = [("class", layout.class_name), ("name", layout.object_name)]
    pairs.extend(_ordered_attrs(layout.attrib, []))
    attrs = _format_attrs(pairs)
    inner = "".join(_write_part(part, indent + 1, layout.class_name) for part in layout.body)
    if not inner:
        return f"{pad}<layout{attrs}/>\n"
    return f"{pad}<layout{attrs}>\n{inner}{pad}</layout>\n"


def _write_action(action: Action, indent: int) -> str:
    pad = " " * indent
    pairs = [("name", action.name)] + _ordered_attrs(action.attrib, [])
    attrs = _format_attrs(pairs)
    inner = "".join(_write_part(part, indent + 1, "QAction") for part in action.body)
    if not inner:
        return f"{pad}<action{attrs}/>\n"
    return f"{pad}<action{attrs}>\n{inner}{pad}</action>\n"


def _write_widget(widget: Widget, indent: int) -> str:
    pad = " " * indent
    pairs = [("class", widget.class_name), ("name", widget.object_name)]
    pairs.extend(_ordered_attrs(widget.attrib, []))
    attrs = _format_attrs(pairs)
    inner = "".join(_write_part(part, indent + 1, widget.class_name) for part in widget.body)
    if not inner:
        return f"{pad}<widget{attrs}/>\n"
    return f"{pad}<widget{attrs}>\n{inner}{pad}</widget>\n"


def _write_footer(part, indent: int) -> str:
    pad = " " * indent
    if isinstance(part, ClassDecl):
        return f"{pad}<class>{_text(part.name)}</class>\n"
    if isinstance(part, TabStops):
        inner = "".join(
            f'{pad} <tabstop>{_text(name)}</tabstop>\n' for name in part.names
        )
        return f"{pad}<tabstops>\n{inner}{pad}</tabstops>\n"
    if isinstance(part, ConnectionList):
        chunks = []
        for link in part.items:
            if not link.sender and link.extras:
                chunks.append("".join(_write_xml(extra, indent + 1) for extra in link.extras))
                continue
            body = (
                f"{pad}  <sender>{_text(link.sender)}</sender>\n"
                f"{pad}  <signal>{_text(link.signal)}</signal>\n"
                f"{pad}  <receiver>{_text(link.receiver)}</receiver>\n"
                f"{pad}  <slot>{_text(link.slot)}</slot>\n"
            )
            for extra in link.extras:
                body += _write_xml(extra, indent + 2)
            if link.hints:
                hint_body = "".join(_write_xml(hint, indent + 3) for hint in link.hints)
                body += f"{pad}  <hints>\n{hint_body}{pad}  </hints>\n"
            chunks.append(f"{pad} <connection>\n{body}{pad} </connection>\n")
        attrs = _format_attrs(_ordered_attrs(part.attrib, []))
        if not chunks:
            return f"{pad}<connections{attrs}/>\n"
        return f"{pad}<connections{attrs}>\n{''.join(chunks)}{pad}</connections>\n"
    if isinstance(part, XmlNode):
        return _write_xml(part, indent)
    raise TypeError(f"cannot write footer {type(part).__name__}")


def dump_ui(doc: Document) -> str:
    attrs = _format_attrs(_ordered_attrs(doc.ui_attrib, ["version"]))
    body = "".join(_write_footer(part, 1) for part in doc.header)
    body += _write_widget(doc.root, 1)
    body += "".join(_write_footer(part, 1) for part in doc.footer)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<ui{attrs}>\n{body}</ui>\n'


def save_path(doc: Document, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_ui(doc))
