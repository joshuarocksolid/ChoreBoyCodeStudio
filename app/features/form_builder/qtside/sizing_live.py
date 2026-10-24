"""Live class defaults and the numbers "Why is it this size?" reads.

``project`` and ``plan`` stay in the engine. This module only measures Qt.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.sizing import SizeFacts, WhyLive, facts_from_document
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue
from app.features.form_builder.qtside.inspector.words import class_words
from app.features.form_builder.qtside.realize.api import Realizer
from app.qt.QtWidgets import QBoxLayout, QFormLayout, QGridLayout, QSplitter, QWidget

_PRISTINE: Dict[str, QWidget] = {}
_HOLDER: Optional[QWidget] = None


def selection_facts(
    document: UiDocument, owners: Tuple[NodeId, ...], realizer: Realizer
) -> Tuple[SizeFacts, ...]:
    """File facts for these owners, with class defaults from one widget each."""
    found: List[SizeFacts] = []
    for owner in owners:
        node = document.get(owner)
        if not isinstance(node, WidgetNode):
            continue
        live = realizer.widget_for(node.id)
        stored = isinstance(node.value("sizePolicy"), SizePolicyValue)
        if not stored and live is not None:
            class_h, class_v = _policy_axes(live)
        else:
            class_h, class_v = _pristine_axes(realizer, node.class_name)
        short = realizer._qt_class_name(node.class_name)
        found.append(
            facts_from_document(
                document,
                node,
                class_h,
                class_v,
                class_words(short).friendly,
            )
        )
    return tuple(found)


def find_realizer(widget: QWidget) -> Optional[Realizer]:
    """The inspector that already holds the realizer. Does not walk the form."""
    current: Optional[QWidget] = widget
    while current is not None:
        if current.objectName() == "formBuilder.inspector":
            found = getattr(current, "_realizer", None)
            if isinstance(found, Realizer):
                return found
            return None
        current = current.parentWidget()
    return None


def measure(widget: QWidget, facts: SizeFacts) -> WhyLive:
    """Geometry, hints, and the parent share after the layouts activate."""
    _activate(widget)
    policy = widget.sizePolicy()
    hint = widget.sizeHint()
    minimum_hint = widget.minimumSizeHint()
    minimum = widget.minimumSize()
    maximum = widget.maximumSize()
    share_k, share_total = _share_of(widget)
    return WhyLive(
        width=int(widget.width()),
        height=int(widget.height()),
        hint_w=int(hint.width()),
        hint_h=int(hint.height()),
        min_hint_w=int(minimum_hint.width()),
        min_hint_h=int(minimum_hint.height()),
        min_w=int(minimum.width()),
        min_h=int(minimum.height()),
        max_w=int(maximum.width()),
        max_h=int(maximum.height()),
        share_k=share_k,
        share_total=share_total,
        parent_phrase=facts.parent_phrase,
        class_friendly=facts.friendly,
        form_label_width=_form_label_width(widget) if facts.is_form_label else None,
        canvas_floor=False,
        policy_h=_policy_name(policy.horizontalPolicy()),
        policy_v=_policy_name(policy.verticalPolicy()),
    )


def _holder() -> QWidget:
    global _HOLDER
    if _HOLDER is None:
        _HOLDER = QWidget()
        _HOLDER.setObjectName("formBuilder.sizeClassDefaults")
        _HOLDER.hide()
    return _HOLDER


def _pristine_axes(realizer: Realizer, class_name: str) -> Tuple[str, str]:
    short = realizer._qt_class_name(class_name)
    widget = _PRISTINE.get(short)
    if widget is None:
        widget = _make_pristine(realizer, class_name)
        _PRISTINE[short] = widget
    return _policy_axes(widget)


def _make_pristine(realizer: Realizer, class_name: str) -> QWidget:
    cls = realizer._widget_type(class_name)
    parent = _holder()
    try:
        made = cls(parent)
    except (TypeError, RuntimeError):
        made = QWidget(parent)
    if not isinstance(made, QWidget):
        made = QWidget(parent)
    made.hide()
    return made


def _policy_axes(widget: QWidget) -> Tuple[str, str]:
    policy = widget.sizePolicy()
    return (
        _policy_name(policy.horizontalPolicy()),
        _policy_name(policy.verticalPolicy()),
    )


def _policy_name(value: object) -> str:
    name = getattr(value, "name", None)
    text = name if isinstance(name, str) and name else str(value)
    if "::" in text:
        text = text.rsplit("::", 1)[-1]
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text or "Preferred"


def _activate(widget: QWidget) -> None:
    chain: List[QWidget] = []
    current: Optional[QWidget] = widget
    while current is not None:
        chain.append(current)
        current = current.parentWidget()
    for item in reversed(chain):
        layout = item.layout()
        if layout is not None:
            layout.activate()


def _share_of(widget: QWidget) -> Tuple[int, int]:
    parent = widget.parentWidget()
    if isinstance(parent, QSplitter):
        return _splitter_share(parent, widget)
    if parent is None:
        return 0, 0
    layout = parent.layout()
    if layout is None or isinstance(layout, QFormLayout):
        return 0, 0
    if isinstance(layout, QBoxLayout):
        return _indexed_share(layout.count(), layout.stretch, layout.indexOf(widget))
    if isinstance(layout, QGridLayout):
        return _grid_share(layout, widget)
    return 0, 0


def _grid_share(layout: QGridLayout, widget: QWidget) -> Tuple[int, int]:
    """WhyLive carries one share. A non-zero column share wins over the row."""
    index = layout.indexOf(widget)
    if index < 0:
        return 0, 0
    position = layout.getItemPosition(index)
    row = int(position[0])
    column = int(position[1])
    column_share = _indexed_share(layout.columnCount(), layout.columnStretch, column)
    if column_share[0] > 0:
        return column_share
    row_share = _indexed_share(layout.rowCount(), layout.rowStretch, row)
    if row_share[0] > 0:
        return row_share
    return 0, 0


def _splitter_share(splitter: QSplitter, widget: QWidget) -> Tuple[int, int]:
    vertical = _vertical(splitter)
    own = 0
    total = 0
    found = False
    for index in range(splitter.count()):
        child = splitter.widget(index)
        if child is None:
            continue
        policy = child.sizePolicy()
        factor = policy.verticalStretch() if vertical else policy.horizontalStretch()
        total += int(factor)
        if child is widget:
            own = int(factor)
            found = True
    if not found:
        return 0, 0
    return own, total


def _indexed_share(count: int, read: object, index: int) -> Tuple[int, int]:
    if index < 0 or not callable(read):
        return 0, 0
    own = 0
    total = 0
    for slot in range(count):
        factor = int(read(slot))
        total += factor
        if slot == index:
            own = factor
    return own, total


def _form_label_width(widget: QWidget) -> Optional[int]:
    parent = widget.parentWidget()
    if parent is None:
        return None
    layout = parent.layout()
    if not isinstance(layout, QFormLayout):
        return None
    role_type = getattr(QFormLayout, "ItemRole", QFormLayout)
    role = getattr(role_type, "LabelRole")
    widths: List[int] = []
    for row in range(layout.rowCount()):
        item = layout.itemAt(row, role)
        if item is None:
            continue
        label = item.widget()
        if label is not None:
            widths.append(int(label.width()))
    if not widths:
        return None
    return max(widths)


def _vertical(splitter: QSplitter) -> bool:
    value = splitter.orientation()
    name = getattr(value, "name", None)
    text = name if isinstance(name, str) and name else str(value)
    return text.endswith("Vertical")
