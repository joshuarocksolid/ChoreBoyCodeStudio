"""Line ranges the XML view marks as kept as written."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from app.features.form_builder.engine.diagnostics import CODES
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui


@dataclass(frozen=True)
class KeptSpan:
    first_line: int
    last_line: int
    reasons: str


def kept_spans(text: str) -> Tuple[KeptSpan, ...]:
    try:
        result = read_ui(text, allocator=IdAllocator())
    except UiReadError:
        return ()
    raw: List[Tuple[int, int, str]] = []
    for diagnostic in result.diagnostics:
        info = CODES.get(diagnostic.code)
        if info is None or not info.kept_as_written:
            continue
        first = diagnostic.location.line
        if first <= 0:
            continue
        end = diagnostic.location.end_line
        last = end if end >= first else first
        raw.append((first, last, diagnostic.message))
    if not raw:
        return ()
    ordered = sorted(raw, key=lambda item: item[0])
    first, last, message = ordered[0]
    messages = [message]
    merged: List[KeptSpan] = []
    for start, end, message in ordered[1:]:
        if start <= last + 1:
            if end > last:
                last = end
            messages.append(message)
            continue
        merged.append(KeptSpan(first, last, "\n".join(messages)))
        first, last = start, end
        messages = [message]
    merged.append(KeptSpan(first, last, "\n".join(messages)))
    return tuple(merged)
