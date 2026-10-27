"""Read a realized widget into the engine's sizing facts.

The sentences stay in the engine. This module only measures.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import effective_class
from app.features.form_builder.engine.sizing import (
    QWIDGET_SIZE_MAX,
    AxisFacts,
    explain,
    placed_freely,
    project_axis,
    read_share,
    share_slots,
    splitter_axis,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue, StringValue
from app.features.form_builder.qtside.inspector.words import class_words
from app.qt.QtCore import QSize, Qt
from app.qt.QtWidgets import QFormLayout, QSizePolicy, QSplitter, QWidget
from app.qt.qt_compat import delete_now

_DEFAULTS: Dict[str, Tuple[str, str]] = {}
_SOFT = frozenset({"Preferred", "Minimum", "Maximum"})
_GROWTH = 200
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
    free = placed_freely(document, node_id)
    growth = _splitter_measure(document, node_id, widget)
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
            free,
            _growth_for(growth, "Width"),
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
            free,
            _growth_for(growth, "Height"),
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
    free: bool,
    growth: Tuple[bool, Optional[int], Optional[int]],
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
        free,
        growth[0],
        growth[1],
        growth[2],
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
    if _class_name(widget) != "QLabel":
        return None
    parent = document.parent(node_id)
    if not isinstance(parent, LayoutItemNode) or parent.column != 0:
        return None
    layout = document.parent(parent.id)
    if not isinstance(layout, LayoutNode) or layout.class_name != "QFormLayout":
        return None
    host = widget.parentWidget()
    if host is None:
        return None
    form = host.layout()
    if not isinstance(form, QFormLayout):
        return None
    role = getattr(getattr(QFormLayout, "ItemRole", QFormLayout), "LabelRole")
    widest = 0
    seen = False
    for row in range(form.rowCount()):
        item = form.itemAt(row, role)
        if item is None:
            continue
        child = item.widget()
        if child is None:
            continue
        widest = max(widest, int(child.width()))
        seen = True
    if not seen:
        return int(widget.width())
    return widest


def _splitter_measure(
    document: UiDocument, node_id: NodeId, widget: QWidget
) -> Optional[Tuple[str, Optional[int], Optional[int]]]:
    parent = document.parent(node_id)
    if not isinstance(parent, WidgetNode) or effective_class(document, parent) != "QSplitter":
        return None
    host = widget.parentWidget()
    if not isinstance(host, QSplitter):
        return None
    horizontal = splitter_axis(parent) == "h"
    taken, total = _pane_growth(host, widget, horizontal)
    return ("Width" if horizontal else "Height", taken, total)


def _growth_for(
    growth: Optional[Tuple[str, Optional[int], Optional[int]]], axis: str
) -> Tuple[bool, Optional[int], Optional[int]]:
    if growth is None or growth[0] != axis:
        return (False, None, None)
    return (True, growth[1], growth[2])


def _pane_growth(splitter: QSplitter, pane: QWidget, horizontal: bool) -> Tuple[Optional[int], Optional[int]]:
    """What this pane does when the splitter grows. A grip drag is not growth."""
    index = _pane_index(splitter, pane)
    if index is None:
        return (None, None)
    return _scratch_growth(splitter, horizontal).get(index, (None, None))


def _pane_index(splitter: QSplitter, pane: QWidget) -> Optional[int]:
    for index in range(splitter.count()):
        if splitter.widget(index) is pane:
            return index
    return None


def _scratch_growth(splitter: QSplitter, horizontal: bool) -> Dict[int, Tuple[int, int]]:
    """Resizing the live splitter would fight a caller that is measuring its own resize."""
    scratch = QSplitter()
    scratch.setAttribute(Qt.WA_DontShowOnScreen, True)
    scratch.setOrientation(splitter.orientation())
    scratch.setHandleWidth(int(splitter.handleWidth()))
    scratch.setChildrenCollapsible(bool(splitter.childrenCollapsible()))
    for index in range(splitter.count()):
        pane = splitter.widget(index)
        if pane is None:
            scratch.addWidget(QWidget(scratch))
            continue
        scratch.addWidget(
            _GrowthPane(pane.sizeHint(), pane.sizePolicy(), _floor(pane), pane.maximumSize())
        )
    width = max(int(splitter.width()), 1)
    height = max(int(splitter.height()), 1)
    scratch.resize(width, height)
    scratch.show()
    before = [int(size) for size in scratch.sizes()]
    if horizontal:
        scratch.resize(width + _GROWTH, height)
    else:
        scratch.resize(width, height + _GROWTH)
    after = [int(size) for size in scratch.sizes()]
    delete_now(scratch)
    if len(before) != len(after) or not before:
        return {}
    total = sum(after) - sum(before)
    return {index: (after[index] - before[index], total) for index in range(len(after))}


def _floor(pane: QWidget) -> QSize:
    minimum = pane.minimumSize()
    hint = pane.minimumSizeHint()
    return QSize(
        max(int(minimum.width()), int(hint.width())),
        max(int(minimum.height()), int(hint.height())),
    )


class _GrowthPane(QWidget):
    def __init__(self, hint: QSize, policy: QSizePolicy, minimum: QSize, maximum: QSize) -> None:
        super().__init__()
        self._hint = hint
        self.setSizePolicy(policy)
        self.setMinimumSize(minimum)
        self.setMaximumSize(maximum)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self._hint

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()


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
