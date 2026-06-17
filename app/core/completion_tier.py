"""Shared completion tier presentation constants (presentation boundary)."""

from __future__ import annotations

from typing import Protocol

TIER_HEADER_SIDE_EFFECT = "tier_header"


class _TierHeaderInspectable(Protocol):
    side_effect_risk: str


def is_tier_header_item(item: _TierHeaderInspectable) -> bool:
    """Return whether ``item`` is a non-selectable tier section header row."""
    return item.side_effect_risk == TIER_HEADER_SIDE_EFFECT


__all__ = ["TIER_HEADER_SIDE_EFFECT", "is_tier_header_item"]
