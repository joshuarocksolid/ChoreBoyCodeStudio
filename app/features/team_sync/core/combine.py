"""Combine sessions. Finish is the first moment merged bytes touch the worktree."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.team_sync.api import (
    CLASH_BINARY,
    CLASH_DELETED,
    CLASH_FORM,
    CLASH_LINES,
    RESOLVE_BOTH,
    RESOLVE_DELETE,
    RESOLVE_OURS,
    RESOLVE_TEXT_PREFIX,
    RESOLVE_THEIRS,
    Clash,
    CombineState,
    Resolution,
)
from app.features.team_sync.core import TeamSyncError
from app.features.team_sync.core.mailbox import atomic_write_bytes
from app.features.team_sync.core.merge3way import (
    LinePiece,
    TreeMerge,
    both_lines,
    inspect_text,
    join_lines,
    render_pieces,
)

_KINDS = {
    "lines": CLASH_LINES,
    "form": CLASH_FORM,
    "binary": CLASH_BINARY,
    "deleted": CLASH_DELETED,
}


class CombineSession:
    def __init__(self, project_root: str) -> None:
        self.root = Path(project_root)
        self.path = self.root / ".git" / "cbcs" / "combine.json"

    def load(self) -> Optional[CombineState]:
        raw = self._read()
        if raw is None:
            return None
        return _state(raw)

    def meta(self) -> Dict[str, object]:
        raw = self._require()
        return {
            "id": raw["id"],
            "kind": raw["kind"],
            "note": raw["note"],
            "ours": raw["ours"],
            "theirs": raw["theirs"],
            "base": raw.get("base", ""),
            "incoming_id": raw.get("incoming_id", ""),
            "theirs_from": raw["theirs_from"],
            "aside_index": raw.get("aside_index"),
        }

    def start(
        self,
        *,
        session_id: str,
        kind: str,
        theirs_from: str,
        note: str,
        ours: str,
        theirs: str,
        base: str,
        incoming_id: str,
        merge: TreeMerge,
        aside_index: Optional[int] = None,
    ) -> CombineState:
        if self.path.is_file():
            raise TeamSyncError("Finish or cancel the combine already open.")
        clashes = []
        for index, clash in enumerate(merge.clashes):
            clashes.append(
                {
                    "id": f"{clash.path}#{index}",
                    "path": clash.path,
                    "kind": clash.kind,
                    "line": clash.line,
                    "ours": list(clash.ours_lines),
                    "theirs": list(clash.theirs_lines),
                    "base": list(clash.base_lines),
                    "context_before": list(clash.context_before),
                    "context_after": list(clash.context_after),
                    "resolution": None,
                    "ours_present": clash.ours_present,
                    "theirs_present": clash.theirs_present,
                    "ours_b64": _b64(clash.ours_bytes),
                    "theirs_b64": _b64(clash.theirs_bytes),
                    "sep": clash.sep,
                    "trailing": clash.trailing,
                    "pieces": [
                        {"text": list(piece.text), "clash": piece.clash is not None}
                        for piece in clash.pieces
                    ],
                }
            )
        raw = {
            "schema_version": 1,
            "id": session_id,
            "kind": kind,
            "theirs_from": theirs_from,
            "note": note,
            "ours": ours,
            "theirs": theirs,
            "base": base,
            "incoming_id": incoming_id,
            "aside_index": aside_index,
            "auto": {path: _b64(data) for path, data in merge.files.items()},
            "clashes": clashes,
        }
        self._write(raw)
        return _state(raw)

    def resolve(self, clash_id: str, resolution: Resolution) -> CombineState:
        raw = self._require()
        _check_resolution(resolution)
        found = False
        for clash in raw["clashes"]:
            if clash["id"] == clash_id:
                clash["resolution"] = resolution
                found = True
                break
        if not found:
            raise TeamSyncError("That clash is not in this combine.")
        self._write(raw)
        return _state(raw)

    def finish_files(self) -> Dict[str, Optional[bytes]]:
        raw = self._require()
        if any(clash["resolution"] is None for clash in raw["clashes"]):
            raise TeamSyncError("Choose every clash before finishing.")
        files: Dict[str, Optional[bytes]] = {}
        for path, payload in raw["auto"].items():
            files[path] = base64.b64decode(payload) if payload is not None else None
        grouped: Dict[str, List[dict]] = {}
        for clash in raw["clashes"]:
            grouped.setdefault(clash["path"], []).append(clash)
        for path, clashes in grouped.items():
            files[path] = _apply_path(clashes)
        return files

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return

    def _require(self) -> dict:
        raw = self._read()
        if raw is None:
            raise TeamSyncError("There is no combine in progress.")
        return raw

    def _read(self) -> Optional[dict]:
        if not self.path.is_file():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TeamSyncError(f"Could not read the combine session: {exc}") from exc
        if not isinstance(payload, dict):
            raise TeamSyncError("The combine session is damaged.")
        return payload

    def _write(self, raw: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(self.path, (json.dumps(raw, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _state(raw: dict) -> CombineState:
    clashes = tuple(
        Clash(
            id=str(item["id"]),
            path=str(item["path"]),
            kind=_KINDS.get(str(item["kind"]), CLASH_LINES),
            line=int(item.get("line") or 0),
            ours=tuple(item.get("ours") or ()),
            theirs=tuple(item.get("theirs") or ()),
            base=tuple(item.get("base") or ()),
            context_before=tuple(item.get("context_before") or ()),
            context_after=tuple(item.get("context_after") or ()),
            resolution=item.get("resolution"),
        )
        for item in raw.get("clashes") or []
    )
    auto_paths = tuple(
        path for path, payload in (raw.get("auto") or {}).items() if payload is not None
    )
    return CombineState(
        id=str(raw.get("id", "")),
        theirs_from=str(raw.get("theirs_from", "")),
        note=str(raw.get("note", "")),
        clashes=clashes,
        auto_paths=auto_paths,
    )


def _apply_path(clashes: Sequence[dict]) -> Optional[bytes]:
    first = clashes[0]
    kind = first["kind"]
    if kind == "lines" and first.get("pieces"):
        pieces = _pieces(first["pieces"])
        resolutions = {}
        clash_ordinal = 0
        for piece in pieces:
            if piece.clash is None:
                continue
            resolutions[clash_ordinal] = _resolved_lines(clashes[clash_ordinal])
            clash_ordinal += 1
        return render_pieces(pieces, resolutions, first["sep"], bool(first["trailing"]))
    return _apply_whole(first)


def _pieces(raw_pieces: Sequence[dict]) -> Tuple[LinePiece, ...]:
    pieces: List[LinePiece] = []
    for item in raw_pieces:
        if item.get("clash"):
            pieces.append(LinePiece(clash=True))  # type: ignore[arg-type]
        else:
            pieces.append(LinePiece(text=tuple(item.get("text") or ())))
    return tuple(pieces)


def _resolved_lines(clash: dict) -> Tuple[str, ...]:
    resolution = clash["resolution"]
    ours = tuple(clash.get("ours") or ())
    theirs = tuple(clash.get("theirs") or ())
    if resolution == RESOLVE_OURS:
        return ours
    if resolution == RESOLVE_THEIRS:
        return theirs
    if resolution == RESOLVE_BOTH:
        return both_lines(ours, theirs)
    if resolution == RESOLVE_DELETE:
        return ()
    if isinstance(resolution, str) and resolution.startswith(RESOLVE_TEXT_PREFIX):
        text = resolution[len(RESOLVE_TEXT_PREFIX) :]
        lines, _sep, _trailing = inspect_text(text.encode("utf-8"))
        return lines
    raise TeamSyncError("That choice is not one Team Sync understands.")


def _apply_whole(clash: dict) -> Optional[bytes]:
    resolution = clash["resolution"]
    if resolution == RESOLVE_DELETE:
        return None
    if resolution == RESOLVE_OURS:
        if not clash.get("ours_present"):
            return None
        return _decode(clash.get("ours_b64"))
    if resolution == RESOLVE_THEIRS:
        if not clash.get("theirs_present"):
            return None
        return _decode(clash.get("theirs_b64"))
    if resolution == RESOLVE_BOTH and clash["kind"] == "lines":
        lines = both_lines(tuple(clash.get("ours") or ()), tuple(clash.get("theirs") or ()))
        return join_lines(lines, clash["sep"], bool(clash["trailing"]))
    if isinstance(resolution, str) and resolution.startswith(RESOLVE_TEXT_PREFIX):
        return resolution[len(RESOLVE_TEXT_PREFIX) :].encode("utf-8")
    raise TeamSyncError("Choose one version of this file.")


def _check_resolution(resolution: Resolution) -> None:
    if resolution in {RESOLVE_OURS, RESOLVE_THEIRS, RESOLVE_BOTH, RESOLVE_DELETE}:
        return
    if isinstance(resolution, str) and resolution.startswith(RESOLVE_TEXT_PREFIX):
        return
    raise TeamSyncError("That choice is not one Team Sync understands.")


def _b64(data: Optional[bytes]) -> Optional[str]:
    if data is None:
        return None
    return base64.b64encode(data).decode("ascii")


def _decode(payload: Optional[str]) -> bytes:
    if not payload:
        return b""
    return base64.b64decode(payload)
