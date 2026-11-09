"""One undo step for a sizing edit.

``apply`` plans the same property and field ops the rest of the catalog uses,
so the inverse is the inverse those ops already return.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Hashable, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import PlanContext
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.sizing import (
    PaneShare,
    Share,
    SizingWrite,
    encode_share,
    splice_stretch,
    stretch_length,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue

_STRETCH_FIELDS = (
    "stretch",
    "rowstretch",
    "columnstretch",
    "rowminimumheight",
    "columnminimumwidth",
)


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(ApplySizing)


@dataclass(frozen=True)
class ApplySizing:
    """Write the size policy, the limits, and one layout stretch together."""

    command_type: ClassVar[str] = "apply_sizing"
    owner: NodeId
    policy: Optional[SizePolicyValue] = None
    minimum: Optional[SizeValue] = None
    maximum: Optional[SizeValue] = None
    touch_policy: bool = False
    touch_minimum: bool = False
    touch_maximum: bool = False
    layout: Optional[NodeId] = None
    stretch_field: Optional[str] = None
    stretch: Optional[str] = None
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        clearing = (
            (not self.touch_policy or self.policy is None)
            and (not self.touch_minimum or self.minimum is None)
            and (not self.touch_maximum or self.maximum is None)
            and (self.stretch_field is None or self.stretch is None)
            and (self.touch_policy or self.touch_minimum or self.touch_maximum or self.stretch_field is not None)
        )
        if clearing and self.policy is None and self.minimum is None and self.maximum is None:
            return "Reset"
        return "Size"

    def merge_key(self) -> Optional[Hashable]:
        return ("apply_sizing", self.owner, self.stretch_field)

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if self.touch_policy:
            planning.set_property(doc, ctx, self.owner, "sizePolicy", self.policy)
        if self.touch_minimum:
            planning.set_property(doc, ctx, self.owner, "minimumSize", self.minimum)
        if self.touch_maximum:
            planning.set_property(doc, ctx, self.owner, "maximumSize", self.maximum)
        if self.layout is not None and self.stretch_field in _STRETCH_FIELDS:
            planning.set_field(doc, ctx, self.layout, self.stretch_field, self.stretch)


def from_write(
    owner: NodeId,
    write: SizingWrite,
    *,
    layout: Optional[NodeId] = None,
    stretch_field: Optional[str] = None,
    stretch: Optional[str] = None,
    merge_token: Optional[str] = None,
) -> ApplySizing:
    return ApplySizing(
        owner,
        write.policy,
        write.minimum,
        write.maximum,
        write.touch_policy,
        write.touch_minimum,
        write.touch_maximum,
        layout,
        stretch_field,
        stretch,
        merge_token,
    )


def write_share(
    document: UiDocument,
    slot: Share,
    owner: NodeId,
    value: int,
    defaults: Tuple[str, str],
) -> Optional[ApplySizing]:
    """The one share writer. ``defaults`` are the owner's class (horizontal, vertical) policies.

    None when the slot's layout or pane is gone.
    """
    if isinstance(slot, PaneShare):
        pane = document.get(slot.pane)
        if not isinstance(pane, WidgetNode):
            return None
        entry = pane.prop("sizePolicy")
        current = entry.value if entry is not None and isinstance(entry.value, SizePolicyValue) else None
        write = encode_share(
            axis=slot.axis,
            value=value,
            current_policy=current,
            class_default_h=defaults[0],
            class_default_v=defaults[1],
        )
        return from_write(owner, write)
    layout = document.get(slot.layout)
    if not isinstance(layout, LayoutNode):
        return None
    raw = layout.field(slot.field)
    text = raw if isinstance(raw, str) else None
    return from_write(
        owner,
        SizingWrite(None, None, None, False, False, False),
        layout=slot.layout,
        stretch_field=slot.field,
        stretch=splice_stretch(text, slot.index, value, stretch_length(layout, slot.field)),
    )
