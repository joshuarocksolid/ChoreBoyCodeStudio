"""Read a realized widget into the engine's sizing facts.

The sentences stay in the engine. This module only measures.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.sizing import (
    QWIDGET_SIZE_MAX,
    AxisFacts,
    explain,
    project_axis,
    read_share,
    share_slots,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue, StringValue
from app.features.form_builder.qtside.inspector.words import class_words
from app.qt.QtWidgets import QWidget

_DEFAULTS: Dict[str, Tuple[str, str]] = {}
_SOFT = frozenset({"Preferred", "Minimum", "Maximum"})
_PARENT = {
    "QVBoxLayout": "vertical layout",
    "QHBoxLayout": "horizontal layout",
    "QGridLayout": "grid",
    "QFormLayout": "form layout",
}


def policy_name(value: object) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.split("::")[-1]
    return str(value).rsplit(".", 1)[-1]


def class_default_policies(widget: QWidget) -> Tuple[str, str]:
    """The class's own size policy, cached. Not the value stored on ``widget``."""
    key = _class_name(widget)
    cached = _DEFAULTS.get(key)
    if cached is not None:
        return cached
    fresh = _fresh(widget)
    if fresh is None:
        pair = ("Preferred", "Preferred")
    else:
        policy = fresh.sizePolicy()
        pair = (policy_name(policy.horizontalPolicy()), policy_name(policy.verticalPolicy()))
        fresh.deleteLater()
    _DEFAULTS[key] = pair
    return pair


def class_phrase(qt_class: str) -> str:
    return class_words(qt_class).friendly.lower()


def why_text(document: UiDocument, node_id: NodeId, widget: QWidget, *, qt_names: bool) -> str:
    """Explain ``widget``'s current size. Numbers are read from ``widget``."""
    width_fact, height_fact = measure_axes(document, node_id, widget)
    return explain(int(widget.width()), int(widget.height()), (width_fact, height_fact), qt_names=qt_names)


def measure_axes(document: UiDocument, node_id: NodeId, widget: QWidget) -> Tuple[AxisFacts, AxisFacts]:
    node = document.get(node_id)
    stored = _stored_policy(node)
    minimum = _stored_size(node, "minimumSize")
    maximum = _stored_size(node, "maximumSize")
    defaults = class_default_policies(widget)
    if stored is None:
        live = widget.sizePolicy()
        defaults = (policy_name(live.horizontalPolicy()), policy_name(live.verticalPolicy()))
    phrase = class_phrase(_class_name(widget))
    horizontal = project_axis(
        stored_policy=None if stored is None else stored.hsizetype,
        minimum=None if minimum is None else minimum.width,
        maximum=None if maximum is None else maximum.width,
        class_default_policy=defaults[0],
        class_phrase=phrase,
    )
    vertical = project_axis(
        stored_policy=None if stored is None else stored.vsizetype,
        minimum=None if minimum is None else minimum.height,
        maximum=None if maximum is None else maximum.height,
        class_default_policy=defaults[1],
        class_phrase=phrase,
    )
    parent = _parent_phrase(document, node_id)
    label_width = _form_label_width(document, node_id, widget)
    empty = _canvas_empty(widget)
    stretch = _stretches(document, node_id)
    return (
        _axis(
            "Width",
            int(widget.width()),
            int(widget.sizeHint().width()),
            int(widget.minimumSize().width()),
            int(widget.maximumSize().width()),
            policy_name(widget.sizePolicy().horizontalPolicy()),
            horizontal.word,
            stretch[0],
            stretch[1],
            parent,
            phrase,
            minimum is not None and minimum.width > 0,
            maximum is not None and maximum.width < QWIDGET_SIZE_MAX,
            horizontal.word == "Fixed",
            label_width,
            empty,
            int(widget.minimumSizeHint().width()),
        ),
        _axis(
            "Height",
            int(widget.height()),
            int(widget.sizeHint().height()),
            int(widget.minimumSize().height()),
            int(widget.maximumSize().height()),
            policy_name(widget.sizePolicy().verticalPolicy()),
            vertical.word,
            stretch[2],
            stretch[3],
            parent,
            phrase,
            minimum is not None and minimum.height > 0,
            maximum is not None and maximum.height < QWIDGET_SIZE_MAX,
            vertical.word == "Fixed",
            None,
            empty,
            int(widget.minimumSizeHint().height()),
        ),
    )


def _axis(
    name: str,
    size: int,
    hint: int,
    minimum: int,
    maximum: int,
    policy: str,
    word: Optional[str],
    stretch: int,
    stretch_sum: int,
    parent: str,
    phrase: str,
    minimum_set: bool,
    maximum_set: bool,
    fixed: bool,
    form_label_width: Optional[int],
    canvas_empty: bool,
    minimum_hint: int,
) -> AxisFacts:
    return AxisFacts(
        name,
        size,
        hint,
        minimum,
        maximum,
        policy,
        word,
        stretch,
        stretch_sum,
        max(0, size - hint),
        parent,
        phrase,
        minimum_set,
        maximum_set,
        fixed,
        size < hint,
        size > hint and policy in _SOFT and not fixed,
        form_label_width,
        canvas_empty,
        minimum_hint,
    )


def _stretches(document: UiDocument, node_id: NodeId) -> Tuple[int, int, int, int]:
    """Horizontal stretch, its sum, vertical stretch, its sum."""
    horizontal = 0
    horizontal_sum = 0
    vertical = 0
    vertical_sum = 0
    for slot in share_slots(document, node_id):
        reading = read_share(document, slot)
        if slot.axis == "h":
            horizontal, horizontal_sum = reading.value, reading.total
        else:
            vertical, vertical_sum = reading.value, reading.total
    return horizontal, horizontal_sum, vertical, vertical_sum


def _stored_policy(node: object) -> Optional[SizePolicyValue]:
    if not isinstance(node, WidgetNode):
        return None
    entry = node.prop("sizePolicy")
    if entry is None or not isinstance(entry.value, SizePolicyValue):
        return None
    return entry.value


def _stored_size(node: object, name: str) -> Optional[SizeValue]:
    if not isinstance(node, WidgetNode):
        return None
    entry = node.prop(name)
    if entry is None or not isinstance(entry.value, SizeValue):
        return None
    return entry.value


def _parent_phrase(document: UiDocument, node_id: NodeId) -> str:
    parent = document.parent(node_id)
    if isinstance(parent, LayoutItemNode):
        layout = document.parent(parent.id)
        if isinstance(layout, LayoutNode):
            owner = document.parent(layout.id)
            if isinstance(owner, WidgetNode) and owner.class_name == "QGroupBox":
                return "group box %s" % (_title(owner) or owner.object_name or "group")
            return _PARENT.get(layout.class_name, "layout")
    if isinstance(parent, WidgetNode):
        return class_phrase(parent.class_name)
    return "layout"


def _title(node: WidgetNode) -> str:
    entry = node.prop("title")
    if entry is None:
        entry = node.prop("text")
    if entry is not None and isinstance(entry.value, StringValue):
        return entry.value.text
    return ""


def _form_label_width(document: UiDocument, node_id: NodeId, widget: QWidget) -> Optional[int]:
    parent = document.parent(node_id)
    if not isinstance(parent, LayoutItemNode) or parent.column not in (0, None):
        return None
    layout = document.parent(parent.id)
    if not isinstance(layout, LayoutNode) or layout.class_name != "QFormLayout":
        return None
    if parent.column != 0:
        return None
    host = widget.parentWidget()
    if host is None:
        return int(widget.width())
    widest = int(widget.width())
    for child in host.children():
        if not isinstance(child, QWidget):
            continue
        if _class_name(child) != "QLabel":
            continue
        widest = max(widest, int(child.width()))
    return widest


def _canvas_empty(widget: QWidget) -> bool:
    layout = widget.layout()
    if layout is None or layout.count() != 0:
        return False
    hint = widget.sizeHint()
    return int(widget.width()) > int(hint.width()) or int(widget.height()) > int(hint.height())


def _class_name(widget: QWidget) -> str:
    meta = widget.metaObject()
    if meta is None:
        return "QWidget"
    return str(meta.className())


def _fresh(widget: QWidget) -> Optional[QWidget]:
    try:
        created = widget.__class__()
    except (TypeError, RuntimeError):
        return None
    if isinstance(created, QWidget):
        return created
    return None
