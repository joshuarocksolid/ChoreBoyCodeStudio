"""Shop sharing: the public module. Persistence callers use ``route_documents``; the UI uses the service."""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Optional, Protocol, Sequence, Union

from app.bootstrap.paths import PathInput
from app.core import constants
from app.features.shop_sharing import legacy
from app.features.shop_sharing.link import LocalDocumentsCopy, ShopLink
from app.features.shop_sharing.model import (
    MARKER_FILENAME,
    SHOP_FOLDER_NAME,
    CorruptChoice,
    DiscoveredShop,
    LocalChoice,
    Machine,
    RecentRow,
    RecentsAddMissing,
    SharingChanged,
    SharingMode,
    SharingResult,
    ShopChoice,
    ShopDoc,
    ShopStatus,
    classify_project,
)
from app.features.shop_sharing.storage import (
    LocalShopFiles,
    create_shop_folder,
    discover_shop_folders,
    logical_path,
    marker_payload,
    probe_shop_folder,
    shop_folder_at,
    write_shop_doc_if_absent,
)

_LOGGER = logging.getLogger(__name__)

CONSOLE_HISTORY_MAX_ENTRIES = 200


class SharedDocuments(Protocol):
    """What routed persistence callers see in shop mode."""

    @property
    def settings_path(self) -> Path: ...

    def load_settings(self) -> dict[str, Any]: ...

    def save_settings(self, *, base: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]: ...

    def recent_rows(self) -> list[RecentRow]: ...

    def remember_project(self, project_root: str) -> None: ...

    def load_console_history(self, *, max_entries: int) -> list[str]: ...

    def append_console_history(self, lines: Sequence[str], *, max_entries: int) -> None: ...


@dataclass(frozen=True)
class DocumentRoute:
    """``shop`` is None for today's local code path.

    ``generation`` changes whenever the documents behind the route may have
    changed: turn on, turn off, back online. ``reloading`` is True while
    listeners run for such a change.
    """

    generation: int
    shop: Optional[SharedDocuments]
    reloading: bool


def route_documents(state_root: Optional[PathInput]) -> DocumentRoute:
    """An explicit ``state_root`` never shares and never builds the service."""
    service = shop_sharing_service(state_root)
    if service is None:
        return DocumentRoute(generation=0, shop=None, reloading=False)
    return DocumentRoute(generation=service.generation, shop=service.documents(), reloading=service.reloading)


_service: Optional["ShopSharingService"] = None
_service_key: Optional[tuple[object, ...]] = None


def shop_sharing_service(state_root: Optional[PathInput] = None) -> Optional["ShopSharingService"]:
    """The process service for this machine, or None for an explicit ``state_root`` (hide sharing UI).

    Built on first use, after logging; bootstrap and migration never call it.
    Rebuilt when HOME, the hostname, or ``CBCS_STATE_ROOT`` changes.
    """
    if state_root is not None:
        return None
    global _service, _service_key
    machine = Machine.current()
    key = (machine, os.environ.get(constants.CBCS_STATE_ROOT_ENV_NAME, ""))
    if _service is None or _service_key != key:
        _service = ShopSharingService(machine)
        _service_key = key
    return _service


@dataclass(frozen=True)
class Pinned:
    """``CBCS_STATE_ROOT`` is set. Env wins every launch, so sharing is off."""

    reason: str


@dataclass(frozen=True)
class LocalSharing:
    undecided: bool


@dataclass(frozen=True)
class ShopSharing:
    link: ShopLink


SharingState = Union[Pinned, LocalSharing, ShopSharing]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ShopSharingService:
    """Owns this machine's sharing state. The only writer of the choice file. GUI thread only.

    UI-lane API:

    - ``status() -> ShopStatus`` with mode, folder, label, reachable,
      last_synced_at, pending_count, created_by_host, created_at.
    - ``discover_shop_folders() -> list[DiscoveredShop]``
    - ``default_new_folder() -> Path``
    - ``turn_on(folder, via=...) -> SharingResult`` (``ok``, ``error``, ``created``)
    - ``turn_off() -> SharingResult``
    - ``check_reconnect() -> bool``
    - ``undecided_prompt_target() -> Optional[DiscoveredShop]``
    - ``decline(folder) -> None``
    - ``recent_rows() -> list[RecentRow]``
    - ``add_listener(callback) -> unsubscribe``

    Transitions: ``LocalSharing -> ShopSharing`` on turn_on, ``ShopSharing ->
    LocalSharing`` on turn_off, ``LocalSharing(undecided) -> LocalSharing`` on
    decline. ``Pinned`` never changes. Each change that moves documents bumps
    ``generation`` and emits ``SharingChanged(documents_reloaded=True)``.
    """

    def __init__(
        self,
        machine: Machine,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._machine = machine
        self._local = LocalShopFiles(machine.local_state)
        self._monotonic = monotonic
        self._utc_now = utc_now
        self._listeners: list[Callable[[SharingChanged], None]] = []
        self._generation = 0
        self._reloading = False
        self._state = self._resolve()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def reloading(self) -> bool:
        return self._reloading

    def documents(self) -> Optional[SharedDocuments]:
        return self._state.link if isinstance(self._state, ShopSharing) else None

    def status(self) -> ShopStatus:
        """Snapshot for the chip and the Settings status line. Cheap: no shop-folder IO."""
        state = self._state
        if not isinstance(state, ShopSharing):
            mode = SharingMode.PINNED if isinstance(state, Pinned) else SharingMode.LOCAL
            return ShopStatus(mode, None, None, False, None, 0, None, None)
        fields = state.link.status_fields()
        marker = fields.marker
        return ShopStatus(
            mode=SharingMode.SHOP,
            folder=state.link.folder.path,
            label=state.link.folder.label,
            reachable=fields.reachable,
            last_synced_at=fields.last_synced_at,
            pending_count=fields.pending_count,
            created_by_host=(marker.created_by_host or None) if marker is not None else None,
            created_at=marker.created_at if marker is not None else None,
        )

    def discover_shop_folders(self) -> list[DiscoveredShop]:
        """Reachable ``Code Studio Settings`` folders under this machine's share roots, in spec order."""
        return discover_shop_folders(self._machine)

    def default_new_folder(self) -> Path:
        """The first discovered shop folder, else ``~/share/Code Studio Settings``."""
        found = self.discover_shop_folders()
        return found[0].folder if found else self._machine.home / "share" / SHOP_FOLDER_NAME

    def turn_on(self, folder: PathInput, *, via: Literal["settings", "prompt"] = "settings") -> SharingResult:
        """Join ``folder`` if it has a readable ``shop.json``, else create it. Safe to re-run after a crash.

        Join backs up the local documents to ``before_shop/``, then adds this
        machine's recents to the shop list. Create needs the parent to exist,
        copies the current documents in, and writes ``shop.json`` last. The
        choice file is the commit point. Listeners then get
        ``documents_reloaded=True``.

        Callers that also save a dialog payload call this first, then
        ``SettingsService.save_global``, with no ``load_global`` in between
        outside a listener: the save diffs against the payload's original base.
        """
        if isinstance(self._state, Pinned):
            return SharingResult(error="Shop sharing is off because CBCS_STATE_ROOT is set.")
        try:
            path = logical_path(folder)
        except ValueError as exc:
            return SharingResult(error=str(exc))
        if isinstance(self._state, ShopSharing) and self._state.link.folder.path == path:
            return SharingResult()
        joining = probe_shop_folder(path) is not None
        try:
            if joining:
                self._local.back_up_local_documents()
            current = self._current_documents()
            if not joining:
                error = create_shop_folder(path)
                if error:
                    return SharingResult(error=error)
                self._seed_new_folder(path, current)
            link = self._new_link(path)
            if joining:
                link.add_missing_recents(current.recent_paths)
            self._local.write_choice(ShopChoice(folder=path, decided_at=self._now_text(), source=via))
        except OSError as exc:
            return SharingResult(error=f"Could not use {path}: {exc.strerror or exc}")
        self._state = ShopSharing(link)
        self._documents_changed()
        return SharingResult(created=not joining)

    def turn_off(self) -> SharingResult:
        """Copy the current shop views into the local files, then switch to local. No-op unless shop mode.

        Recents become this machine's absolute paths: share entries resolved
        here plus this host's entries. Changes not yet pushed land in the local
        files, not the shop. The shop folder is not touched.
        """
        state = self._state
        if not isinstance(state, ShopSharing):
            return SharingResult()
        from app.persistence.settings_store import save_settings
        from app.project.recent_projects import replace_recent_projects
        from app.shell.python_console_history import save_python_console_history

        docs = state.link.documents_for_turn_off()
        local = self._machine.local_state
        try:
            save_settings(docs.settings, state_root=local)
            replace_recent_projects(docs.recent_paths, state_root=local)
            save_python_console_history(
                local,
                list(docs.history),
                appended=len(docs.history),
                max_entries=CONSOLE_HISTORY_MAX_ENTRIES,
            )
            self._local.write_choice(LocalChoice(declined_folder=None, decided_at=self._now_text(), source="settings"))
            self._local.reset_mirror(state.link.folder.path)
        except OSError as exc:
            return SharingResult(error=f"Could not write this computer's settings: {exc.strerror or exc}")
        self._state = LocalSharing(undecided=False)
        self._documents_changed()
        return SharingResult()

    def check_reconnect(self) -> bool:
        """Window activation. At most one probe per 10 s. True when reachability flipped or pending changes were pushed.

        Coming back online bumps ``generation`` and emits ``documents_reloaded=True``.
        """
        if not isinstance(self._state, ShopSharing):
            return False
        return self._state.link.check(throttled=True)

    def undecided_prompt_target(self) -> Optional[DiscoveredShop]:
        """The folder for the one-time prompt: only when undecided and a shop folder is found."""
        if not (isinstance(self._state, LocalSharing) and self._state.undecided):
            return None
        found = self.discover_shop_folders()
        return found[0] if found else None

    def decline(self, folder: PathInput) -> None:
        """Keep this computer's settings: write ``mode: "local"`` with ``declined_folder``. Only while undecided."""
        if not (isinstance(self._state, LocalSharing) and self._state.undecided):
            return
        self._local.write_choice(
            LocalChoice(declined_folder=logical_path(folder), decided_at=self._now_text(), source="prompt")
        )
        self._state = LocalSharing(undecided=False)
        self._emit(documents_reloaded=False)

    def recent_rows(self) -> list[RecentRow]:
        """Recent projects in stored order. In shop mode another host's entries come back with
        ``host`` set and ``available=False``; elsewhere every row is this machine's and available."""
        state = self._state
        if isinstance(state, ShopSharing):
            return state.link.recent_rows()
        from app.bootstrap.state_roots import resolve_settings_root
        from app.project.recent_projects import load_recent_projects

        root = resolve_settings_root(None).path if isinstance(state, Pinned) else self._machine.local_state
        return [RecentRow(path=path, label=Path(path).name, host=None, available=True) for path in load_recent_projects(root)]

    def add_listener(self, callback: Callable[[SharingChanged], None]) -> Callable[[], None]:
        """Returns unsubscribe. Callbacks run synchronously after the state is committed. They may
        read anything, including ``SettingsService.load_global``; they must not call turn_on,
        turn_off, or decline."""
        self._listeners.append(callback)

        def unsubscribe() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return unsubscribe

    def _resolve(self) -> SharingState:
        from app.bootstrap.state_roots import resolve_settings_root

        root = resolve_settings_root(None)
        if root.source in ("env", "local-fallback"):
            return Pinned(root.source)
        choice = self._local.read_choice()
        if isinstance(choice, ShopChoice):
            return ShopSharing(self._new_link(choice.folder))
        if isinstance(choice, LocalChoice):
            return LocalSharing(undecided=False)
        if isinstance(choice, CorruptChoice):
            _LOGGER.warning("Shop sharing choice file is unreadable, using this computer's settings: %s", choice.reason)
            return LocalSharing(undecided=False)
        hit = legacy.convert_if_found(self._machine, self._utc_now)
        if hit is None:
            return LocalSharing(undecided=True)
        self._local.write_choice(ShopChoice(folder=hit, decided_at=self._now_text(), source="converted"))
        return ShopSharing(self._new_link(hit))

    def _new_link(self, path: Path) -> ShopLink:
        return ShopLink(
            shop_folder_at(path, self._machine),
            self._local,
            self._machine,
            monotonic=self._monotonic,
            utc_now=self._utc_now,
            on_change=self._link_changed,
        )

    def _current_documents(self) -> LocalDocumentsCopy:
        if isinstance(self._state, ShopSharing):
            return self._state.link.documents_for_turn_off()
        from app.persistence.settings_store import load_settings
        from app.project.recent_projects import load_recent_projects
        from app.shell.python_console_history import load_python_console_history

        local = self._machine.local_state
        return LocalDocumentsCopy(
            settings=load_settings(state_root=local),
            recent_paths=tuple(load_recent_projects(state_root=local)),
            history=tuple(
                load_python_console_history(local, max_entries=CONSOLE_HISTORY_MAX_ENTRIES)
            ),
        )

    def _seed_new_folder(self, path: Path, current: LocalDocumentsCopy) -> None:
        """Copy the documents in, then ``shop.json`` last, so the folder is discoverable only when complete.
        Files already in the folder are kept, so an old folder is adopted rather than overwritten."""
        hostname = self._machine.hostname
        folder = shop_folder_at(path, self._machine)
        refs = tuple(classify_project(root, folder=folder, hostname=hostname) for root in current.recent_paths)
        recents = RecentsAddMissing(op_id=uuid.uuid4().hex, refs=refs).apply(ShopDoc.RECENTS.empty())
        write_shop_doc_if_absent(path, ShopDoc.SETTINGS.value, current.settings, hostname=hostname)
        write_shop_doc_if_absent(path, ShopDoc.RECENTS.value, recents, hostname=hostname)
        write_shop_doc_if_absent(path, ShopDoc.HISTORY.value, {"history": list(current.history)}, hostname=hostname)
        write_shop_doc_if_absent(path, MARKER_FILENAME, marker_payload(hostname, self._utc_now()), hostname=hostname)

    def _link_changed(self, documents_reloaded: bool) -> None:
        if documents_reloaded:
            self._documents_changed()
        else:
            self._emit(documents_reloaded=False)

    def _documents_changed(self) -> None:
        self._generation += 1
        self._emit(documents_reloaded=True)

    def _emit(self, *, documents_reloaded: bool) -> None:
        event = SharingChanged(status=self.status(), documents_reloaded=documents_reloaded)
        self._reloading = documents_reloaded
        try:
            for callback in list(self._listeners):
                callback(event)
        finally:
            self._reloading = False

    def _now_text(self) -> str:
        return self._utc_now().isoformat()
