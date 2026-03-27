"""Read Qt Designer `.ui` XML into `UIModel`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import xml.etree.ElementTree as ET

from app.designer.model import (
    AddActionModel,
    ActionGroupModel,
    ActionModel,
    ButtonGroupModel,
    ConnectionModel,
    CustomWidgetModel,
    LayoutItem,
    LayoutNode,
    PropertyValue,
    ResourceModel,
    SpacerItem,
    UIModel,
    WidgetNode,
    ZOrderModel,
)


def read_ui_file(file_path: str) -> UIModel:
    """Load `.ui` model from file path."""
    source = Path(file_path).read_text(encoding="utf-8")
    return read_ui_string(source)


def read_ui_string(source: str) -> UIModel:
    """Load `.ui` model from XML string payload."""
    root = ET.fromstring(source)
    if root.tag != "ui":
        raise ValueError("Invalid .ui XML: root <ui> element is required.")

    form_class_name = (root.findtext("class") or "").strip()
    if not form_class_name:
        raise ValueError("Invalid .ui XML: <class> value is required.")

    widget_element = root.find("widget")
    if widget_element is None:
        raise ValueError("Invalid .ui XML: top-level <widget> element is required.")

    model = UIModel(
        form_class_name=form_class_name,
        root_widget=_parse_widget(widget_element),
        ui_version=root.attrib.get("version", "4.0"),
        actions=_parse_actions((root, widget_element)),
        action_groups=_parse_action_groups((root, widget_element)),
        add_actions=_parse_add_actions((root, widget_element)),
        zorders=_parse_z_orders((root, widget_element)),
        button_groups=_parse_button_groups((root, widget_element)),
        connections=_parse_connections(root),
        resources=_parse_resources(root),
        tab_stops=_parse_tab_stops(root),
        custom_widgets=_parse_custom_widgets(root),
        unknown_top_level_xml=_parse_unknown_top_level_nodes(root),
    )
    return model


def _parse_widget(element: ET.Element) -> WidgetNode:
    class_name = element.attrib.get("class", "").strip()
    object_name = element.attrib.get("name", "").strip()
    if not class_name or not object_name:
        raise ValueError("Invalid .ui XML: widget must include class and name attributes.")
    properties: dict[str, PropertyValue] = {}
    children: list[WidgetNode] = []
    layout: LayoutNode | None = None
    add_actions: list[AddActionModel] = []
    unknown_children_xml: list[str] = []

    for child in element:
        if child.tag == "property":
            prop_name = child.attrib.get("name", "").strip()
            if prop_name:
                properties[prop_name] = _parse_property(child)
            continue
        if child.tag == "widget":
            children.append(_parse_widget(child))
            continue
        if child.tag == "layout":
            layout = _parse_layout(child)
            continue
        if child.tag in {"action", "actiongroup", "zorder", "buttongroups", "buttongroup"}:
            continue
        if child.tag == "addaction":
            action_name = (child.attrib.get("name") or "").strip()
            if action_name:
                add_actions.append(AddActionModel(name=action_name))
            continue
        unknown_children_xml.append(ET.tostring(child, encoding="unicode"))

    return WidgetNode(
        class_name=class_name,
        object_name=object_name,
        properties=properties,
        children=children,
        layout=layout,
        add_actions=add_actions,
        unknown_children_xml=unknown_children_xml,
    )


def _parse_layout(element: ET.Element) -> LayoutNode:
    class_name = element.attrib.get("class", "").strip()
    object_name = element.attrib.get("name", "").strip()
    if not class_name or not object_name:
        raise ValueError("Invalid .ui XML: layout must include class and name attributes.")
    items: list[LayoutItem] = []
    unknown_children_xml: list[str] = []
    for child in element:
        if child.tag == "item":
            item = _parse_layout_item(child)
            if item is not None:
                items.append(item)
            continue
        unknown_children_xml.append(ET.tostring(child, encoding="unicode"))
    return LayoutNode(
        class_name=class_name,
        object_name=object_name,
        items=items,
        unknown_children_xml=unknown_children_xml,
    )


def _parse_layout_item(element: ET.Element) -> LayoutItem | None:
    attributes = {
        key: value
        for key, value in element.attrib.items()
        if key in {"row", "column", "rowspan", "colspan", "alignment"}
    }
    widget_element = element.find("widget")
    if widget_element is not None:
        return LayoutItem(widget=_parse_widget(widget_element), attributes=attributes)
    layout_element = element.find("layout")
    if layout_element is not None:
        return LayoutItem(layout=_parse_layout(layout_element), attributes=attributes)
    spacer_element = element.find("spacer")
    if spacer_element is not None:
        spacer_name = spacer_element.attrib.get("name", "").strip() or "spacerItem"
        return LayoutItem(spacer=SpacerItem(name=spacer_name), attributes=attributes)
    unknown_xml = [ET.tostring(child, encoding="unicode") for child in list(element)]
    if unknown_xml:
        return LayoutItem(attributes=attributes, unknown_xml=unknown_xml)
    return None


def _parse_property(element: ET.Element) -> PropertyValue:
    if len(element) == 0:
        return PropertyValue(value_type="string", value=(element.text or ""))

    value_element = element[0]
    value_type = value_element.tag
    if value_type == "string":
        return PropertyValue(value_type=value_type, value=value_element.text or "")
    if value_type == "bool":
        return PropertyValue(value_type=value_type, value=(value_element.text or "").strip().lower() == "true")
    if value_type in {"number", "int"}:
        return PropertyValue(value_type=value_type, value=int((value_element.text or "0").strip() or "0"))
    if value_type in {"double", "float"}:
        return PropertyValue(value_type=value_type, value=float((value_element.text or "0").strip() or "0"))
    if value_type == "rect":
        return PropertyValue(value_type=value_type, value=_parse_rect(value_element))
    if value_type == "iconset":
        icon_text = (value_element.text or "").strip()
        if not icon_text:
            icon_text = (value_element.findtext("normaloff") or "").strip()
        return PropertyValue(value_type=value_type, value=icon_text)
    if value_type == "size":
        return PropertyValue(value_type=value_type, value=_parse_size(value_element))
    if value_type == "sizepolicy":
        return PropertyValue(value_type=value_type, value=_parse_size_policy(value_element))
    raw_xml = ET.tostring(value_element, encoding="unicode") if len(value_element) > 0 else None
    return PropertyValue(value_type=value_type, value=value_element.text or "", raw_xml=raw_xml)


def _parse_rect(rect_element: ET.Element) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for field in ("x", "y", "width", "height"):
        field_value = rect_element.findtext(field)
        parsed[field] = int((field_value or "0").strip() or "0")
    return parsed


def _parse_size(size_element: ET.Element) -> dict[str, int]:
    return {
        "width": int((size_element.findtext("width") or "0").strip() or "0"),
        "height": int((size_element.findtext("height") or "0").strip() or "0"),
    }


def _parse_size_policy(size_policy_element: ET.Element) -> dict[str, object]:
    return {
        "hsizetype": (size_policy_element.attrib.get("hsizetype") or "").strip(),
        "vsizetype": (size_policy_element.attrib.get("vsizetype") or "").strip(),
        "horstretch": int((size_policy_element.findtext("horstretch") or "0").strip() or "0"),
        "verstretch": int((size_policy_element.findtext("verstretch") or "0").strip() or "0"),
    }


def _parse_connections(root: ET.Element) -> list[ConnectionModel]:
    container = root.find("connections")
    if container is None:
        return []
    parsed: list[ConnectionModel] = []
    for connection in container.findall("connection"):
        sender = (connection.findtext("sender") or "").strip()
        signal = (connection.findtext("signal") or "").strip()
        receiver = (connection.findtext("receiver") or "").strip()
        slot = (connection.findtext("slot") or "").strip()
        if not sender or not signal or not receiver or not slot:
            continue
        parsed.append(
            ConnectionModel(
                sender=sender,
                signal=signal,
                receiver=receiver,
                slot=slot,
            )
        )
    return parsed


def _parse_resources(root: ET.Element) -> list[ResourceModel]:
    container = root.find("resources")
    if container is None:
        return []
    parsed: list[ResourceModel] = []
    for include in container.findall("include"):
        location = (include.attrib.get("location") or "").strip()
        if not location:
            continue
        parsed.append(ResourceModel(location=location))
    return parsed


def _parse_tab_stops(root: ET.Element) -> list[str]:
    container = root.find("tabstops")
    if container is None:
        return []
    tab_stops: list[str] = []
    for tabstop in container.findall("tabstop"):
        name = (tabstop.text or "").strip()
        if name:
            tab_stops.append(name)
    return tab_stops


def _parse_custom_widgets(root: ET.Element) -> list[CustomWidgetModel]:
    container = root.find("customwidgets")
    if container is None:
        return []
    parsed: list[CustomWidgetModel] = []
    for element in container.findall("customwidget"):
        class_name = (element.findtext("class") or "").strip()
        extends = (element.findtext("extends") or "").strip()
        header = (element.findtext("header") or "").strip()
        if not class_name or not extends:
            continue
        parsed.append(CustomWidgetModel(class_name=class_name, extends=extends, header=header))
    return parsed


def _parse_actions(scopes: Sequence[ET.Element]) -> list[ActionModel]:
    parsed: list[ActionModel] = []
    seen: set[str] = set()
    for scope in scopes:
        for element in scope.findall("action"):
            name = (element.attrib.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            properties: dict[str, PropertyValue] = {}
            add_actions: list[AddActionModel] = []
            unknown_children_xml: list[str] = []
            for child in list(element):
                if child.tag == "property":
                    prop_name = (child.attrib.get("name") or "").strip()
                    if prop_name:
                        properties[prop_name] = _parse_property(child)
                    continue
                if child.tag == "addaction":
                    action_name = (child.attrib.get("name") or "").strip()
                    if action_name:
                        add_actions.append(AddActionModel(name=action_name))
                    continue
                unknown_children_xml.append(ET.tostring(child, encoding="unicode"))
            parsed.append(
                ActionModel(
                    name=name,
                    properties=properties,
                    add_actions=add_actions,
                    unknown_children_xml=unknown_children_xml,
                )
            )
    return parsed


def _parse_action_groups(scopes: Sequence[ET.Element]) -> list[ActionGroupModel]:
    parsed: list[ActionGroupModel] = []
    seen: set[str] = set()
    for scope in scopes:
        for element in scope.findall("actiongroup"):
            name = (element.attrib.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            properties: dict[str, PropertyValue] = {}
            add_actions: list[AddActionModel] = []
            unknown_children_xml: list[str] = []
            for child in list(element):
                if child.tag == "property":
                    prop_name = (child.attrib.get("name") or "").strip()
                    if prop_name:
                        properties[prop_name] = _parse_property(child)
                    continue
                if child.tag in {"addaction", "action"}:
                    action_name = (child.attrib.get("name") or "").strip()
                    if action_name:
                        add_actions.append(AddActionModel(name=action_name))
                    continue
                unknown_children_xml.append(ET.tostring(child, encoding="unicode"))
            parsed.append(
                ActionGroupModel(
                    name=name,
                    properties=properties,
                    add_actions=add_actions,
                    unknown_children_xml=unknown_children_xml,
                )
            )
    return parsed


def _parse_add_actions(scopes: Sequence[ET.Element]) -> list[AddActionModel]:
    parsed: list[AddActionModel] = []
    widget_scope = scopes[1] if len(scopes) > 1 else None
    for scope in scopes:
        for element in scope.findall("addaction"):
            name = (element.attrib.get("name") or "").strip()
            if not name:
                continue
            if widget_scope is not None and scope is widget_scope:
                continue
            parsed.append(AddActionModel(name=name))
    return parsed


def _parse_z_orders(scopes: Sequence[ET.Element]) -> list[ZOrderModel]:
    parsed: list[ZOrderModel] = []
    for scope in scopes:
        for element in scope.findall("zorder"):
            name = (element.text or "").strip()
            if not name:
                continue
            parsed.append(ZOrderModel(name=name))
    return parsed


def _parse_button_groups(scopes: Sequence[ET.Element]) -> list[ButtonGroupModel]:
    parsed: list[ButtonGroupModel] = []
    seen: set[str] = set()
    for scope in scopes:
        direct = list(scope.findall("buttongroup"))
        for container in scope.findall("buttongroups"):
            direct.extend(container.findall("buttongroup"))
        for button_group_element in direct:
            name = (button_group_element.attrib.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            exclusive_attr = (button_group_element.attrib.get("exclusive") or "").strip().lower()
            exclusive: bool | None = None
            if exclusive_attr in {"true", "false"}:
                exclusive = exclusive_attr == "true"
            unknown_children_xml = [
                ET.tostring(child, encoding="unicode")
                for child in list(button_group_element)
            ]
            parsed.append(
                ButtonGroupModel(
                    name=name,
                    exclusive=exclusive,
                    unknown_children_xml=unknown_children_xml,
                )
            )
    return parsed


def _parse_unknown_top_level_nodes(root: ET.Element) -> list[str]:
    known_tags = {
        "class",
        "widget",
        "action",
        "actiongroup",
        "addaction",
        "zorder",
        "buttongroups",
        "buttongroup",
        "tabstops",
        "resources",
        "customwidgets",
        "connections",
    }
    unknown_nodes: list[str] = []
    for child in list(root):
        if child.tag in known_tags:
            continue
        unknown_nodes.append(ET.tostring(child, encoding="unicode"))
    return unknown_nodes

