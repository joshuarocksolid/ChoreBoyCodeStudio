"""The event badge (UX-ARR-001). Glyph U+203A, the mark the canvas already paints."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.qtside.canvas.layers.badge_kinds import BadgeKind

_GLYPH = "\u203a"


def applies(node: object, facts: Any) -> bool:
    del node
    return bool(getattr(facts, "events", ()))


def sentence(node: object, facts: Any) -> str:
    del node
    from app.features.form_builder.qtside.canvas.layers.logic_badges import _tip

    return _tip(facts.document, facts.sender, facts.events)


def register(registry: Any) -> None:
    registry.add(BadgeKind("events", 100, _GLYPH, applies, sentence))
