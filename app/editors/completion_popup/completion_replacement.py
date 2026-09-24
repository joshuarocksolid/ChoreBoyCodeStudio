"""Shared replacement-range helpers for editor and console completion accept."""

from __future__ import annotations

from dataclasses import replace

from app.intelligence.completion_models import CompletionItem


def identifier_span_before(source_text: str, cursor_position: int) -> tuple[int, int]:
    """Return ``[start, end)`` covering the identifier immediately before the cursor."""

    end = max(0, min(cursor_position, len(source_text)))
    start = end
    while start > 0:
        ch = source_text[start - 1]
        if ch.isalnum() or ch == "_":
            start -= 1
            continue
        break
    return start, end


def retained_replacement_matches_cursor(
    items: list[CompletionItem],
    source_text: str,
    cursor_position: int,
) -> bool:
    """Return whether retained replacement starts still anchor the live identifier.

    Stale starts from a dismissed ``.`` paint must not be reused after the cursor
    moves to a different member access (possibly on another line).
    """

    live_start, live_end = identifier_span_before(source_text, cursor_position)
    stored_starts = {
        item.replacement_start
        for item in items
        if item.replacement_start is not None
    }
    if not stored_starts:
        return True
    if stored_starts != {live_start}:
        return False
    for index in range(live_start, live_end):
        ch = source_text[index]
        if ch == "\n" or ch == "\r" or not (ch.isalnum() or ch == "_"):
            return False
    return True


def items_with_prefix_replacement_range(
    items: list[CompletionItem],
    prefix: str,
) -> list[CompletionItem]:
    """Rewrite item replacement spans so they cover the current typed prefix.

    Dot-trigger paints often arrive with a collapsed span at the member start
    (``replacement_start == replacement_end``). Refining the visible list must
    extend ``replacement_end`` through the typed characters so accept replaces
    them instead of inserting ahead of them.
    """

    prefix_len = len(prefix)
    updated: list[CompletionItem] = []
    for item in items:
        if item.replacement_start is None and item.replacement_end is None:
            updated.append(item)
            continue
        if item.replacement_start is not None:
            member_start = item.replacement_start
        else:
            member_start = int(item.replacement_end or 0)
        updated.append(
            replace(
                item,
                replacement_start=member_start,
                replacement_end=member_start + prefix_len,
            )
        )
    return updated


def resolve_insert_replacement_range(
    source_text: str,
    cursor_position: int,
    item: CompletionItem,
) -> tuple[int, int]:
    """Return the buffer span to replace when accepting ``item``.

    Always replaces only the live identifier under the cursor. Stored item
    ranges must never widen the left edge past that identifier start (a stale
    empty-prefix start from an earlier ``.`` paint would delete intervening
    text).
    """

    _ = item
    return identifier_span_before(source_text, cursor_position)
