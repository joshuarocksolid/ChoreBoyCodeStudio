"""Decide once whether a bridge or slot op exists.

A missing op says so in the command text. A later widget error still means
the op is installed, so the adapter must not treat that as a fallback.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Caps:
    grab: bool = False
    state: bool = False
    drag: bool = False
    dblclick: bool = False
    hover: bool = False
    slot_snapshot: bool = False

    def to_dict(self) -> dict:
        return {
            "grab": self.grab,
            "state": self.state,
            "drag": self.drag,
            "dblclick": self.dblclick,
            "hover": self.hover,
            "slot_snapshot": self.slot_snapshot,
        }


def op_supported(text: str, op: str) -> bool:
    blob = (text or "").lower()
    if "unknown ctl op: " + op.lower() in blob:
        return False
    if "unknown op: " + op.lower() in blob:
        return False
    if "invalid choice" in blob and op.lower() in blob:
        return False
    return True
