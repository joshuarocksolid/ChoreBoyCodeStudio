"""The checks badge. Order 200 keeps the event glyph (order 100) first when both apply."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.engine.logic.checks import read_checks
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.canvas.layers.badge_kinds import BadgeKind

_GLYPH = "\u2713"


def _text(node: object) -> str:
    value = getattr(node, "value", None)
    if not callable(value):
        return ""
    found = value("cbcsValidate")
    if isinstance(found, StringValue):
        return found.text
    return ""


def _count(node: object) -> int:
    text = _text(node)
    if not text.strip():
        return 0
    read = read_checks(text)
    if read.error is not None:
        return 0
    return len(read.checks)


def applies(node: object, facts: Any) -> bool:
    del facts
    return _count(node) > 0


def sentence(node: object, facts: Any) -> str:
    del facts
    count = _count(node)
    if count == 1:
        return "1 check"
    return "%d checks" % count


def register(registry: Any) -> None:
    registry.add(BadgeKind("checks", 200, _GLYPH, applies, sentence))
