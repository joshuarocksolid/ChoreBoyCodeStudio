"""Small builders for default fragments (Qt-free). Same shapes the drop code already uses."""

from __future__ import annotations

from typing import Callable, Optional, Sequence, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.qtside.insert.catalog._model import WIDGET, Entry
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    EnumValue,
    NumberValue,
    SetValue,
    SizeValue,
    StringValue,
    Value,
)

Slot = Tuple[str, Tuple[NodeSpec, ...]]


def prop(name: str, value: Value) -> PropertyEntry:
    return PropertyEntry("property", name, value)


def text(name: str, value: str) -> PropertyEntry:
    return PropertyEntry("property", name, StringValue(value))


def attr(name: str, value: str) -> PropertyEntry:
    return PropertyEntry("attribute", name, StringValue(value))


def flag(name: str, value: bool) -> PropertyEntry:
    return PropertyEntry("property", name, BoolValue(value))


def number(name: str, value: int) -> PropertyEntry:
    return PropertyEntry("property", name, NumberValue(value))


def enum(name: str, value: str) -> PropertyEntry:
    return PropertyEntry("property", name, EnumValue(value))


def orientation(horizontal: bool) -> PropertyEntry:
    return enum("orientation", "Qt::Horizontal" if horizontal else "Qt::Vertical")


def layout(class_name: str, object_name: str) -> NodeSpec:
    return NodeSpec("layout", None, (("class_name", class_name), ("object_name", object_name)))


def vbox(object_name: str = "verticalLayout") -> NodeSpec:
    return layout("QVBoxLayout", object_name)


def widget(
    class_name: str,
    object_name: str,
    *,
    properties: Sequence[PropertyEntry] = (),
    attributes: Sequence[PropertyEntry] = (),
    layout_spec: Optional[NodeSpec] = None,
    children: Sequence[NodeSpec] = (),
    columns: Sequence[NodeSpec] = (),
) -> NodeSpec:
    slots = []
    if columns:
        slots.append(("columns", tuple(columns)))
    if layout_spec is not None:
        slots.append(("layout", (layout_spec,)))
    if children:
        slots.append(("children", tuple(children)))
    return NodeSpec(
        "widget",
        None,
        (("class_name", class_name), ("object_name", object_name)),
        tuple(properties),
        tuple(attributes),
        tuple(slots),
    )


def container(
    class_name: str,
    object_name: str,
    *,
    properties: Sequence[PropertyEntry] = (),
    children: Sequence[NodeSpec] = (),
) -> NodeSpec:
    """A container that owns a vertical layout (UX-AUTO-001)."""
    return widget(
        class_name,
        object_name,
        properties=properties,
        layout_spec=vbox(),
        children=children,
    )


def page(class_name: str, object_name: str, *, attributes: Sequence[PropertyEntry] = (), properties: Sequence[PropertyEntry] = ()) -> NodeSpec:
    """A page with its own vertical layout: tab, toolbox, stacked and wizard pages."""
    return widget(
        class_name,
        object_name,
        properties=properties,
        attributes=attributes,
        layout_spec=vbox(),
    )


def spacer(object_name: str, horizontal: bool) -> NodeSpec:
    hint = SizeValue(40, 20) if horizontal else SizeValue(20, 40)
    return NodeSpec(
        "spacer",
        None,
        (("name", object_name),),
        (
            orientation(horizontal),
            enum("sizeType", "QSizePolicy::Expanding"),
            PropertyEntry("property", "sizeHint", hint, stdset="0"),
        ),
    )


def header_column(title: str) -> NodeSpec:
    return NodeSpec("header", None, (("axis", "column"),), (text("text", title),))


def standard_buttons(text_value: str) -> PropertyEntry:
    return PropertyEntry("property", "standardButtons", SetValue(text_value))


def fragment(*nodes: NodeSpec, customwidgets: Sequence[NodeSpec] = ()) -> Fragment:
    return Fragment(nodes=tuple(nodes), customwidgets=tuple(customwidgets))


def declaration(class_name: str, extends: str, header: str) -> NodeSpec:
    """A ``customwidget`` declaration as FreeCAD's own forms write it."""
    return NodeSpec(
        "customwidget",
        None,
        (("class_name", class_name), ("extends", extends), ("header", header)),
    )



def leaf(class_name: str, object_name: str, properties: Sequence[PropertyEntry] = ()) -> Callable[[], Fragment]:
    """Builder for a widget with no children: its class, name and properties."""
    props = tuple(properties)

    def build() -> Fragment:
        return fragment(widget(class_name, object_name, properties=props))

    return build


def leaf_entry(
    key: str,
    friendly: str,
    qt_class: str,
    category: str,
    object_name: str,
    description: str,
    synonyms: Tuple[str, ...],
    glyph: str,
    properties: Sequence[PropertyEntry] = (),
) -> Entry:
    return Entry(
        key, friendly, qt_class, category, object_name, description, synonyms, glyph,
        WIDGET, leaf(qt_class, object_name, properties),
    )
