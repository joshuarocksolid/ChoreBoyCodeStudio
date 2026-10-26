"""One shop folder for this process: Online/Offline reachability and the journal push."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple, Union

from app.core.errors import ProjectStructureValidationError
from app.features.shop_sharing.model import (
    PRIOR_TAIL_LENGTH,
    HistoryAppend,
    HostRef,
    Machine,
    Present,
    RecentRef,
    RecentRow,
    RecentsAddMissing,
    RecentsForget,
    RecentsPutFirst,
    ShopDoc,
    ShopFolder,
    ShopMarker,
    ShopOp,
    Unreadable,
    classify_project,
    fold,
    prune_candidates,
    ref_from_json,
    resolve_ref,
    settings_patch,
)
from app.features.shop_sharing.storage import LocalShopFiles, probe_shop_folder, read_shop_doc, write_shop_doc
from app.project.project_service import validate_openable_project_root

_LOGGER = logging.getLogger(__name__)

RECHECK_INTERVAL_SECONDS = 10.0


@dataclass(frozen=True)
class Online:
    checked_at: float
    marker: ShopMarker


@dataclass(frozen=True)
class Offline:
    checked_at: float


Reachability = Union[Online, Offline]


@dataclass(frozen=True)
class LinkStatus:
    reachable: bool
    last_synced_at: Optional[datetime]
    pending_count: int
    marker: Optional[ShopMarker]


@dataclass(frozen=True)
class LocalDocumentsCopy:
    """What turn_off writes into the local files, and what turn_on copies into a new folder."""

    settings: dict[str, Any]
    recent_paths: Tuple[str, ...]
    history: Tuple[str, ...]


class ShopLink:
    """Owns one shop folder. GUI thread only.

    Every shared write, online or offline, appends one op to the local journal
    and then syncs. Syncing probes the folder, pushes the journal when online,
    and reports a reachability flip through ``on_change(documents_reloaded)``.
    A read is ``fold(journal, base)`` where base is the shared file when online
    and present, else the mirror. Reads never change reachability.
    """

    def __init__(
        self,
        folder: ShopFolder,
        local: LocalShopFiles,
        machine: Machine,
        *,
        monotonic: Callable[[], float],
        utc_now: Callable[[], datetime],
        on_change: Callable[[bool], None],
    ) -> None:
        self.folder = folder
        self._local = local
        self._machine = machine
        self._monotonic = monotonic
        self._utc_now = utc_now
        self._on_change = on_change
        self._marker: Optional[ShopMarker] = None
        if local.mirror_folder() != folder.path:
            local.reset_mirror(folder.path)
        self._state = self._probe()
        if isinstance(self._state, Online):
            self._push()

    @property
    def settings_path(self) -> Path:
        return self.folder.path / ShopDoc.SETTINGS.value

    def load_settings(self) -> dict[str, Any]:
        return self._view(ShopDoc.SETTINGS)

    def save_settings(self, *, base: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
        """Journal the leaf diff from ``base`` to ``new`` and return the document the session now has.

        Both sides get the Settings dialog's default fill first, so a default the
        dialog filled in cancels out and only real edits are written.
        """
        from app.shell.settings_models import normalize_global_settings_payload

        patch = settings_patch(
            normalize_global_settings_payload(base),
            normalize_global_settings_payload(new),
            op_id=_new_op_id(),
        )
        if not patch.is_empty:
            self._commit(patch)
        return self._view(ShopDoc.SETTINGS)

    def recent_rows(self) -> list[RecentRow]:
        """Stored order, resolved for this machine. Prunes missing entries only while online."""
        entries = self._view(ShopDoc.RECENTS).get("projects", [])
        refs = [ref for ref in (ref_from_json(entry) for entry in entries) if ref is not None]
        candidates = self._prune_candidates(refs)
        if candidates:
            self._state = self._probe()
            candidates = self._prune_candidates(refs)
            if candidates:
                self._commit(RecentsForget(op_id=_new_op_id(), refs=candidates))
        forgotten = set(candidates)
        return [self._row(ref) for ref in refs if ref not in forgotten]

    def remember_project(self, project_root: str) -> None:
        ref = classify_project(project_root, folder=self.folder, hostname=self._machine.hostname)
        self._commit(RecentsPutFirst(op_id=_new_op_id(), ref=ref))

    def load_console_history(self, *, max_entries: int) -> list[str]:
        history = _history_lines(self._view(ShopDoc.HISTORY))
        return history[-max_entries:] if max_entries > 0 else []

    def append_console_history(self, lines: Sequence[str], *, max_entries: int) -> None:
        if not lines:
            return
        prior_tail = tuple(_history_lines(self._view(ShopDoc.HISTORY))[-PRIOR_TAIL_LENGTH:])
        self._commit(
            HistoryAppend(op_id=_new_op_id(), lines=tuple(lines), prior_tail=prior_tail, max_entries=max_entries)
        )

    def add_missing_recents(self, project_roots: Sequence[str]) -> None:
        refs = tuple(
            classify_project(root, folder=self.folder, hostname=self._machine.hostname) for root in project_roots
        )
        if refs:
            self._commit(RecentsAddMissing(op_id=_new_op_id(), refs=refs))

    def documents_for_turn_off(self) -> LocalDocumentsCopy:
        refs = [ref_from_json(entry) for entry in self._view(ShopDoc.RECENTS).get("projects", [])]
        paths = (resolve_ref(ref, folder=self.folder, hostname=self._machine.hostname) for ref in refs if ref)
        return LocalDocumentsCopy(
            settings=self._view(ShopDoc.SETTINGS),
            recent_paths=tuple(path for path in paths if path is not None),
            history=tuple(_history_lines(self._view(ShopDoc.HISTORY))),
        )

    def check(self, *, throttled: bool) -> bool:
        """Activation path. Returns True when reachability flipped or the share was written."""
        if throttled and self._monotonic() - self._state.checked_at < RECHECK_INTERVAL_SECONDS:
            return False
        return self._sync()

    def status_fields(self) -> LinkStatus:
        return LinkStatus(
            reachable=isinstance(self._state, Online),
            last_synced_at=self._local.last_synced_at(),
            pending_count=len(self._local.read_journal()),
            marker=self._marker,
        )

    def _commit(self, op: ShopOp) -> None:
        self._local.append_journal(op)
        self._sync()

    def _sync(self) -> bool:
        was_online = isinstance(self._state, Online)
        self._state = self._probe()
        wrote = self._push() if isinstance(self._state, Online) else False
        now_online = isinstance(self._state, Online)
        if now_online != was_online:
            self._on_change(now_online)
            return True
        return wrote

    def _probe(self) -> Reachability:
        marker = probe_shop_folder(self.folder.path)
        now = self._monotonic()
        if marker is None:
            return Offline(now)
        self._marker = marker
        return Online(now, marker)

    def _push(self) -> bool:
        """Apply the journal to the shared files. An Unreadable document keeps its ops pending."""
        ops = self._local.read_journal()
        if not ops:
            return False
        applied: set[str] = set()
        for doc in ShopDoc:
            doc_ops = [op for op in ops if op.doc is doc]
            if not doc_ops:
                continue
            read = read_shop_doc(self.folder.path, doc)
            if isinstance(read, Unreadable):
                _LOGGER.warning("Shop %s is unreadable, keeping changes pending: %s", doc.value, read.reason)
                continue
            current = read.payload if isinstance(read, Present) else self._local.read_mirror(doc)
            merged = fold(doc_ops, doc, current)
            try:
                write_shop_doc(self.folder.path, doc, merged, hostname=self._machine.hostname)
            except OSError as exc:
                _LOGGER.warning("Shop folder write failed, staying offline: %s", exc)
                self._state = Offline(self._monotonic())
                break
            self._local.write_mirror(doc, merged)
            applied.update(op.op_id for op in doc_ops)
        self._local.drop_journal_ops(applied)
        if applied:
            self._local.mark_synced(self._utc_now())
        return bool(applied)

    def _view(self, doc: ShopDoc) -> dict[str, Any]:
        base: Optional[dict[str, Any]] = None
        if isinstance(self._state, Online):
            read = read_shop_doc(self.folder.path, doc)
            if isinstance(read, Present):
                base = read.payload
                if self._local.read_mirror(doc) != base:
                    self._local.write_mirror(doc, base)
                self._local.mark_synced(self._utc_now())
        if base is None:
            base = self._local.read_mirror(doc)
        return fold(self._local.read_journal(), doc, base)

    def _prune_candidates(self, refs: Sequence[RecentRef]) -> Tuple[RecentRef, ...]:
        return prune_candidates(
            refs,
            hostname=self._machine.hostname,
            exists=self._openable_ref,
            online=isinstance(self._state, Online),
        )

    def _openable_ref(self, ref: RecentRef) -> bool:
        path = resolve_ref(ref, folder=self.folder, hostname=self._machine.hostname)
        # No path on this machine is not evidence the project is gone.
        if path is None:
            return True
        return _openable(path)

    def _row(self, ref: RecentRef) -> RecentRow:
        path = resolve_ref(ref, folder=self.folder, hostname=self._machine.hostname)
        if path is not None:
            return RecentRow(path=path, label=Path(path).name, host=None, available=_openable(path))
        if isinstance(ref, HostRef):
            return RecentRow(path=ref.path, label=Path(ref.path).name, host=ref.host, available=False)
        return RecentRow(path=ref.rel, label=Path(ref.rel).name, host=None, available=False)


def _openable(path: str) -> bool:
    try:
        validate_openable_project_root(path)
    except (ProjectStructureValidationError, ValueError, OSError):
        return False
    return True


def _history_lines(payload: Mapping[str, Any]) -> list[str]:
    history = payload.get("history")
    if not isinstance(history, list):
        return []
    return [entry for entry in history if isinstance(entry, str) and entry.strip()]


def _new_op_id() -> str:
    return uuid.uuid4().hex
