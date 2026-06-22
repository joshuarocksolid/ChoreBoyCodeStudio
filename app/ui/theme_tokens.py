"""Minimal theme token contract for shared UI widgets."""

from __future__ import annotations

from typing import Protocol


class HelpThemeTokens(Protocol):
    """Theme fields consumed by help markdown rendering."""

    text_primary: str
    border: str
    badge_bg: str
