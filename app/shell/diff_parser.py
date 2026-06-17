"""Pure diff parsing and side-by-side buffer alignment for :class:`DiffView`."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

LINE_KIND_CONTEXT = "context"
LINE_KIND_ADD = "add"
LINE_KIND_REMOVE = "remove"
LINE_KIND_HEADER = "header"
LINE_KIND_FILE_LABEL = "file_label"


@dataclass
class DiffLine:
    """One classified line in a unified diff."""

    kind: str
    text: str
    old_no: Optional[int] = None
    new_no: Optional[int] = None


@dataclass
class DiffHunk:
    """One @@ ... @@ block with classified lines."""

    header: str
    old_start: int
    new_start: int
    lines: List[DiffLine] = field(default_factory=list)


@dataclass
class DiffStats:
    """Aggregate counts for a diff."""

    added: int
    removed: int

    @property
    def is_empty(self) -> bool:
        return self.added == 0 and self.removed == 0


def compute_diff_hunks(
    before_text: str,
    after_text: str,
    *,
    from_label: str = "before",
    to_label: str = "after",
) -> tuple[list[DiffHunk], DiffStats, str]:
    """Return parsed hunks, aggregate stats, and the raw unified-diff text.

    The third return value is the full ``difflib.unified_diff`` text
    (suitable for ``QPlainTextEdit.setPlainText``); the hunks list is
    used by the gutter and the side-by-side renderer.
    """

    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
    )
    raw_text = "\n".join(diff_lines)

    hunks: list[DiffHunk] = []
    current_hunk: Optional[DiffHunk] = None
    old_cursor = 0
    new_cursor = 0
    added = 0
    removed = 0

    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            old_start, new_start = _parse_hunk_header(line)
            current_hunk = DiffHunk(
                header=line,
                old_start=old_start,
                new_start=new_start,
            )
            hunks.append(current_hunk)
            old_cursor = old_start
            new_cursor = new_start
            continue
        if current_hunk is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.lines.append(
                DiffLine(kind=LINE_KIND_ADD, text=line[1:], new_no=new_cursor)
            )
            new_cursor += 1
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.lines.append(
                DiffLine(kind=LINE_KIND_REMOVE, text=line[1:], old_no=old_cursor)
            )
            old_cursor += 1
            removed += 1
        else:
            payload = line[1:] if line.startswith(" ") else line
            current_hunk.lines.append(
                DiffLine(
                    kind=LINE_KIND_CONTEXT,
                    text=payload,
                    old_no=old_cursor,
                    new_no=new_cursor,
                )
            )
            old_cursor += 1
            new_cursor += 1

    return hunks, DiffStats(added=added, removed=removed), raw_text


def _parse_hunk_header(header: str) -> tuple[int, int]:
    """Best-effort parse of '@@ -1,3 +1,4 @@' style hunk headers."""
    try:
        body = header.split("@@")[1].strip()
        parts = body.split()
        old_part = parts[0].lstrip("-").split(",")[0]
        new_part = parts[1].lstrip("+").split(",")[0]
        return int(old_part), int(new_part)
    except (IndexError, ValueError):
        return 1, 1


def inline_gutter_numbers(
    raw_text: str, hunks: Iterable[DiffHunk]
) -> tuple[list[Optional[int]], list[Optional[int]]]:
    """Compute per-line gutter numbers for the inline (unified) view.

    The inline editor displays the raw unified-diff text — including
    ``---`` / ``+++`` / ``@@`` lines — so the numbering must be aligned
    line-for-line with that text.
    """

    old_numbers: list[Optional[int]] = []
    new_numbers: list[Optional[int]] = []
    if not raw_text:
        return old_numbers, new_numbers

    hunks_iter = iter(hunks)
    current_hunk: Optional[DiffHunk] = next(hunks_iter, None)
    old_cursor = 0
    new_cursor = 0

    for line in raw_text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            old_numbers.append(None)
            new_numbers.append(None)
            continue
        if line.startswith("@@"):
            if current_hunk is not None:
                old_cursor = current_hunk.old_start
                new_cursor = current_hunk.new_start
                current_hunk = next(hunks_iter, None)
            old_numbers.append(None)
            new_numbers.append(None)
            continue
        if line.startswith("+"):
            old_numbers.append(None)
            new_numbers.append(new_cursor)
            new_cursor += 1
        elif line.startswith("-"):
            old_numbers.append(old_cursor)
            new_numbers.append(None)
            old_cursor += 1
        else:
            old_numbers.append(old_cursor)
            new_numbers.append(new_cursor)
            old_cursor += 1
            new_cursor += 1

    return old_numbers, new_numbers


def side_by_side_buffers(
    hunks: Iterable[DiffHunk],
) -> tuple[
    list[str], list[str], dict[int, str], dict[int, str], list[Optional[int]], list[Optional[int]]
]:
    """Build aligned side-by-side text and per-line classifications.

    Removed lines pad the right pane with empty rows, additions pad the
    left pane.  Returns ``(before_lines, after_lines, before_kinds,
    after_kinds, before_numbers, after_numbers)`` where ``*_kinds`` map
    a 0-based block number to ``add`` / ``remove`` / ``gap`` / context
    (absent).
    """

    before_lines: list[str] = []
    after_lines: list[str] = []
    before_kinds: dict[int, str] = {}
    after_kinds: dict[int, str] = {}
    before_numbers: list[Optional[int]] = []
    after_numbers: list[Optional[int]] = []

    for hunk_index, hunk in enumerate(hunks):
        if hunk_index > 0:
            before_lines.append("")
            after_lines.append("")
            before_numbers.append(None)
            after_numbers.append(None)
            before_kinds[len(before_lines) - 1] = "gap"
            after_kinds[len(after_lines) - 1] = "gap"

        index = 0
        line_count = len(hunk.lines)
        while index < line_count:
            line = hunk.lines[index]
            if line.kind == LINE_KIND_CONTEXT:
                before_lines.append(line.text)
                after_lines.append(line.text)
                before_numbers.append(line.old_no)
                after_numbers.append(line.new_no)
                index += 1
                continue

            removes: list[DiffLine] = []
            adds: list[DiffLine] = []
            while index < line_count and hunk.lines[index].kind == LINE_KIND_REMOVE:
                removes.append(hunk.lines[index])
                index += 1
            while index < line_count and hunk.lines[index].kind == LINE_KIND_ADD:
                adds.append(hunk.lines[index])
                index += 1

            paired = max(len(removes), len(adds))
            for slot in range(paired):
                remove_line = removes[slot] if slot < len(removes) else None
                add_line = adds[slot] if slot < len(adds) else None
                if remove_line is not None:
                    before_lines.append(remove_line.text)
                    before_numbers.append(remove_line.old_no)
                    before_kinds[len(before_lines) - 1] = LINE_KIND_REMOVE
                else:
                    before_lines.append("")
                    before_numbers.append(None)
                    before_kinds[len(before_lines) - 1] = "gap"
                if add_line is not None:
                    after_lines.append(add_line.text)
                    after_numbers.append(add_line.new_no)
                    after_kinds[len(after_lines) - 1] = LINE_KIND_ADD
                else:
                    after_lines.append("")
                    after_numbers.append(None)
                    after_kinds[len(after_lines) - 1] = "gap"

    if not before_lines:
        before_lines = [""]
        after_lines = [""]
        before_numbers = [None]
        after_numbers = [None]

    return (
        before_lines,
        after_lines,
        before_kinds,
        after_kinds,
        before_numbers,
        after_numbers,
    )
