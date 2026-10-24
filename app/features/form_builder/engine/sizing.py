"""Hug, Fill, and Fixed as a projection of Qt size policy, limits, and stretch.

The engine never imports Qt. A caller measures the live widget and passes
numbers in. Writing the projection back produces the properties a ``.ui``
file already knows, and Reset deletes those properties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutItemNode, LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.values import SizePolicyValue, SizeValue

QWIDGET_SIZE_MAX = 16777215

WORD_HUG = "Hug"
WORD_FILL = "Fill"
WORD_FIXED = "Fixed"
WORDS = (WORD_HUG, WORD_FILL, WORD_FIXED)

_FILL_POLICIES = frozenset({"Expanding", "MinimumExpanding", "Ignored"})
_HUG_POLICIES = frozenset({"Preferred", "Fixed"})
_SOFT_DEFAULTS = frozenset({"Preferred", "Minimum", "Maximum"})
_CUSTOM_CLAUSE = {
    "Minimum": "grows, never smaller than its content",
    "Maximum": "shrinks, never larger than its content",
    "Preferred": "asks for its content size, and may grow or shrink",
    "MinimumExpanding": "grows, and tries not to shrink below its content",
    "Ignored": "takes whatever room it is given",
}

TEXT_FACTORS = (
    ("Smaller", 0.85),
    ("Normal", 1.0),
    ("Larger", 1.25),
    ("Largest", 1.5),
)
SCREEN_SCALES = (100, 125, 150, 200)
WIDE_SCREEN_PX = 1366

HUG_TIP = "As big as its content needs, and no bigger."
FILL_TIP = "Takes the spare room the layout gives it."
FIXED_TIP = "Exactly this many pixels."
SHARE_CAPTION = "0 means no share. Two widgets with 1 and 2 split the spare room 1 : 2."


@dataclass(frozen=True)
class AxisProjection:
    """What one axis of the Size group shows.

    ``filled`` is a stored Hug, Fill, or Fixed. An outlined default has a
    word and ``filled`` false. ``custom`` is a stored policy outside those
    three encodings, so no segment is filled.
    """

    word: Optional[str]
    filled: bool
    custom: bool
    pixels: Optional[int]
    policy_name: str
    caption: str


@dataclass(frozen=True)
class SizingWrite:
    """Properties one sizing edit stores. ``None`` deletes the property."""

    policy: Optional[SizePolicyValue]
    minimum: Optional[SizeValue]
    maximum: Optional[SizeValue]
    touch_policy: bool
    touch_minimum: bool
    touch_maximum: bool


@dataclass(frozen=True)
class ShareSlot:
    """One layout stretch cell that belongs to a widget."""

    layout: NodeId
    field: str
    index: int
    axis: str


@dataclass(frozen=True)
class AxisFacts:
    """Numbers measured from one live axis. ``explain`` only reads these."""

    name: str
    size: int
    hint: int
    minimum: int
    maximum: int
    policy: str
    word: Optional[str]
    stretch: int
    stretch_sum: int
    spare: int
    parent_phrase: str
    class_phrase: str
    minimum_set: bool
    maximum_set: bool
    fixed: bool
    squeezed: bool
    grew: bool
    form_label_width: Optional[int] = None
    canvas_empty: bool = False


def policy_tail(policy: str) -> str:
    return policy.split("::")[-1].split(".")[-1]


def effective_word(policy: str, fixed_size: bool) -> Optional[str]:
    """The word the chip and the Size group share for a live policy."""
    name = policy_tail(policy)
    if name == "Fixed" and fixed_size:
        return WORD_FIXED
    if name in _FILL_POLICIES:
        return WORD_FILL
    if name in _HUG_POLICIES:
        return WORD_HUG
    return None


def outlined_word(class_default_policy: str) -> str:
    """The outlined segment when the file stores no policy on this axis."""
    if policy_tail(class_default_policy) in _FILL_POLICIES:
        return WORD_FILL
    return WORD_HUG


def project_axis(
    *,
    stored_policy: Optional[str],
    minimum: Optional[int],
    maximum: Optional[int],
    class_default_policy: str,
    class_phrase: str,
) -> AxisProjection:
    """Project one axis. ``minimum`` and ``maximum`` are that axis only."""
    phrase = class_phrase.strip() or "widget"
    if stored_policy is None:
        default_name = policy_tail(class_default_policy) or "Preferred"
        word = outlined_word(default_name)
        if default_name in _SOFT_DEFAULTS:
            caption = (
                "Default for %s: hugs its content, and grows when nothing else wants the room."
                % _articled(phrase)
            )
        else:
            caption = "Default for %s" % _articled(phrase)
        return AxisProjection(word, False, False, None, default_name, caption)
    name = policy_tail(stored_policy)
    locked = (
        minimum is not None
        and maximum is not None
        and minimum == maximum
        and maximum < QWIDGET_SIZE_MAX
    )
    word = effective_word(name, locked)
    if word is None:
        clause = _CUSTOM_CLAUSE.get(name, "is a policy the three words do not name")
        caption = (
            "Custom: %s — %s. Change it in All properties, or pick a word to replace it."
            % (name, clause)
        )
        return AxisProjection(None, False, True, None, name, caption)
    pixels = minimum if word == WORD_FIXED else None
    return AxisProjection(word, True, False, pixels, name, "")


def encode_axis(
    *,
    axis: str,
    word: str,
    pixels: Optional[int],
    current_policy: Optional[SizePolicyValue],
    current_minimum: Optional[SizeValue],
    current_maximum: Optional[SizeValue],
    class_default_h: str,
    class_default_v: str,
) -> SizingWrite:
    """Store ``word`` on one axis. The other axis keeps what it already has."""
    if word not in WORDS:
        raise ValueError(word)
    if word == WORD_FIXED and pixels is None:
        raise ValueError("Fixed needs a pixel size")
    horizontal = current_policy.hsizetype if current_policy is not None else policy_tail(class_default_h)
    vertical = current_policy.vsizetype if current_policy is not None else policy_tail(class_default_v)
    horstretch = current_policy.horstretch if current_policy is not None else 0
    verstretch = current_policy.verstretch if current_policy is not None else 0
    min_w, min_h = _pair(current_minimum, 0)
    max_w, max_h = _pair(current_maximum, QWIDGET_SIZE_MAX)
    if axis == "h":
        horizontal, min_w, max_w = _apply_word(word, pixels, min_w, max_w)
    else:
        vertical, min_h, max_h = _apply_word(word, pixels, min_h, max_h)
    return _pack(horizontal, vertical, horstretch, verstretch, min_w, min_h, max_w, max_h)


def reset_words(
    *,
    current_policy: Optional[SizePolicyValue],
    current_minimum: Optional[SizeValue],
    current_maximum: Optional[SizeValue],
) -> SizingWrite:
    """Delete the stored policy and any Fixed lock. A plain minimum stays."""
    min_w, min_h = _pair(current_minimum, 0)
    max_w, max_h = _pair(current_maximum, QWIDGET_SIZE_MAX)
    if _locked(min_w, max_w):
        min_w, max_w = 0, QWIDGET_SIZE_MAX
    if _locked(min_h, max_h):
        min_h, max_h = 0, QWIDGET_SIZE_MAX
    return SizingWrite(
        None,
        _size_or_none(min_w, min_h, 0),
        _size_or_none(max_w, max_h, QWIDGET_SIZE_MAX),
        True,
        True,
        True,
    )


def clear_property(name: str) -> SizingWrite:
    """Reset one of minimumSize or maximumSize and leave the policy alone."""
    if name == "minimumSize":
        return SizingWrite(None, None, None, False, True, False)
    if name == "maximumSize":
        return SizingWrite(None, None, None, False, False, True)
    raise ValueError(name)


def share_slots(document: UiDocument, node_id: NodeId) -> Tuple[ShareSlot, ...]:
    """Box and grid stretch for ``node_id``. Form layouts and splitters have none."""
    parent = document.parent(node_id)
    if not isinstance(parent, LayoutItemNode):
        return ()
    layout = document.parent(parent.id)
    if not isinstance(layout, LayoutNode):
        return ()
    kind = layout.class_name
    if kind == "QVBoxLayout":
        return _box_slot(layout, parent, "v")
    if kind == "QHBoxLayout":
        return _box_slot(layout, parent, "h")
    if kind == "QGridLayout":
        found = []
        if parent.column is not None:
            found.append(ShareSlot(layout.id, "columnstretch", int(parent.column), "h"))
        if parent.row is not None:
            found.append(ShareSlot(layout.id, "rowstretch", int(parent.row), "v"))
        return tuple(found)
    return ()


def stretch_at(value: Optional[str], index: int) -> int:
    if value is None or index < 0:
        return 0
    parts = value.split(",")
    if index >= len(parts):
        return 0
    text = parts[index].strip()
    if text.startswith("-"):
        body = text[1:]
    else:
        body = text
    if not body.isdigit():
        return 0
    return int(text)


def splice_stretch(current: Optional[str], index: int, value: int, length: int) -> Optional[str]:
    """Replace one cell. All zeros deletes the attribute so the file omits it."""
    if index < 0:
        raise ValueError(index)
    width = max(length, index + 1)
    parts = [0] * width
    if current:
        for at, piece in enumerate(current.split(",")):
            if at >= width:
                parts.append(0)
            text = piece.strip()
            if text.lstrip("-").isdigit():
                parts[at] = int(text)
    if index >= len(parts):
        parts.extend([0] * (index + 1 - len(parts)))
    parts[index] = int(value)
    if all(item == 0 for item in parts):
        return None
    return ",".join(str(item) for item in parts)


def explain(width: int, height: int, axes: Sequence[AxisFacts], *, qt_names: bool) -> str:
    """The "why is it this size?" paragraph. Every number comes from ``axes``."""
    lines = ["%d × %d px." % (int(width), int(height))]
    if any(axis.canvas_empty for axis in axes):
        lines.append(
            "The canvas shows empty layouts bigger so you can drop into them; that size isn't saved."
        )
    for axis in axes:
        if axis.form_label_width is not None and axis.name == "Width":
            lines.append("Labels are as wide as the longest label, %d px." % int(axis.form_label_width))
        sentence = _axis_sentence(axis)
        if qt_names and axis.policy and sentence:
            sentence = "%s (%s)" % (sentence, policy_tail(axis.policy))
        if sentence:
            lines.append(sentence)
    return " ".join(lines)


def effective_preview_points(
    base_points: float,
    text_factor: float,
    screen_percent: int,
    absolute: Optional[float],
) -> float:
    if absolute is not None:
        return float(absolute)
    return float(base_points) * float(text_factor) * (float(screen_percent) / 100.0)


def preview_pill(
    base_points: float,
    text_factor: float,
    screen_percent: int,
    absolute: Optional[float],
    cut_off: int,
) -> Optional[str]:
    """None when the preview matches the saved font and 100% screen.

    Screen scale is its own clause. It does not also count as larger text.
    """
    larger = False
    smaller = False
    if absolute is not None:
        if float(absolute) > float(base_points) + 0.05:
            larger = True
        elif float(absolute) < float(base_points) - 0.05:
            smaller = True
    elif float(text_factor) > 1.001:
        larger = True
    elif float(text_factor) < 0.999:
        smaller = True
    screen_changed = int(screen_percent) != 100
    if not larger and not smaller and not screen_changed and cut_off <= 0:
        return None
    bits = []
    if larger:
        bits.append("Previewing larger text")
    elif smaller:
        bits.append("Previewing smaller text")
    if screen_changed:
        if bits:
            bits.append("%d%% screen" % int(screen_percent))
        else:
            bits.append("Previewing %d%% screen" % int(screen_percent))
    if not bits:
        bits.append("Previewing")
    text = " · ".join(bits)
    if cut_off > 0:
        noun = "widget" if cut_off == 1 else "widgets"
        text = "%s · %d %s cut off text" % (text, int(cut_off), noun)
    return "%s · Reset" % text


def _axis_sentence(axis: AxisFacts) -> str:
    if axis.fixed and axis.word == WORD_FIXED:
        return "%s is fixed at %d px." % (axis.name, int(axis.size if axis.minimum == axis.maximum else axis.minimum))
    if axis.word == WORD_FILL and axis.maximum_set and axis.size >= axis.maximum:
        return "%s would fill, but stops at its maximum of %d px." % (axis.name, int(axis.maximum))
    if axis.word == WORD_FILL and axis.stretch > 0 and axis.stretch_sum > 0:
        return "It gets %d of every %d px of spare room (share %d of %d)." % (
            int(axis.stretch),
            int(axis.stretch_sum),
            int(axis.stretch),
            int(axis.stretch_sum),
        )
    if axis.word == WORD_FILL:
        parent = axis.parent_phrase or "layout"
        return "%s fills the room the %s gives it." % (axis.name, parent)
    if axis.squeezed:
        floor = axis.minimum if axis.minimum_set else axis.minimum
        return (
            "%s is squeezed below the %d px it asks for, because the window is too narrow. "
            "It can't go below %d px."
        ) % (axis.name, int(axis.hint), int(floor))
    if axis.grew:
        return "%s grew past the %d px it asks for, because nothing else wanted the room." % (
            axis.name,
            int(axis.hint),
        )
    if axis.minimum_set and axis.size <= axis.minimum:
        return "%s can't go below its minimum of %d px." % (axis.name, int(axis.minimum))
    if axis.word == WORD_HUG or axis.word is None:
        kind = axis.class_phrase or "widget"
        return "%s is what a %s needs for its content: %d px." % (axis.name, kind, int(axis.hint))
    return ""


def _apply_word(word: str, pixels: Optional[int], low: int, high: int) -> Tuple[str, int, int]:
    if word == WORD_HUG:
        return "Fixed", 0, QWIDGET_SIZE_MAX
    if word == WORD_FILL:
        return "Expanding", 0, QWIDGET_SIZE_MAX
    size = int(pixels or 0)
    return "Fixed", size, size


def _pack(
    horizontal: str,
    vertical: str,
    horstretch: int,
    verstretch: int,
    min_w: int,
    min_h: int,
    max_w: int,
    max_h: int,
) -> SizingWrite:
    return SizingWrite(
        SizePolicyValue(horizontal, vertical, int(horstretch), int(verstretch)),
        _size_or_none(min_w, min_h, 0),
        _size_or_none(max_w, max_h, QWIDGET_SIZE_MAX),
        True,
        True,
        True,
    )


def _pair(size: Optional[SizeValue], fallback: int) -> Tuple[int, int]:
    if size is None:
        return fallback, fallback
    return int(size.width), int(size.height)


def _locked(low: int, high: int) -> bool:
    return low == high and high < QWIDGET_SIZE_MAX


def _size_or_none(width: int, height: int, empty: int) -> Optional[SizeValue]:
    if width == empty and height == empty:
        return None
    return SizeValue(int(width), int(height))


def _box_slot(layout: LayoutNode, item: LayoutItemNode, axis: str) -> Tuple[ShareSlot, ...]:
    try:
        index = layout.items.index(item)
    except ValueError:
        return ()
    return (ShareSlot(layout.id, "stretch", index, axis),)


def _articled(phrase: str) -> str:
    article = "an" if phrase[:1].lower() in "aeiou" else "a"
    return "%s %s" % (article, phrase)
