"""Write `UIModel` to Qt Designer `.ui` XML."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from app.designer.model import (
    ConnectionModel,
    CustomWidgetModel,
    LayoutItem,
    LayoutNode,
    PropertyValue,
    ResourceModel,
    UIModel,
    WidgetNode,
)


def write_ui_file(model: UIModel, file_path: str) -> None:
    """Serialize model and write XML payload to disk."""
    Path(file_path).write_text(write_ui_string(model), encoding="utf-8")


def write_ui_string(model: UIModel) -> str:
    """Serialize model into deterministic `.ui` XML string."""
    ui_element = ET.Element("ui", attrib={"version": model.ui_version})
    class_element = ET.SubElement(ui_element, "class")
    class_element.text = model.form_class_name

    ui_element.append(_build_widget(model.root_widget))
    ui_element.append(_build_tab_stops(model.tab_stops))
    ui_element.append(_build_resources(model.resources))
    ui_element.append(_build_custom_widgets(model.custom_widgets))
    ui_element.append(_build_connections(model.connections))
    _indent_xml(ui_element)
    xml_body = ET.tostring(ui_element, encoding="unicode")
    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + xml_body + "\n"


def _build_widget(widget: WidgetNode) -> ET.Element:
    element = ET.Element("widget", attrib={"class": widget.class_name, "name": widget.object_name})
    for prop_name in sorted(widget.properties):
        element.append(_build_property(prop_name, widget.properties[prop_name]))
    for child in widget.children:
        element.append(_build_widget(child))
    if widget.layout is not None:
        element.append(_build_layout(widget.layout))
    return element


def _build_layout(layout: LayoutNode) -> ET.Element:
    element = ET.Element("layout", attrib={"class": layout.class_name, "name": layout.object_name})
    for item in layout.items:
        item_element = ET.SubElement(element, "item")
        _append_layout_item(item_element, item)
    return element


def _append_layout_item(item_element: ET.Element, item: LayoutItem) -> None:
    if item.widget is not None:
        item_element.append(_build_widget(item.widget))
        return
    if item.layout is not None:
        item_element.append(_build_layout(item.layout))
        return
    if item.spacer is not None:
        ET.SubElement(item_element, "spacer", attrib={"name": item.spacer.name})


def _build_property(property_name: str, property_value: PropertyValue) -> ET.Element:
    property_element = ET.Element("property", attrib={"name": property_name})
    value_type = property_value.value_type
    value = property_value.value
    if value_type == "rect" and isinstance(value, dict):
        rect_element = ET.SubElement(property_element, "rect")
        for field in ("x", "y", "width", "height"):
            field_element = ET.SubElement(rect_element, field)
            field_element.text = str(int(value.get(field, 0)))
        return property_element
    if value_type == "iconset":
        icon_element = ET.SubElement(property_element, "iconset")
        normal_off = ET.SubElement(icon_element, "normaloff")
        normal_off.text = str(value)
        return property_element

    value_element = ET.SubElement(property_element, value_type)
    if value_type == "bool":
        value_element.text = "true" if bool(value) else "false"
    else:
        value_element.text = str(value)
    return property_element


def _build_resources(resources: list[ResourceModel]) -> ET.Element:
    resources_element = ET.Element("resources")
    for resource in resources:
        ET.SubElement(resources_element, "include", attrib={"location": resource.location})
    return resources_element


def _build_connections(connections: list[ConnectionModel]) -> ET.Element:
    connections_element = ET.Element("connections")
    for connection in connections:
        connection_element = ET.SubElement(connections_element, "connection")
        sender = ET.SubElement(connection_element, "sender")
        sender.text = connection.sender
        signal = ET.SubElement(connection_element, "signal")
        signal.text = connection.signal
        receiver = ET.SubElement(connection_element, "receiver")
        receiver.text = connection.receiver
        slot = ET.SubElement(connection_element, "slot")
        slot.text = connection.slot
    return connections_element


def _build_tab_stops(tab_stops: list[str]) -> ET.Element:
    tab_stops_element = ET.Element("tabstops")
    for tab_stop in tab_stops:
        tab_stop_element = ET.SubElement(tab_stops_element, "tabstop")
        tab_stop_element.text = tab_stop
    return tab_stops_element


def _build_custom_widgets(custom_widgets: list[CustomWidgetModel]) -> ET.Element:
    custom_widgets_element = ET.Element("customwidgets")
    for custom_widget in custom_widgets:
        custom_widget_element = ET.SubElement(custom_widgets_element, "customwidget")
        class_element = ET.SubElement(custom_widget_element, "class")
        class_element.text = custom_widget.class_name
        extends_element = ET.SubElement(custom_widget_element, "extends")
        extends_element.text = custom_widget.extends
        header_element = ET.SubElement(custom_widget_element, "header")
        header_element.text = custom_widget.header
    return custom_widgets_element


def _indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + (" " * (level * 1))
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = indent + " "
        for child in children:
            _indent_xml(child, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = indent
    if level > 0 and (not element.tail or not element.tail.strip()):
        element.tail = indent

