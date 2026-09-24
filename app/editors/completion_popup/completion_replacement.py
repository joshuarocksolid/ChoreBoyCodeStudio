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

    Prefers the live identifier under the cursor when a stored range is missing
    or lags behind typed characters (stale empty-prefix paint).
    """

    live_start, live_end = identifier_span_before(source_text, cursor_position)
    if item.replacement_start is None or item.replacement_end is None:
        return live_start, live_end
    return (
        min(item.replacement_start, live_start),
        max(item.replacement_end, live_end),
    )
