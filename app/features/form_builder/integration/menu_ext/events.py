"""Canvas context menu. No UX clause names a canvas item. The list menu is the section widget."""

from __future__ import annotations


def register(registry: object) -> None:
    # No UX clause names a canvas item. The list menu is the section widget.
    del registry
