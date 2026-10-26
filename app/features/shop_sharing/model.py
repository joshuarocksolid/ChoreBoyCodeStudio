"""Shop sharing types and pure reducers. No filesystem writes.

Every shared write is one of the ``ShopOp`` types. Each op carries its own
``apply(payload) -> payload`` reducer, so the online push and the offline view
fold the same ops the same way.
"""

from __future__ import annotations

import copy
import enum
import os
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, ClassVar, Literal, Mapping, Optional, Sequence, Tuple, Union, get_args

KeyPath = Tuple[str, ...]
ChoiceSource = Literal["settings", "prompt", "converted"]

SHOP_FOLDER_NAME = "Code Studio Settings"
MARKER_FILENAME = "shop.json"
PRIOR_TAIL_LENGTH = 3


class ShopDoc(enum.Enum):
    """The three shared documents. The value is the file name in the shop folder and the mirror."""

    SETTINGS = "settings.json"
    RECENTS = "shop_recent_projects.json"
    HISTORY = "python_console_history.json"

    def empty(self) -> dict[str, Any]:
        if self is ShopDoc.SETTINGS:
            return {"schema_version": 1}
        if self is ShopDoc.RECENTS:
            return {"schema_version": 2, "projects": []}
        return {"history": []}


@dataclass(frozen=True)
class Machine:
    """This computer as the feature sees it.

    ``local_state`` is ``resolve_global_state_root(None)`` in production.
    ``default_home`` is ``/home/default``; it is a field so tests never read it.
    """

    home: Path
    hostname: str
    local_state: Path
    default_home: Path = Path("/home/default")

    @classmethod
    def current(cls) -> "Machine":
        from app.bootstrap.paths import resolve_global_state_root

        return cls(
            home=Path(os.path.abspath(str(Path.home()))),
            hostname=socket.gethostname(),
            local_state=resolve_global_state_root(None),
        )


@dataclass(frozen=True)
class ShopFolder:
    """A shop folder as seen from this machine.

    ``path`` is logical (``os.path.abspath``), never ``Path.resolve()``d.
    ``share_root`` is ``path.parent``: recents ``share`` entries are relative to it.
    ``label`` is the share-root child name ("net1") when the folder sits under
    ``<top share>/<child>/``, otherwise this machine's hostname.
    """

    path: Path
    share_root: Path
    label: str


@dataclass(frozen=True)
class ShopMarker:
    """Parsed ``shop.json``. ``created_at`` is None when missing or unparseable."""

    created_by_host: str
    created_at: Optional[datetime]


@dataclass(frozen=True)
class DiscoveredShop:
    folder: Path
    label: str
    marker: ShopMarker


@dataclass(frozen=True)
class ShopChoice:
    folder: Path
    decided_at: str
    source: ChoiceSource


@dataclass(frozen=True)
class LocalChoice:
    declined_folder: Optional[Path]
    decided_at: str
    source: ChoiceSource


@dataclass(frozen=True)
class NoChoice:
    """No choice file. The only state that runs legacy conversion or prompts."""


@dataclass(frozen=True)
class CorruptChoice:
    """The file exists but cannot be parsed. Treated as decided-local and never overwritten silently."""

    reason: str


ChoiceRead = Union[ShopChoice, LocalChoice, NoChoice, CorruptChoice]


@dataclass(frozen=True)
class Present:
    payload: dict[str, Any]


@dataclass(frozen=True)
class Absent:
    """The folder is a readable directory and the file is not there."""


@dataclass(frozen=True)
class Unreadable:
    """The file cannot be read, is empty, or is not a JSON object, or the folder is gone.
    Never treat this as ``{}``: writes for the document stay pending."""

    reason: str


DocRead = Union[Present, Absent, Unreadable]


@dataclass(frozen=True)
class ShareRef:
    """A project under the shop's share root. ``rel`` is POSIX, relative, with no ``..``."""

    rel: str


@dataclass(frozen=True)
class HostRef:
    """A project outside the share. Only ``host == this machine`` is ever opened or pruned."""

    host: str
    path: str


RecentRef = Union[ShareRef, HostRef]


@dataclass(frozen=True)
class RecentRow:
    """One recent project for the UI.

    ``path`` is this machine's absolute path, or the other host's path as stored.
    ``host`` is set only for another machine's project, and then ``available`` is False.
    """

    path: str
    label: str
    host: Optional[str]
    available: bool


def ref_from_json(entry: object) -> Optional[RecentRef]:
    """``{"share": rel}`` or ``{"host", "path"}``. Anything else is None and is kept untouched by reducers."""
    if not isinstance(entry, dict):
        return None
    share = entry.get("share")
    if isinstance(share, str) and _is_clean_rel(share):
        return ShareRef(share)
    host = entry.get("host")
    path = entry.get("path")
    if isinstance(host, str) and host and isinstance(path, str) and os.path.isabs(path):
        return HostRef(host, path)
    return None


def ref_to_json(ref: RecentRef) -> dict[str, str]:
    if isinstance(ref, ShareRef):
        return {"share": ref.rel}
    return {"host": ref.host, "path": ref.path}


def classify_project(project_root: str, *, folder: ShopFolder, hostname: str) -> RecentRef:
    """ShareRef when ``project_root`` is inside ``folder.share_root``, else ``HostRef(hostname, project_root)``.

    Containment is checked on logical paths first, then on realpaths of both sides,
    because ``validate_openable_project_root`` hands back a resolved path. The
    realpath is only compared, never stored.
    """
    logical_root = os.path.abspath(project_root)
    rel = _relative_inside(logical_root, os.path.abspath(str(folder.share_root)))
    if rel is None:
        rel = _relative_inside(os.path.realpath(logical_root), os.path.realpath(str(folder.share_root)))
    if rel is not None:
        return ShareRef(rel)
    return HostRef(hostname, logical_root)


def resolve_ref(ref: RecentRef, *, folder: ShopFolder, hostname: str) -> Optional[str]:
    """Absolute path on this machine, or None for another host's entry."""
    if isinstance(ref, ShareRef):
        return str(folder.share_root.joinpath(*ref.rel.split("/")))
    if ref.host == hostname:
        return ref.path
    return None


def _relative_inside(path: str, root: str) -> Optional[str]:
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        return None
    rel = Path(rel).as_posix()
    if rel == "." or not _is_clean_rel(rel):
        return None
    return rel


def _is_clean_rel(rel: str) -> bool:
    if not rel or rel.startswith("/"):
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


def strict_equal(left: Any, right: Any) -> bool:
    """JSON equality where ``True`` is not ``1`` and ``1`` is not ``1.0``."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(strict_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(strict_equal(a, b) for a, b in zip(left, right))
    return bool(left == right)


@dataclass(frozen=True)
class SettingsPatch:
    """Leaf diff between two settings payloads.

    Each set path points at a non-dict value or an empty dict, so another
    machine's sibling keys under the same parent survive. Each removed path is
    a leaf the base knew about. Lists are leaves. ``apply`` is idempotent.
    """

    kind: ClassVar[str] = "settings_patch"
    doc: ClassVar[ShopDoc] = ShopDoc.SETTINGS
    op_id: str
    set_leaves: Tuple[Tuple[KeyPath, Any], ...]
    removed_leaves: Tuple[KeyPath, ...]

    @property
    def is_empty(self) -> bool:
        return not self.set_leaves and not self.removed_leaves

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(dict(payload))
        for path, value in self.set_leaves:
            parent = result
            for key in path[:-1]:
                child = parent.get(key)
                if not isinstance(child, dict):
                    child = {}
                    parent[key] = child
                parent = child
            parent[path[-1]] = copy.deepcopy(value)
        for path in self.removed_leaves:
            parent = result
            for key in path[:-1]:
                child = parent.get(key)
                if not isinstance(child, dict):
                    break
                parent = child
            else:
                current = parent.get(path[-1])
                if path[-1] in parent and not (isinstance(current, dict) and current):
                    del parent[path[-1]]
        return result

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "op_id": self.op_id,
            "set": [[list(path), value] for path, value in self.set_leaves],
            "removed": [list(path) for path in self.removed_leaves],
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "SettingsPatch":
        return cls(
            op_id=_require_str(raw, "op_id"),
            set_leaves=tuple((_key_path(item[0]), item[1]) for item in _require_list(raw, "set")),
            removed_leaves=tuple(_key_path(item) for item in _require_list(raw, "removed")),
        )


@dataclass(frozen=True)
class RecentsPutFirst:
    """Remember a project: move or insert ``ref`` at index 0. No cap. Idempotent."""

    kind: ClassVar[str] = "recents_put_first"
    doc: ClassVar[ShopDoc] = ShopDoc.RECENTS
    op_id: str
    ref: RecentRef

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        entries = [entry for entry in _recent_entries(payload) if ref_from_json(entry) != self.ref]
        return _with_recent_entries(payload, [ref_to_json(self.ref)] + entries)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "op_id": self.op_id, "ref": ref_to_json(self.ref)}

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "RecentsPutFirst":
        return cls(op_id=_require_str(raw, "op_id"), ref=_require_ref(raw.get("ref")))


@dataclass(frozen=True)
class RecentsAddMissing:
    """Join: append refs not already present, at the end, in order. Idempotent."""

    kind: ClassVar[str] = "recents_add_missing"
    doc: ClassVar[ShopDoc] = ShopDoc.RECENTS
    op_id: str
    refs: Tuple[RecentRef, ...]

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        entries = _recent_entries(payload)
        present = {ref_from_json(entry) for entry in entries}
        for ref in self.refs:
            if ref not in present:
                entries.append(ref_to_json(ref))
                present.add(ref)
        return _with_recent_entries(payload, entries)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "op_id": self.op_id, "refs": [ref_to_json(ref) for ref in self.refs]}

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "RecentsAddMissing":
        return cls(op_id=_require_str(raw, "op_id"), refs=tuple(_require_ref(item) for item in _require_list(raw, "refs")))


@dataclass(frozen=True)
class RecentsForget:
    """Prune. Built only from ``prune_candidates`` while online, so never another host's entry. Idempotent."""

    kind: ClassVar[str] = "recents_forget"
    doc: ClassVar[ShopDoc] = ShopDoc.RECENTS
    op_id: str
    refs: Tuple[RecentRef, ...]

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        forget = set(self.refs)
        entries = [entry for entry in _recent_entries(payload) if ref_from_json(entry) not in forget]
        return _with_recent_entries(payload, entries)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "op_id": self.op_id, "refs": [ref_to_json(ref) for ref in self.refs]}

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "RecentsForget":
        return cls(op_id=_require_str(raw, "op_id"), refs=tuple(_require_ref(item) for item in _require_list(raw, "refs")))


@dataclass(frozen=True)
class HistoryAppend:
    """Append this session's console lines, skipping a line equal to the current last
    line, then trim the oldest to ``max_entries``.

    ``prior_tail`` is the list tail this session saw before the append. When
    ``prior_tail`` followed by the appended lines is already a contiguous window
    of the list, the op was pushed before and replay is a no-op.
    """

    kind: ClassVar[str] = "history_append"
    doc: ClassVar[ShopDoc] = ShopDoc.HISTORY
    op_id: str
    lines: Tuple[str, ...]
    prior_tail: Tuple[str, ...]
    max_entries: int

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        history = [entry for entry in _history_entries(payload)]
        if self.prior_tail and _contains_window(history, _append_lines(list(self.prior_tail), self.lines)):
            return _with_history(payload, history)
        history = _append_lines(history, self.lines)
        return _with_history(payload, history[-self.max_entries :] if self.max_entries > 0 else [])

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "op_id": self.op_id,
            "lines": list(self.lines),
            "prior_tail": list(self.prior_tail),
            "max_entries": self.max_entries,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "HistoryAppend":
        max_entries = raw.get("max_entries")
        if not isinstance(max_entries, int) or isinstance(max_entries, bool):
            raise ValueError("max_entries")
        return cls(
            op_id=_require_str(raw, "op_id"),
            lines=tuple(_require_str_items(raw, "lines")),
            prior_tail=tuple(_require_str_items(raw, "prior_tail")),
            max_entries=max_entries,
        )


ShopOp = Union[SettingsPatch, RecentsPutFirst, RecentsAddMissing, RecentsForget, HistoryAppend]
_OP_BY_KIND = {op_type.kind: op_type for op_type in get_args(ShopOp)}


def op_from_json(raw: object) -> Optional[ShopOp]:
    """Unknown kind or malformed is None. The journal reader drops it."""
    if not isinstance(raw, dict):
        return None
    op_type = _OP_BY_KIND.get(raw.get("kind"))  # type: ignore[arg-type]
    if op_type is None:
        return None
    try:
        return op_type.from_json(raw)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def fold(ops: Sequence[ShopOp], doc: ShopDoc, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Apply, in order, the ops whose ``doc`` is ``doc``."""
    result = copy.deepcopy(dict(payload))
    for op in ops:
        if op.doc is doc:
            result = op.apply(result)
    return result


def settings_patch(base: Mapping[str, Any], new: Mapping[str, Any], *, op_id: str) -> SettingsPatch:
    """Leaf diff from ``base`` to ``new``. Leaf equality is type-strict."""
    set_leaves: list[Tuple[KeyPath, Any]] = []
    removed_leaves: list[KeyPath] = []

    def walk(old: Mapping[str, Any], current: Mapping[str, Any], prefix: KeyPath) -> None:
        for key, value in current.items():
            path = prefix + (key,)
            if key not in old:
                set_leaves.extend(_leaves(value, path))
            elif isinstance(old[key], dict) and isinstance(value, dict):
                walk(old[key], value, path)
            elif not strict_equal(old[key], value):
                set_leaves.extend(_leaves(value, path))
        for key, value in old.items():
            if key not in current:
                removed_leaves.extend(path for path, _ in _leaves(value, prefix + (key,)))

    walk(base, new, ())
    return SettingsPatch(op_id=op_id, set_leaves=tuple(set_leaves), removed_leaves=tuple(removed_leaves))


def prune_candidates(
    refs: Sequence[RecentRef],
    *,
    hostname: str,
    exists: Callable[[RecentRef], bool],
    online: bool,
) -> Tuple[RecentRef, ...]:
    """Spec pruning. Empty unless online. Never returns another host's entry."""
    if not online:
        return ()
    return tuple(
        ref
        for ref in refs
        if (isinstance(ref, ShareRef) or ref.host == hostname) and not exists(ref)
    )


class SharingMode(enum.Enum):
    SHOP = "shop"
    LOCAL = "local"
    PINNED = "pinned"


@dataclass(frozen=True)
class ShopStatus:
    """Snapshot for the chip, the Settings status line, and the tooltip.

    ``mode != SHOP`` implies folder, label, last_synced_at, and created_* are
    None, ``reachable`` is False, and ``pending_count`` is 0.
    """

    mode: SharingMode
    folder: Optional[Path]
    label: Optional[str]
    reachable: bool
    last_synced_at: Optional[datetime]
    pending_count: int
    created_by_host: Optional[str]
    created_at: Optional[datetime]


@dataclass(frozen=True)
class SharingChanged:
    """``documents_reloaded``: settings, recents, or history may differ from what the window shows."""

    status: ShopStatus
    documents_reloaded: bool


@dataclass(frozen=True)
class SharingResult:
    """``ok`` is ``error == ""``. ``created`` is True only when turn_on created a new shop folder."""

    error: str = ""
    created: bool = False

    @property
    def ok(self) -> bool:
        return not self.error


def _leaves(value: Any, path: KeyPath) -> list[Tuple[KeyPath, Any]]:
    if isinstance(value, dict) and value:
        found: list[Tuple[KeyPath, Any]] = []
        for key, child in value.items():
            found.extend(_leaves(child, path + (key,)))
        return found
    return [(path, copy.deepcopy(value))]


def _recent_entries(payload: Mapping[str, Any]) -> list[Any]:
    projects = payload.get("projects")
    return list(projects) if isinstance(projects, list) else []


def _with_recent_entries(payload: Mapping[str, Any], entries: list[Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(payload))
    result["schema_version"] = 2
    result["projects"] = copy.deepcopy(entries)
    return result


def _history_entries(payload: Mapping[str, Any]) -> list[str]:
    history = payload.get("history")
    if not isinstance(history, list):
        return []
    return [entry for entry in history if isinstance(entry, str) and entry.strip()]


def _with_history(payload: Mapping[str, Any], history: list[str]) -> dict[str, Any]:
    result = copy.deepcopy(dict(payload))
    result["history"] = history
    return result


def _append_lines(history: list[str], lines: Sequence[str]) -> list[str]:
    for line in lines:
        if not history or history[-1] != line:
            history.append(line)
    return history


def _contains_window(history: Sequence[str], window: Sequence[str]) -> bool:
    size = len(window)
    return any(list(history[start : start + size]) == list(window) for start in range(len(history) - size + 1))


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(key)
    return value


def _require_list(raw: Mapping[str, Any], key: str) -> list[Any]:
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(key)
    return value


def _require_str_items(raw: Mapping[str, Any], key: str) -> list[str]:
    items = _require_list(raw, key)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(key)
    return items


def _require_ref(raw: object) -> RecentRef:
    ref = ref_from_json(raw)
    if ref is None:
        raise ValueError("ref")
    return ref


def _key_path(raw: object) -> KeyPath:
    if not isinstance(raw, list) or not raw or not all(isinstance(key, str) for key in raw):
        raise ValueError("key path")
    return tuple(raw)
