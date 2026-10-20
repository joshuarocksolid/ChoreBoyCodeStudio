"""Hug, Fill, and Fixed, stored as plain Qt properties. No Qt imports.

Per axis:

- Hug   -> size policy Fixed (or Maximum): the widget stays at the size its content asks for.
- Fill  -> size policy Expanding (or MinimumExpanding, Ignored): it takes the spare room.
           "Share" is the policy stretch on that axis.
- Fixed -> policy Fixed plus minimum = maximum = N on that axis.
- Auto  -> no policy in the file; the class default applies (most grow only if nothing else wants the room).

Every change returns commands. Values that go back to the default delete the
property line instead of writing the default ("Reset deletes the line").
"""

from __future__ import annotations

from typing import Optional

from spikes.form_builder.commands import Compound, SetProperty
from spikes.form_builder.model import Property, Widget, XmlNode, get_property

QT_MAX = 16777215
FILL = {"Expanding", "MinimumExpanding", "Ignored"}
HUG = {"Fixed", "Maximum"}
AXES = {"h": 0, "v": 1}


def read_size(node, name: str) -> Optional[tuple[int, int]]:
    prop = get_property(node, name)
    if prop is None or prop.body.tag != "size":
        return None
    values = {child.tag: child.text for child in prop.body.children}
    try:
        return int(values.get("width", "0")), int(values.get("height", "0"))
    except ValueError:
        return None


def read_policy(node) -> Optional[dict]:
    prop = get_property(node, "sizePolicy")
    if prop is None or prop.body.tag != "sizepolicy":
        return None
    stretch = {child.tag: child.text for child in prop.body.children}
    return {
        "h": prop.body.attrib.get("hsizetype", "Preferred"),
        "v": prop.body.attrib.get("vsizetype", "Preferred"),
        "hs": int(stretch.get("horstretch", "0") or 0),
        "vs": int(stretch.get("verstretch", "0") or 0),
    }


def axis_mode(node, axis: str, class_default: tuple[str, str]) -> tuple[str, Optional[int], bool]:
    """Return (mode, fixed value, explicit) for one axis. Mode is hug, fill, fixed, or auto."""
    index = AXES[axis]
    low = read_size(node, "minimumSize")
    high = read_size(node, "maximumSize")
    if low and high and low[index] == high[index] and low[index] > 0:
        return "fixed", low[index], True
    policy = read_policy(node)
    explicit = policy is not None and policy[axis] != class_default[index]
    name = policy[axis] if policy is not None else class_default[index]
    if name in FILL:
        return "fill", None, explicit
    if name in HUG:
        return "hug", None, explicit
    return "auto", None, explicit


def share_of(node, axis: str) -> int:
    policy = read_policy(node)
    if policy is None:
        return 0
    return policy["hs" if axis == "h" else "vs"]


def policy_property(h: str, v: str, hs: int = 0, vs: int = 0) -> Property:
    body = XmlNode(
        "sizepolicy",
        {"hsizetype": h, "vsizetype": v},
        "",
        [XmlNode("horstretch", {}, str(hs)), XmlNode("verstretch", {}, str(vs))],
    )
    return Property({"name": "sizePolicy"}, body)


def size_property(name: str, width: int, height: int) -> Property:
    body = XmlNode("size", {}, "", [XmlNode("width", {}, str(width)), XmlNode("height", {}, str(height))])
    return Property({"name": name}, body)


def _policy_command(node: Widget, policy: dict, class_default: tuple[str, str]):
    if policy["h"] == class_default[0] and policy["v"] == class_default[1] and not policy["hs"] and not policy["vs"]:
        if get_property(node, "sizePolicy") is None:
            return None
        return SetProperty(node.id, "sizePolicy", None)
    return SetProperty(node.id, "sizePolicy", policy_property(policy["h"], policy["v"], policy["hs"], policy["vs"]))


def _size_commands(node: Widget, axis: str, value: Optional[int]) -> list:
    """Set min = max = value on one axis, or clear that axis (None). Lines vanish at defaults."""
    index = AXES[axis]
    steps = []
    for name, default in (("minimumSize", 0), ("maximumSize", QT_MAX)):
        current = list(read_size(node, name) or (default, default))
        current[index] = default if value is None else value
        if current == [default, default]:
            if get_property(node, name) is not None:
                steps.append(SetProperty(node.id, name, None))
        elif tuple(current) != read_size(node, name):
            steps.append(SetProperty(node.id, name, size_property(name, current[0], current[1])))
    return steps


def set_axis(node: Widget, axis: str, mode: str, class_default: tuple[str, str], value: Optional[int] = None):
    """Commands that make one axis Hug, Fill, Fixed N, or Auto (the class default)."""
    current = read_policy(node) or {"h": class_default[0], "v": class_default[1], "hs": 0, "vs": 0}
    policy = dict(current)
    index = AXES[axis]
    if mode == "hug":
        policy[axis] = "Fixed"
    elif mode == "fill":
        policy[axis] = "Expanding"
    elif mode == "fixed":
        policy[axis] = "Fixed"
    else:
        policy[axis] = class_default[index]
    if mode != "fill":
        policy["hs" if axis == "h" else "vs"] = 0
    steps = []
    command = _policy_command(node, policy, class_default)
    if command is not None:
        steps.append(command)
    steps.extend(_size_commands(node, axis, value if mode == "fixed" else None))
    if not steps:
        return None
    return steps[0] if len(steps) == 1 else Compound(steps)


def set_share(node: Widget, axis: str, share: Optional[int], class_default: tuple[str, str]):
    """Set the stretch share on an axis. A share above zero implies Fill on that axis."""
    current = read_policy(node) or {"h": class_default[0], "v": class_default[1], "hs": 0, "vs": 0}
    policy = dict(current)
    policy["hs" if axis == "h" else "vs"] = int(share or 0)
    if share and policy[axis] not in FILL:
        policy[axis] = "Expanding"
    return _policy_command(node, policy, class_default)


def reset_size_property(node: Widget, name: str):
    """Reset deletes the line. It never writes 0 x 0."""
    if get_property(node, name) is None:
        return None
    return SetProperty(node.id, name, None)


WORDS = {"hug": "Hug", "fill": "Fill", "fixed": "Fixed", "auto": "Auto"}


def badge(h_mode: str, v_mode: str) -> str:
    return f"{WORDS[h_mode]} × {WORDS[v_mode]}"


def why_sentence(facts: dict) -> str:
    """Explain the live size in plain words.

    facts: class_label, width, height, hint_w, hint_h, h_mode, v_mode, h_policy,
    v_policy, min_w, min_h, max_w, max_h, parent (layout words or ""), share_h, share_v,
    fixed_w, fixed_h.
    """
    parts = [f"{facts['width']} × {facts['height']} px."]
    for axis, word in (("h", "Width"), ("v", "Height")):
        mode = facts[f"{axis}_mode"]
        size = facts["width"] if axis == "h" else facts["height"]
        hint = facts["hint_w"] if axis == "h" else facts["hint_h"]
        policy = facts[f"{axis}_policy"]
        share = facts.get(f"share_{axis}", 0)
        if mode == "fixed":
            parts.append(f"{word} is fixed at {facts['fixed_w' if axis == 'h' else 'fixed_h']} px.")
        elif mode == "fill":
            extra = f" with a share of {share}" if share else ""
            parts.append(f"{word} fills the room {facts['parent'] or 'the form'} gives it{extra} ({policy}).")
        elif mode == "hug":
            parts.append(f"{word} hugs its content: {hint} px is what a {facts['class_label']} asks for ({policy}).")
        else:
            if size > hint + 1:
                parts.append(f"{word} grew past the {hint} px it asks for because nothing else wanted the room ({policy}).")
            else:
                parts.append(f"{word} is the {hint} px it asks for; it grows only when nothing else wants the room ({policy}).")
    limits = []
    if facts["min_w"] or facts["min_h"]:
        limits.append(f"minimum {facts['min_w']} × {facts['min_h']}")
    if facts["max_w"] < QT_MAX or facts["max_h"] < QT_MAX:
        max_w = "any" if facts["max_w"] >= QT_MAX else facts["max_w"]
        max_h = "any" if facts["max_h"] >= QT_MAX else facts["max_h"]
        limits.append(f"maximum {max_w} × {max_h}")
    if limits:
        parts.append("Limits: " + ", ".join(limits) + ".")
    return " ".join(parts)
