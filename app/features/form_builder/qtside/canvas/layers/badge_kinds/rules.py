"""Rule badges. Orders sit below the event mark."""

from __future__ import annotations

import json
from typing import Any

from app.features.form_builder.qtside.canvas.layers.badge_kinds import BadgeKind

_WHEN = ("cbcsEnabledWhen", "cbcsVisibleWhen", "cbcsReadOnlyWhen")


def _text(node: object, key: str) -> str:
    if node is None:
        return ""
    value = node.value(key) if hasattr(node, "value") else None
    text = getattr(value, "text", None)
    return text.strip() if isinstance(text, str) else ""


def _calculated(node: object, facts: Any) -> bool:
    del facts
    return bool(_text(node, "cbcsValue"))


def _conditional(node: object, facts: Any) -> bool:
    del facts
    return any(_text(node, key) for key in _WHEN)


def _checks(node: object, facts: Any) -> bool:
    del facts
    raw = _text(node, "cbcsValidate")
    if not raw:
        return False
    try:
        parsed = json.loads(raw)
    except ValueError:
        return False
    return isinstance(parsed, list) and len(parsed) > 0


def _calculated_sentence(node: object, facts: Any) -> str:
    del node, facts
    return "This value is calculated."


def _conditional_sentence(node: object, facts: Any) -> str:
    del node, facts
    return "A rule controls this widget."


def _checks_sentence(node: object, facts: Any) -> str:
    del node, facts
    return "This field has checks."


def register(registry: Any) -> None:
    registry.add(BadgeKind("calculated", 10, "=", _calculated, _calculated_sentence))
    registry.add(BadgeKind("conditional", 20, "?", _conditional, _conditional_sentence))
    registry.add(BadgeKind("checks", 30, "!", _checks, _checks_sentence))
