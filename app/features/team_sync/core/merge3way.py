"""CBCS three-way merge. dulwich's merge needs GPL merge3, so this is ours.

Line merge is diff3 over difflib.SequenceMatcher. The tree merge turns that
into file results: clean bytes, a deletion, or clashes the combine session
holds until Finish.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from app.features.team_sync.api import DiffHunk

WHOLE_FILE_BYTES = 1024 * 1024
CLASH_CONTEXT = 2
DIFF_CONTEXT = 3


@dataclass(frozen=True)
class LineClash:
    line: int
    base: Tuple[str, ...]
    ours: Tuple[str, ...]
    theirs: Tuple[str, ...]
    context_before: Tuple[str, ...]
    context_after: Tuple[str, ...]


@dataclass(frozen=True)
class LinePiece:
    text: Tuple[str, ...] = ()
    clash: Optional[LineClash] = None


@dataclass(frozen=True)
class LineMerge:
    pieces: Tuple[LinePiece, ...]

    @property
    def clashes(self) -> Tuple[LineClash, ...]:
        return tuple(piece.clash for piece in self.pieces if piece.clash is not None)

    def merged_lines(self) -> Optional[Tuple[str, ...]]:
        if self.clashes:
            return None
        lines: List[str] = []
        for piece in self.pieces:
            lines.extend(piece.text)
        return tuple(lines)


@dataclass(frozen=True)
class TreeClash:
    path: str
    kind: str
    line: int
    base_lines: Tuple[str, ...]
    ours_lines: Tuple[str, ...]
    theirs_lines: Tuple[str, ...]
    context_before: Tuple[str, ...]
    context_after: Tuple[str, ...]
    pieces: Tuple[LinePiece, ...]
    ours_present: bool
    theirs_present: bool
    ours_bytes: Optional[bytes]
    theirs_bytes: Optional[bytes]
    sep: str
    trailing: bool


@dataclass(frozen=True)
class TreeMerge:
    """Complete result tree. Missing paths are deletions. Clashes are not in ``files``."""

    files: Dict[str, Optional[bytes]]
    clashes: Tuple[TreeClash, ...]


def both_lines(ours: Sequence[str], theirs: Sequence[str]) -> Tuple[str, ...]:
    """Ours then theirs, unless one single line is a prefix of the other."""

    if len(ours) == 1 and len(theirs) == 1:
        left, right = ours[0], theirs[0]
        if left == right:
            return (left,)
        if left and right.startswith(left):
            return (right,)
        if right and left.startswith(right):
            return (left,)
    return tuple(ours) + tuple(theirs)


def inspect_text(data: bytes) -> Tuple[Tuple[str, ...], str, bool]:
    """Split bytes into lines, the newline spell they use, and whether one trails."""

    if data == b"":
        return (), "\n", False
    raw_sep = b"\r\n" if b"\r\n" in data else b"\n"
    trailing = data.endswith(raw_sep)
    body = data[: -len(raw_sep)] if trailing else data
    if body == b"":
        parts = [b""] if trailing else []
    else:
        parts = body.split(raw_sep)
    lines = tuple(part.decode("utf-8", "surrogateescape") for part in parts)
    return lines, raw_sep.decode("ascii"), trailing


def join_lines(lines: Sequence[str], sep: str, trailing: bool) -> bytes:
    raw_sep = sep.encode("ascii")
    body = raw_sep.join(line.encode("utf-8", "surrogateescape") for line in lines)
    if trailing and lines:
        body += raw_sep
    return body


def is_binary_payload(data: Optional[bytes]) -> bool:
    if not data:
        return False
    return b"\0" in data[:8192]


def whole_file_kind(path: str, ours: bytes, theirs: bytes) -> Optional[str]:
    """Return form/binary when the file must clash as a whole, else None."""

    if path.lower().endswith(".ui"):
        return "form"
    if is_binary_payload(ours) or is_binary_payload(theirs):
        return "binary"
    if len(ours) > WHOLE_FILE_BYTES or len(theirs) > WHOLE_FILE_BYTES:
        return "binary"
    return None


def diff_hunks(
    old: Sequence[str],
    new: Sequence[str],
    context: int = DIFF_CONTEXT,
) -> Tuple[DiffHunk, ...]:
    matcher = difflib.SequenceMatcher(a=list(old), b=list(new), autojunk=False)
    hunks: List[DiffHunk] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        hunks.append(
            DiffHunk(
                old_start=i1 + 1,
                old_lines=tuple(old[i1:i2]),
                new_start=j1 + 1,
                new_lines=tuple(new[j1:j2]),
                context_before=tuple(old[max(0, i1 - context) : i1]),
                context_after=tuple(old[i2 : i2 + context]),
            )
        )
    return tuple(hunks)


def merge_lines(
    base: Sequence[str],
    ours: Sequence[str],
    theirs: Sequence[str],
) -> LineMerge:
    """Diff3. Non-overlapping and identical edits merge. Overlaps clash."""

    ours_hunks = _hunks(base, ours)
    theirs_hunks = _hunks(base, theirs)
    pieces: List[LinePiece] = []
    i = 0
    j = 0
    pos = 0
    while i < len(ours_hunks) or j < len(theirs_hunks):
        if (
            i < len(ours_hunks)
            and j < len(theirs_hunks)
            and _hunks_overlap(ours_hunks[i], theirs_hunks[j])
        ):
            span_s, span_e, taken_o, taken_t, i, j = _gather_cluster(
                base, ours_hunks, theirs_hunks, i, j
            )
            if span_s > pos:
                pieces.append(LinePiece(text=tuple(base[pos:span_s])))
            ours_lines = _materialize(base, taken_o, span_s, span_e)
            theirs_lines = _materialize(base, taken_t, span_s, span_e)
            if ours_lines == theirs_lines:
                if ours_lines:
                    pieces.append(LinePiece(text=tuple(ours_lines)))
            else:
                before = _emitted_tail(pieces, CLASH_CONTEXT)
                pieces.append(
                    LinePiece(
                        clash=LineClash(
                            line=len(_materialize(base, ours_hunks, 0, span_s)) + 1,
                            base=tuple(base[span_s:span_e]),
                            ours=tuple(ours_lines),
                            theirs=tuple(theirs_lines),
                            context_before=before,
                            context_after=tuple(base[span_e : span_e + CLASH_CONTEXT]),
                        )
                    )
                )
            pos = span_e
            continue
        take_ours = j >= len(theirs_hunks) or (
            i < len(ours_hunks) and ours_hunks[i][0] <= theirs_hunks[j][0]
        )
        if take_ours:
            start, end, lines = ours_hunks[i]
            i += 1
        else:
            start, end, lines = theirs_hunks[j]
            j += 1
        if start > pos:
            pieces.append(LinePiece(text=tuple(base[pos:start])))
        if lines:
            pieces.append(LinePiece(text=lines))
        pos = max(pos, end)
    if pos < len(base):
        pieces.append(LinePiece(text=tuple(base[pos:])))
    return LineMerge(pieces=tuple(pieces))


def merge_trees(
    base: Dict[str, bytes],
    ours: Dict[str, bytes],
    theirs: Dict[str, bytes],
) -> TreeMerge:
    files: Dict[str, Optional[bytes]] = {}
    clashes: List[TreeClash] = []
    for path in sorted(set(base) | set(ours) | set(theirs)):
        base_bytes = base.get(path)
        ours_bytes = ours.get(path)
        theirs_bytes = theirs.get(path)
        if ours_bytes == theirs_bytes:
            files[path] = ours_bytes
            continue
        if base_bytes == ours_bytes:
            files[path] = theirs_bytes
            continue
        if base_bytes == theirs_bytes:
            files[path] = ours_bytes
            continue
        if ours_bytes is None or theirs_bytes is None:
            clashes.append(
                _deleted_clash(path, base_bytes, ours_bytes, theirs_bytes)
            )
            continue
        if base_bytes is None:
            clashes.append(_add_add_clash(path, ours_bytes, theirs_bytes))
            continue
        kind = whole_file_kind(path, ours_bytes, theirs_bytes)
        if kind is not None:
            clashes.append(_whole_clash(path, kind, ours_bytes, theirs_bytes))
            continue
        merged = _merge_text_file(path, base_bytes, ours_bytes, theirs_bytes)
        if isinstance(merged, bytes):
            files[path] = merged
        else:
            clashes.extend(merged)
    return TreeMerge(files=files, clashes=tuple(clashes))


def render_pieces(
    pieces: Sequence[LinePiece],
    resolutions: Dict[int, Tuple[str, ...]],
    sep: str,
    trailing: bool,
) -> bytes:
    """Apply per-clash line tuples. ``resolutions`` is keyed by clash order."""

    lines: List[str] = []
    clash_index = 0
    for piece in pieces:
        if piece.clash is None:
            lines.extend(piece.text)
            continue
        chosen = resolutions.get(clash_index)
        if chosen is None:
            raise ValueError("a line clash is still open")
        lines.extend(chosen)
        clash_index += 1
    return join_lines(lines, sep, trailing)


def _hunks(
    base: Sequence[str], other: Sequence[str]
) -> List[Tuple[int, int, Tuple[str, ...]]]:
    matcher = difflib.SequenceMatcher(a=list(base), b=list(other), autojunk=False)
    found: List[Tuple[int, int, Tuple[str, ...]]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        found.append((i1, i2, tuple(other[j1:j2])))
    return found


def _ranges_overlap(start: int, end: int, other_start: int, other_end: int) -> bool:
    if start == end and other_start == other_end:
        return start == other_start
    if start == end:
        return other_start <= start < other_end
    if other_start == other_end:
        return start <= other_start < end
    return start < other_end and other_start < end


def _hunks_overlap(
    left: Tuple[int, int, Tuple[str, ...]],
    right: Tuple[int, int, Tuple[str, ...]],
) -> bool:
    return _ranges_overlap(left[0], left[1], right[0], right[1])


def _hunk_overlaps_span(
    hunk: Tuple[int, int, Tuple[str, ...]], span_start: int, span_end: int
) -> bool:
    return _ranges_overlap(hunk[0], hunk[1], span_start, span_end)


def _gather_cluster(
    base: Sequence[str],
    ours_hunks: Sequence[Tuple[int, int, Tuple[str, ...]]],
    theirs_hunks: Sequence[Tuple[int, int, Tuple[str, ...]]],
    i: int,
    j: int,
) -> Tuple[int, int, List[Tuple[int, int, Tuple[str, ...]]], List[Tuple[int, int, Tuple[str, ...]]], int, int]:
    del base
    span_s = min(ours_hunks[i][0], theirs_hunks[j][0])
    span_e = max(ours_hunks[i][1], theirs_hunks[j][1])
    taken_o: List[Tuple[int, int, Tuple[str, ...]]] = []
    taken_t: List[Tuple[int, int, Tuple[str, ...]]] = []
    oi = i
    ti = j
    while True:
        grew = False
        while oi < len(ours_hunks) and _hunk_overlaps_span(ours_hunks[oi], span_s, span_e):
            start, end, _lines = ours_hunks[oi]
            taken_o.append(ours_hunks[oi])
            span_s = min(span_s, start)
            span_e = max(span_e, end)
            oi += 1
            grew = True
        while ti < len(theirs_hunks) and _hunk_overlaps_span(theirs_hunks[ti], span_s, span_e):
            start, end, _lines = theirs_hunks[ti]
            taken_t.append(theirs_hunks[ti])
            span_s = min(span_s, start)
            span_e = max(span_e, end)
            ti += 1
            grew = True
        if not grew:
            break
    return span_s, span_e, taken_o, taken_t, oi, ti


def _materialize(
    base: Sequence[str],
    hunks: Sequence[Tuple[int, int, Tuple[str, ...]]],
    start: int,
    end: int,
) -> List[str]:
    lines: List[str] = []
    pos = start
    for hunk_start, hunk_end, hunk_lines in hunks:
        if hunk_end < start or (hunk_start == hunk_end and hunk_start < start):
            continue
        if hunk_start > end or (hunk_start == hunk_end and hunk_start >= end):
            continue
        if hunk_start >= end:
            continue
        if hunk_start > pos:
            lines.extend(base[pos:min(hunk_start, end)])
            pos = min(hunk_start, end)
        if hunk_start == hunk_end:
            if start <= hunk_start < end:
                lines.extend(hunk_lines)
            continue
        lines.extend(hunk_lines)
        pos = hunk_end
    if pos < end:
        lines.extend(base[pos:end])
    return lines


def _emitted_tail(pieces: Sequence[LinePiece], count: int) -> Tuple[str, ...]:
    lines: List[str] = []
    for piece in pieces:
        lines.extend(piece.text)
    return tuple(lines[-count:])


def _style_of(data: Optional[bytes], fallback: bytes) -> Tuple[str, bool]:
    source = data if data is not None else fallback
    _lines, sep, trailing = inspect_text(source)
    return sep, trailing


def _merge_text_file(
    path: str, base: bytes, ours: bytes, theirs: bytes
) -> Union[bytes, List[TreeClash]]:
    base_lines, _base_sep, _base_trailing = inspect_text(base)
    ours_lines, sep, trailing = inspect_text(ours)
    theirs_lines, _sep, _trailing = inspect_text(theirs)
    merged = merge_lines(base_lines, ours_lines, theirs_lines)
    if merged.clashes:
        clashes: List[TreeClash] = []
        for clash in merged.clashes:
            clashes.append(
                TreeClash(
                    path=path,
                    kind="lines",
                    line=clash.line,
                    base_lines=clash.base,
                    ours_lines=clash.ours,
                    theirs_lines=clash.theirs,
                    context_before=clash.context_before,
                    context_after=clash.context_after,
                    pieces=merged.pieces,
                    ours_present=True,
                    theirs_present=True,
                    ours_bytes=ours,
                    theirs_bytes=theirs,
                    sep=sep,
                    trailing=trailing,
                )
            )
        return clashes
    lines = merged.merged_lines() or ()
    return join_lines(lines, sep, trailing)


def _text_lines(data: Optional[bytes]) -> Tuple[str, ...]:
    if data is None or is_binary_payload(data):
        return ()
    lines, _sep, _trailing = inspect_text(data)
    return lines


def _deleted_clash(
    path: str,
    base: Optional[bytes],
    ours: Optional[bytes],
    theirs: Optional[bytes],
) -> TreeClash:
    present = ours if ours is not None else theirs if theirs is not None else base or b""
    sep, trailing = _style_of(present, b"")
    return TreeClash(
        path=path,
        kind="deleted",
        line=0,
        base_lines=_text_lines(base),
        ours_lines=_text_lines(ours),
        theirs_lines=_text_lines(theirs),
        context_before=(),
        context_after=(),
        pieces=(),
        ours_present=ours is not None,
        theirs_present=theirs is not None,
        ours_bytes=ours,
        theirs_bytes=theirs,
        sep=sep,
        trailing=trailing,
    )


def _add_add_clash(path: str, ours: bytes, theirs: bytes) -> TreeClash:
    kind = whole_file_kind(path, ours, theirs) or "lines"
    return _whole_clash(path, kind, ours, theirs)


def _whole_clash(path: str, kind: str, ours: bytes, theirs: bytes) -> TreeClash:
    sep, trailing = _style_of(ours, theirs)
    ours_lines = _text_lines(ours) if kind == "lines" else ()
    theirs_lines = _text_lines(theirs) if kind == "lines" else ()
    return TreeClash(
        path=path,
        kind=kind,
        line=1 if kind == "lines" else 0,
        base_lines=(),
        ours_lines=ours_lines,
        theirs_lines=theirs_lines,
        context_before=(),
        context_after=(),
        pieces=(),
        ours_present=True,
        theirs_present=True,
        ours_bytes=ours,
        theirs_bytes=theirs,
        sep=sep,
        trailing=trailing,
    )
