"""Hug, Fill, and Fixed projected onto Qt size policy, limits, and stretch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple, Union

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import (
    SetLayoutStretch,
    SetProperty,
    SetPropertyMany,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import form_item_role
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import EnumValue, SizePolicyValue, SizeValue

QT_MAX = 16777215

Axis = Literal["width", "height"]
Word = Literal["Hug", "Fill", "Fixed"]
LimitKind = Literal["minimum", "maximum"]
_StretchField = Literal["stretch", "columnstretch", "rowstretch"]

_POLICY_PREFIX = "QSizePolicy::"
_FILL_DEFAULTS = frozenset(("Expanding", "MinimumExpanding", "Ignored"))
_SOFT_DEFAULTS = frozenset(("Preferred", "Minimum", "Maximum"))
_GROWING = frozenset(("Preferred", "Minimum", "Expanding", "MinimumExpanding", "Ignored"))
_LAYOUT_PHRASES = {
    "QVBoxLayout": "vertical layout",
    "QHBoxLayout": "horizontal layout",
    "QGridLayout": "grid",
    "QFormLayout": "form layout",
}
_SHARE_CAPTION = "0 means no share. Two widgets with 1 and 2 split the spare room 1 : 2."
_CUSTOM_CLAUSE = {
    "Minimum": "Grows, never smaller than its content",
    "Maximum": "Grows, never larger than the size you set",
    "Preferred": "Asks for its content size, and grows when nothing else wants the room",
    "MinimumExpanding": "Grows, and takes spare room after widgets that only fill",
    "Ignored": "Takes the room it is given, and ignores its content size",
}


@dataclass(frozen=True)
class Hug:
    pass


@dataclass(frozen=True)
class Fill:
    pass


@dataclass(frozen=True)
class Fixed:
    px: int


@dataclass(frozen=True)
class Outlined:
    """Both axes are Outlined, or neither is. The file has one sizepolicy element."""

    word: Word
    soft: bool
    policy_name: str


@dataclass(frozen=True)
class Custom:
    policy_name: str


@dataclass(frozen=True)
class MixedMark:
    any_stored: bool


AxisMode = Union[Hug, Fill, Fixed, Outlined, Custom, MixedMark]


@dataclass(frozen=True)
class Empty:
    pass


@dataclass(frozen=True)
class Pixels:
    px: int


@dataclass(frozen=True)
class MixedLimit:
    pass


LimitCell = Union[Empty, Pixels, MixedLimit]


@dataclass(frozen=True)
class BoxShare:
    layout: NodeId
    index: int
    factors: Tuple[int, ...]
    # The sketch's phrase becomes "group box {name}" and drops the direction.
    axis: Axis


@dataclass(frozen=True)
class GridShare:
    layout: NodeId
    column: int
    row: int
    columns: Tuple[int, ...]
    rows: Tuple[int, ...]


@dataclass(frozen=True)
class SplitterShare:
    """The factor lives in the child's sizepolicy horstretch or verstretch."""

    axis: Axis
    factor: int


ShareFact = Union[BoxShare, GridShare, SplitterShare]


@dataclass(frozen=True)
class SizeFacts:
    owner: NodeId
    class_name: str
    friendly: str
    policy: Optional[SizePolicyValue]
    minimum: Optional[SizeValue]
    maximum: Optional[SizeValue]
    class_h: str
    class_v: str
    share: Optional[ShareFact]
    parent_phrase: str
    is_form_label: bool


@dataclass(frozen=True)
class AxisView:
    mode: AxisMode
    caption: str
    changed: bool
    hide_limits: bool


@dataclass(frozen=True)
class LimitView:
    width: LimitCell
    height: LimitCell
    changed: bool


@dataclass(frozen=True)
class ShareView:
    shown: bool
    factor: Optional[int]
    mixed: bool
    changed: bool
    caption: str


@dataclass(frozen=True)
class SizePanel:
    horizontal: AxisView
    vertical: AxisView
    at_least: LimitView
    at_most: LimitView
    share_width: ShareView
    share_height: ShareView
    why_owner: NodeId


@dataclass(frozen=True)
class SetWord:
    axis: Axis
    word: Word
    px: Optional[int]


@dataclass(frozen=True)
class SetLimit:
    kind: LimitKind
    axis: Axis
    px: Optional[int]


@dataclass(frozen=True)
class SetShare:
    axis: Axis
    factor: Optional[int]


@dataclass(frozen=True)
class ResetPolicy:
    axis: Axis


@dataclass(frozen=True)
class ResetLimits:
    kind: LimitKind


SizeEdit = Union[SetWord, SetLimit, SetShare, ResetPolicy, ResetLimits]


@dataclass(frozen=True)
class WhyLive:
    width: int
    height: int
    hint_w: int
    hint_h: int
    min_hint_w: int
    min_hint_h: int
    min_w: int
    min_h: int
    max_w: int
    max_h: int
    share_k: int
    share_total: int
    parent_phrase: str
    class_friendly: str
    form_label_width: Optional[int]
    canvas_floor: bool
    policy_h: str
    policy_v: str


@dataclass(frozen=True)
class WhyLine:
    text: str


@dataclass
class _StretchWrite:
    layout: NodeId
    field: _StretchField
    original: Tuple[int, ...]
    missing: bool
    indexes: Dict[int, int]


def facts_from_document(
    document: UiDocument,
    node: WidgetNode,
    class_h: str,
    class_v: str,
    friendly: str,
) -> SizeFacts:
    """File fields for one widget. Tests call this. Production calls selection_facts."""
    share, phrase, form_label = _placement(document, node)
    return SizeFacts(
        owner=node.id,
        class_name=node.class_name,
        friendly=friendly,
        policy=_as_policy(node.value("sizePolicy")),
        minimum=_as_size(node.value("minimumSize")),
        maximum=_as_size(node.value("maximumSize")),
        class_h=class_h,
        class_v=class_v,
        share=share,
        parent_phrase=phrase,
        is_form_label=form_label,
    )


def project(facts: Tuple[SizeFacts, ...]) -> SizePanel:
    """One panel. The caller does not pass an empty tuple."""
    return SizePanel(
        horizontal=_axis_view(facts, "width"),
        vertical=_axis_view(facts, "height"),
        at_least=_limit_view(facts, "minimum"),
        at_most=_limit_view(facts, "maximum"),
        share_width=_share_view(facts, "width"),
        share_height=_share_view(facts, "height"),
        why_owner=facts[0].owner,
    )


def chip_word(mode: AxisMode) -> Optional[str]:
    """The only word table. Hug, Fill, Fixed, or None."""
    if isinstance(mode, Hug):
        return "Hug"
    if isinstance(mode, Fill):
        return "Fill"
    if isinstance(mode, Fixed):
        return "Fixed"
    if isinstance(mode, Outlined):
        return mode.word
    return None


def chip_words(panel: SizePanel) -> Tuple[Optional[str], Optional[str]]:
    return (chip_word(panel.horizontal.mode), chip_word(panel.vertical.mode))


def can_grow(mode: AxisMode) -> bool:
    if isinstance(mode, Fill):
        return True
    if isinstance(mode, Outlined):
        if mode.policy_name == "Fixed":
            return False
        if mode.policy_name == "Maximum":
            return True
        return mode.policy_name in _GROWING
    if isinstance(mode, Custom):
        if mode.policy_name == "Maximum":
            return False
        return mode.policy_name in _GROWING
    return False


def cuts_off(
    width: int,
    height: int,
    hint_w: int,
    hint_h: int,
    mode_w: AxisMode,
    mode_h: AxisMode,
) -> bool:
    if hint_w > width and not can_grow(mode_w):
        return True
    if hint_h > height and not can_grow(mode_h):
        return True
    return False


def plan(facts: Tuple[SizeFacts, ...], edit: SizeEdit) -> Tuple[Command, ...]:
    """SetProperty, SetPropertyMany, and SetLayoutStretch only. Never SetGeometry."""
    if isinstance(edit, SetWord):
        return _plan_word(facts, edit)
    if isinstance(edit, SetLimit):
        return _plan_limit(facts, edit)
    if isinstance(edit, SetShare):
        return _plan_share(facts, edit)
    if isinstance(edit, ResetPolicy):
        return _plan_reset_policy(facts, edit.axis)
    if isinstance(edit, ResetLimits):
        return _plan_reset_limits(facts, edit.kind)
    raise TypeError("unknown size edit")


def edit_label(edit: SizeEdit) -> str:
    if isinstance(edit, SetWord):
        return "%s %s" % (edit.word, edit.axis)
    if isinstance(edit, ResetPolicy):
        return "Reset size"
    if isinstance(edit, (SetLimit, ResetLimits)):
        if edit.kind == "minimum":
            return "At least"
        return "At most"
    if isinstance(edit, SetShare):
        return "Share"
    raise TypeError("unknown size edit")


def why_lines(panel: SizePanel, live: WhyLive) -> Tuple[WhyLine, ...]:
    """Opening line, then the first matching sentence per axis, then form label, then canvas floor."""
    lines = [WhyLine("%s \u00d7 %s px." % (live.width, live.height))]
    lines.extend(_axis_lines(panel.horizontal.mode, "Width", live, True))
    lines.extend(_axis_lines(panel.vertical.mode, "Height", live, False))
    if live.form_label_width is not None:
        lines.append(WhyLine("Labels are as wide as the longest label, %s px." % live.form_label_width))
    if live.canvas_floor:
        lines.append(
            WhyLine(
                "The canvas shows empty layouts bigger so you can drop into them; "
                "that size isn't saved."
            )
        )
    return tuple(lines)


def qt_policy_text(live: WhyLive) -> str:
    """"(Fixed × Expanding)". The widget puts this on the faint label, not in the paragraph."""
    return "(%s \u00d7 %s)" % (live.policy_h, live.policy_v)


def _as_policy(value: object) -> Optional[SizePolicyValue]:
    if isinstance(value, SizePolicyValue):
        return value
    return None


def _as_size(value: object) -> Optional[SizeValue]:
    if isinstance(value, SizeValue):
        return value
    return None


def _strip_policy(name: str) -> str:
    if name.startswith(_POLICY_PREFIX):
        return name[len(_POLICY_PREFIX) :]
    return name


def _class_policy_name(raw: str) -> str:
    name = _strip_policy(raw)
    if name == "":
        return "Preferred"
    return name


def _parse_factors(raw: object) -> Tuple[int, ...]:
    if not isinstance(raw, str):
        return ()
    found: List[int] = []
    for piece in raw.split(","):
        text = piece.strip()
        if text == "":
            continue
        try:
            found.append(int(text))
        except ValueError:
            found.append(0)
    return tuple(found)


def _factor_at(factors: Tuple[int, ...], index: int) -> int:
    if 0 <= index < len(factors):
        return factors[index]
    return 0


def _component(size: SizeValue, axis: Axis) -> int:
    if axis == "width":
        return size.width
    return size.height


def _equal_pin(fact: SizeFacts, axis: Axis) -> Optional[int]:
    if fact.minimum is None or fact.maximum is None:
        return None
    low = _component(fact.minimum, axis)
    high = _component(fact.maximum, axis)
    if low == high and high < QT_MAX:
        return low
    return None


def _outlined(raw: str) -> Outlined:
    name = _strip_policy(raw)
    if name == "Fixed":
        return Outlined("Hug", False, name)
    if name in _FILL_DEFAULTS:
        return Outlined("Fill", False, name)
    if name in _SOFT_DEFAULTS:
        return Outlined("Hug", True, name)
    return Outlined("Hug", False, "Preferred")


def _mode_of(fact: SizeFacts, axis: Axis) -> AxisMode:
    policy = fact.policy
    if policy is None:
        raw = fact.class_h if axis == "width" else fact.class_v
        return _outlined(raw)
    raw = policy.hsizetype if axis == "width" else policy.vsizetype
    name = _strip_policy(raw)
    if name == "Fixed":
        pin = _equal_pin(fact, axis)
        if pin is not None:
            return Fixed(pin)
        return Hug()
    if name == "Expanding":
        return Fill()
    return Custom(name)


def _combine(facts: Tuple[SizeFacts, ...], axis: Axis) -> AxisMode:
    modes = tuple(_mode_of(fact, axis) for fact in facts)
    first = modes[0]
    for mode in modes[1:]:
        if mode != first:
            return MixedMark(any(fact.policy is not None for fact in facts))
    return first


def _caption(mode: AxisMode, friendly: str) -> str:
    if isinstance(mode, Outlined):
        noun = friendly.lower()
        if mode.soft:
            return (
                "Default for a %s: hugs its content, and grows when nothing else wants the room."
                % noun
            )
        return "Default for a %s" % noun
    if isinstance(mode, Custom):
        clause = _CUSTOM_CLAUSE.get(mode.policy_name)
        if clause is None:
            return "Custom: %s. Change it in All properties, or pick a word to replace it." % (
                mode.policy_name,
            )
        return "Custom: %s. %s. Change it in All properties, or pick a word to replace it." % (
            mode.policy_name,
            clause,
        )
    if isinstance(mode, MixedMark):
        return "Mixed"
    return ""


def _is_changed(mode: AxisMode) -> bool:
    if isinstance(mode, Outlined):
        return False
    if isinstance(mode, MixedMark):
        return mode.any_stored
    return True


def _axis_view(facts: Tuple[SizeFacts, ...], axis: Axis) -> AxisView:
    mode = _combine(facts, axis)
    return AxisView(
        mode=mode,
        caption=_caption(mode, facts[0].friendly),
        changed=_is_changed(mode),
        hide_limits=isinstance(mode, Fixed),
    )


def _display_limit(kind: LimitKind, value: int) -> LimitCell:
    if kind == "maximum" and value >= QT_MAX:
        return Empty()
    return Pixels(value)


def _limit_cell(facts: Tuple[SizeFacts, ...], kind: LimitKind, axis: Axis) -> LimitCell:
    present: List[int] = []
    saw_missing = False
    for fact in facts:
        size = fact.minimum if kind == "minimum" else fact.maximum
        if size is None:
            saw_missing = True
            continue
        present.append(_component(size, axis))
    if not present:
        return Empty()
    if saw_missing:
        return MixedLimit()
    cells = tuple(_display_limit(kind, value) for value in present)
    first = cells[0]
    for cell in cells[1:]:
        if cell != first:
            return MixedLimit()
    return first


def _limit_view(facts: Tuple[SizeFacts, ...], kind: LimitKind) -> LimitView:
    changed = False
    for fact in facts:
        size = fact.minimum if kind == "minimum" else fact.maximum
        if size is not None:
            changed = True
            break
    return LimitView(
        width=_limit_cell(facts, kind, "width"),
        height=_limit_cell(facts, kind, "height"),
        changed=changed,
    )


def _share_factor(share: Optional[ShareFact], axis: Axis) -> Optional[int]:
    if isinstance(share, BoxShare):
        if share.axis != axis:
            return None
        return _factor_at(share.factors, share.index)
    if isinstance(share, GridShare):
        if axis == "width":
            return _factor_at(share.columns, share.column)
        return _factor_at(share.rows, share.row)
    if isinstance(share, SplitterShare):
        if share.axis != axis:
            return None
        return share.factor
    return None


def _share_view(facts: Tuple[SizeFacts, ...], axis: Axis) -> ShareView:
    factors: List[int] = []
    for fact in facts:
        factor = _share_factor(fact.share, axis)
        if factor is None:
            return ShareView(False, None, False, False, "")
        factors.append(factor)
    first = factors[0]
    mixed = False
    for factor in factors[1:]:
        if factor != first:
            mixed = True
            break
    return ShareView(
        shown=True,
        factor=None if mixed else first,
        mixed=mixed,
        changed=any(factor != 0 for factor in factors),
        caption=_SHARE_CAPTION,
    )


def _placement(
    document: UiDocument, node: WidgetNode
) -> Tuple[Optional[ShareFact], str, bool]:
    parent = document.parent(node.id)
    if isinstance(parent, LayoutItemNode):
        layout = document.parent(parent.id)
        if isinstance(layout, LayoutNode):
            return (
                _layout_share(layout, parent),
                _phrase(document, layout),
                _form_label(layout, parent),
            )
    if isinstance(parent, WidgetNode) and parent.class_name == "QSplitter":
        return _splitter_share(parent, node), "splitter", False
    if isinstance(parent, WidgetNode) and parent.class_name == "QGroupBox" and parent.object_name:
        return None, "group box %s" % parent.object_name, False
    return None, "", False


def _phrase(document: UiDocument, layout: LayoutNode) -> str:
    owner_id = layout.owner_widget_id()
    if owner_id is not None:
        owner = document.node(owner_id)
        if isinstance(owner, WidgetNode) and owner.class_name == "QGroupBox" and owner.object_name:
            return "group box %s" % owner.object_name
    return _LAYOUT_PHRASES.get(layout.class_name, "layout")


def _form_label(layout: LayoutNode, item: LayoutItemNode) -> bool:
    if layout.class_name != "QFormLayout":
        return False
    return form_item_role(item.column, item.colspan) == "label"


def _layout_share(layout: LayoutNode, item: LayoutItemNode) -> Optional[ShareFact]:
    kind = layout.class_name
    if kind == "QVBoxLayout":
        return BoxShare(layout.id, item.slot_index, _parse_factors(layout.field("stretch")), "height")
    if kind == "QHBoxLayout":
        return BoxShare(layout.id, item.slot_index, _parse_factors(layout.field("stretch")), "width")
    if kind == "QGridLayout":
        column = item.column if item.column is not None else 0
        row = item.row if item.row is not None else 0
        return GridShare(
            layout.id,
            column,
            row,
            _parse_factors(layout.field("columnstretch")),
            _parse_factors(layout.field("rowstretch")),
        )
    return None


def _splitter_share(splitter: WidgetNode, child: WidgetNode) -> SplitterShare:
    axis: Axis = "width"
    orientation = splitter.value("orientation")
    if isinstance(orientation, EnumValue) and orientation.key()[1] == "Vertical":
        axis = "height"
    policy = _as_policy(child.value("sizePolicy"))
    factor = 0
    if policy is not None:
        factor = policy.verstretch if axis == "height" else policy.horstretch
    return SplitterShare(axis, factor)


def _word_name(word: Word) -> str:
    if word == "Fill":
        return "Expanding"
    return "Fixed"


def _policy_for_word(fact: SizeFacts, axis: Axis, word: Word) -> SizePolicyValue:
    current = fact.policy
    if current is None:
        horizontal = _class_policy_name(fact.class_h)
        vertical = _class_policy_name(fact.class_v)
        horstretch = 0
        verstretch = 0
    else:
        horizontal = current.hsizetype
        vertical = current.vsizetype
        horstretch = current.horstretch
        verstretch = current.verstretch
    stored = _word_name(word)
    if axis == "width":
        horizontal = stored
    else:
        vertical = stored
    return SizePolicyValue(horizontal, vertical, horstretch, verstretch)


def _assign(current: Optional[SizeValue], axis: Axis, value: int, fill: int) -> SizeValue:
    if current is None:
        if axis == "width":
            return SizeValue(value, fill)
        return SizeValue(fill, value)
    if axis == "width":
        return SizeValue(value, current.height)
    return SizeValue(current.width, value)


def _cleared_value(
    current: Optional[SizeValue], kind: LimitKind, axis: Axis
) -> Tuple[bool, Optional[SizeValue]]:
    if current is None:
        return False, None
    cleared = 0 if kind == "minimum" else QT_MAX
    updated = _assign(current, axis, cleared, cleared)
    result: Optional[SizeValue]
    if kind == "minimum" and updated.width == 0 and updated.height == 0:
        result = None
    elif kind == "maximum" and updated.width >= QT_MAX and updated.height >= QT_MAX:
        result = None
    else:
        result = updated
    if result == current:
        return False, current
    return True, result


def _limit_name(kind: LimitKind) -> str:
    if kind == "minimum":
        return "minimumSize"
    return "maximumSize"


def _set_component(fact: SizeFacts, kind: LimitKind, axis: Axis, px: int) -> Optional[Command]:
    current = fact.minimum if kind == "minimum" else fact.maximum
    fill = 0 if kind == "minimum" else QT_MAX
    updated = _assign(current, axis, px, fill)
    if updated == current:
        return None
    return SetProperty(fact.owner, _limit_name(kind), updated)


def _clear_pin(fact: SizeFacts, axis: Axis) -> List[Command]:
    if _equal_pin(fact, axis) is None:
        return []
    commands: List[Command] = []
    for kind in ("minimum", "maximum"):
        current = fact.minimum if kind == "minimum" else fact.maximum
        changed, updated = _cleared_value(current, kind, axis)
        if changed:
            commands.append(SetProperty(fact.owner, _limit_name(kind), updated))
    return commands


def _plan_word(facts: Tuple[SizeFacts, ...], edit: SetWord) -> Tuple[Command, ...]:
    commands: List[Command] = []
    for fact in facts:
        updated = _policy_for_word(fact, edit.axis, edit.word)
        if updated != fact.policy:
            commands.append(SetProperty(fact.owner, "sizePolicy", updated))
        if edit.word == "Fixed" and edit.px is not None:
            for kind in ("minimum", "maximum"):
                command = _set_component(fact, kind, edit.axis, edit.px)
                if command is not None:
                    commands.append(command)
        elif edit.word != "Fixed":
            commands.extend(_clear_pin(fact, edit.axis))
    return tuple(commands)


def _plan_limit(facts: Tuple[SizeFacts, ...], edit: SetLimit) -> Tuple[Command, ...]:
    commands: List[Command] = []
    for fact in facts:
        current = fact.minimum if edit.kind == "minimum" else fact.maximum
        if edit.px is None:
            changed, updated = _cleared_value(current, edit.kind, edit.axis)
            if changed:
                commands.append(SetProperty(fact.owner, _limit_name(edit.kind), updated))
            continue
        command = _set_component(fact, edit.kind, edit.axis, edit.px)
        if command is not None:
            commands.append(command)
    return tuple(commands)


def _policy_after_reset(fact: SizeFacts, axis: Axis) -> Optional[SizePolicyValue]:
    if fact.class_h == "":
        return None
    current = fact.policy
    if current is None:
        return None
    target = _class_policy_name(fact.class_h if axis == "width" else fact.class_v)
    if axis == "width":
        horizontal, vertical = target, current.vsizetype
    else:
        horizontal, vertical = current.hsizetype, target
    if (
        _strip_policy(horizontal) == _class_policy_name(fact.class_h)
        and _strip_policy(vertical) == _class_policy_name(fact.class_v)
        and current.horstretch == 0
        and current.verstretch == 0
    ):
        return None
    return SizePolicyValue(horizontal, vertical, current.horstretch, current.verstretch)


def _plan_reset_policy(facts: Tuple[SizeFacts, ...], axis: Axis) -> Tuple[Command, ...]:
    commands: List[Command] = []
    for fact in facts:
        updated = _policy_after_reset(fact, axis)
        if updated != fact.policy:
            commands.append(SetProperty(fact.owner, "sizePolicy", updated))
        commands.extend(_clear_pin(fact, axis))
    return tuple(commands)


def _plan_reset_limits(facts: Tuple[SizeFacts, ...], kind: LimitKind) -> Tuple[Command, ...]:
    present = False
    for fact in facts:
        current = fact.minimum if kind == "minimum" else fact.maximum
        if current is not None:
            present = True
            break
    if not present:
        return ()
    owners = tuple(fact.owner for fact in facts)
    return (SetPropertyMany(owners, _limit_name(kind), None),)


def _box_target(
    share: ShareFact, axis: Axis
) -> Optional[Tuple[NodeId, _StretchField, int, Tuple[int, ...]]]:
    if isinstance(share, BoxShare):
        if share.axis != axis:
            return None
        return share.layout, "stretch", share.index, share.factors
    if isinstance(share, GridShare):
        if axis == "width":
            return share.layout, "columnstretch", share.column, share.columns
        return share.layout, "rowstretch", share.row, share.rows
    return None


def _stretch_update(
    original: Tuple[int, ...], missing: bool, indexes: Dict[int, int]
) -> Tuple[bool, Optional[str]]:
    factors = list(original)
    for index, value in indexes.items():
        while len(factors) <= index:
            factors.append(0)
        factors[index] = value
    while len(factors) > len(original) and factors and factors[-1] == 0:
        factors.pop()
    if all(item == 0 for item in factors):
        if missing:
            return False, None
        return True, None
    if factors == list(original):
        return False, None
    return True, ",".join(str(item) for item in factors)


def _plan_splitter_share(fact: SizeFacts, axis: Axis, value: int) -> Tuple[Command, ...]:
    current = fact.policy
    if current is None:
        horizontal = _class_policy_name(fact.class_h)
        vertical = _class_policy_name(fact.class_v)
        horstretch = 0
        verstretch = 0
    else:
        horizontal = current.hsizetype
        vertical = current.vsizetype
        horstretch = current.horstretch
        verstretch = current.verstretch
    if axis == "width":
        horstretch = value
    else:
        verstretch = value
    if current is None and horstretch == 0 and verstretch == 0:
        return ()
    updated = SizePolicyValue(horizontal, vertical, horstretch, verstretch)
    if updated == current:
        return ()
    return (SetProperty(fact.owner, "sizePolicy", updated),)


def _plan_share(facts: Tuple[SizeFacts, ...], edit: SetShare) -> Tuple[Command, ...]:
    written = 0 if edit.factor is None else edit.factor
    groups: Dict[Tuple[NodeId, str], _StretchWrite] = {}
    commands: List[Command] = []
    for fact in facts:
        share = fact.share
        if share is None:
            continue
        if isinstance(share, SplitterShare):
            if share.axis == edit.axis:
                commands.extend(_plan_splitter_share(fact, edit.axis, written))
            continue
        target = _box_target(share, edit.axis)
        if target is None:
            continue
        layout_id, field, index, factors = target
        key = (layout_id, field)
        group = groups.get(key)
        if group is None:
            group = _StretchWrite(layout_id, field, factors, len(factors) == 0, {})
            groups[key] = group
        group.indexes[index] = written
    for group in groups.values():
        changed, value = _stretch_update(group.original, group.missing, group.indexes)
        if not changed:
            continue
        commands.append(SetLayoutStretch(group.layout, group.field, value))
    return tuple(commands)


def _axis_lines(mode: AxisMode, noun: str, live: WhyLive, horizontal: bool) -> Tuple[WhyLine, ...]:
    if isinstance(mode, (Custom, MixedMark)):
        return ()
    size = live.width if horizontal else live.height
    hint = live.hint_w if horizontal else live.hint_h
    min_hint = live.min_hint_w if horizontal else live.min_hint_h
    minimum = live.min_w if horizontal else live.min_h
    maximum = live.max_w if horizontal else live.max_h
    if isinstance(mode, Fixed):
        return (WhyLine("%s is fixed at %s px." % (noun, mode.px)),)
    if isinstance(mode, Fill) and maximum < QT_MAX and size >= maximum:
        return (WhyLine("%s would fill, but stops at its maximum of %s px." % (noun, maximum)),)
    if isinstance(mode, Fill) and live.share_k > 0 and live.share_total > 0:
        return (
            WhyLine(
                "It gets %s of every %s px of spare room (share %s of %s)."
                % (live.share_k, live.share_total, live.share_k, live.share_total)
            ),
        )
    if isinstance(mode, Fill):
        return (WhyLine("%s fills the room the %s gives it." % (noun, live.parent_phrase)),)
    if isinstance(mode, Hug):
        return (
            WhyLine(
                "%s is what a %s needs for its content: %s px."
                % (noun, live.class_friendly.lower(), hint)
            ),
        )
    if isinstance(mode, Outlined) and mode.soft and size > hint:
        return (
            WhyLine(
                "%s grew past the %s px it asks for, because nothing else wanted the room."
                % (noun, hint)
            ),
        )
    if size < hint:
        return (
            WhyLine(
                "%s is squeezed below the %s px it asks for, because the window is too narrow. "
                "It can't go below %s px." % (noun, hint, min_hint)
            ),
        )
    if size == minimum and minimum > min_hint:
        return (WhyLine("%s can't go below its minimum of %s px." % (noun, minimum)),)
    return ()
