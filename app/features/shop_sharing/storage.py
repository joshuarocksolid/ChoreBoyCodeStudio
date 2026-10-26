"""Filesystem boundary for shop sharing.

Shop-folder rules, enforced here and nowhere else:

- Paths are logical (``os.path.abspath``). Never ``Path.resolve()``.
- Nothing creates a parent of the shop folder. A write opens its temp file
  inside the existing folder, so a missing folder fails with
  ``FileNotFoundError`` and is never recreated.
- Temp names are visible: ``<name>.<hostname>.<uuid8>.tmp``.
- A write is exclusive-create temp, write, fsync, close, ``os.replace``. The
  temp is unlinked on any failure.

``save_json_object`` and ``atomic_write_text`` resolve and create parents, so
they are only used for this machine's local files.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple, Union

from app.bootstrap.paths import PathInput
from app.core import constants
from app.features.shop_sharing.model import (
    MARKER_FILENAME,
    SHOP_FOLDER_NAME,
    Absent,
    ChoiceRead,
    CorruptChoice,
    DiscoveredShop,
    DocRead,
    LocalChoice,
    Machine,
    NoChoice,
    Present,
    ShopChoice,
    ShopDoc,
    ShopFolder,
    ShopMarker,
    ShopOp,
    Unreadable,
    op_from_json,
)
from app.persistence.atomic_write import atomic_write_text

_LOGGER = logging.getLogger(__name__)

CHOICE_FILENAME = "shop_sharing.json"
MIRROR_DIRNAME = "shop_mirror"
BACKUP_DIRNAME = "before_shop"
_PENDING_FILENAME = "pending.json"
_SYNC_FILENAME = "sync.json"
_LOCAL_DOCUMENT_FILENAMES = (
    constants.GLOBAL_SETTINGS_FILENAME,
    constants.GLOBAL_RECENT_PROJECTS_FILENAME,
    constants.GLOBAL_PYTHON_CONSOLE_HISTORY_FILENAME,
)


def logical_path(raw: PathInput) -> Path:
    """``expanduser`` plus ``os.path.abspath``. Raises ValueError if the input is not absolute."""
    candidate = os.path.expanduser(str(raw))
    if not os.path.isabs(candidate):
        raise ValueError(f"Not an absolute path: {raw}")
    return Path(os.path.abspath(candidate))


def shop_folder_at(path: Path, machine: Machine) -> ShopFolder:
    parent = path.parent
    top_shares = {_logical(machine.home / "share"), _logical(machine.default_home / "share")}
    if parent not in top_shares and parent.parent in top_shares:
        label = parent.name
    else:
        label = machine.hostname
    logical_parent = logical_path(parent)
    real_parent = os.path.realpath(str(parent))
    # A mount symlink and the directory it names are the same share root.
    share_root = (
        parent
        if any(
            logical_parent == logical_path(root) or real_parent == os.path.realpath(str(root))
            for root in share_roots(machine)
        )
        else None
    )
    return ShopFolder(path=path, share_root=share_root, label=label)


def share_roots(machine: Machine) -> Tuple[Path, ...]:
    """``~/share`` then its visible child directories by name; then ``/home/default/share``
    and its children when HOME differs. Deduped by logical path."""
    tops = [machine.home / "share"]
    if _logical(machine.home) != _logical(machine.default_home):
        tops.append(machine.default_home / "share")
    ordered: list[Path] = []
    for top in tops:
        for root in (top, *visible_child_dirs(top)):
            logical = _logical(root)
            if logical not in ordered:
                ordered.append(logical)
    return tuple(ordered)


def discover_shop_folders(machine: Machine) -> list[DiscoveredShop]:
    found: list[DiscoveredShop] = []
    for root in share_roots(machine):
        folder = root / SHOP_FOLDER_NAME
        marker = probe_shop_folder(folder)
        if marker is not None:
            found.append(DiscoveredShop(folder=folder, label=shop_folder_at(folder, machine).label, marker=marker))
    return found


def probe_shop_folder(folder: Path) -> Optional[ShopMarker]:
    """Reachable means the folder is a directory and ``shop.json`` can be read.
    Unparseable JSON is still reachable, as ``ShopMarker("", None)``. Creates nothing."""
    try:
        if not folder.is_dir():
            return None
        raw = (folder / MARKER_FILENAME).read_bytes()
    except OSError:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ShopMarker("", None)
    if not isinstance(payload, dict):
        return ShopMarker("", None)
    host = payload.get("created_by_host")
    return ShopMarker(
        created_by_host=host if isinstance(host, str) else "",
        created_at=parse_utc(payload.get("created_at")),
    )


def marker_payload(hostname: str, now: datetime) -> dict[str, Any]:
    return {"schema_version": 1, "created_by_host": hostname, "created_at": now.isoformat()}


def read_shop_doc(folder: Path, doc: ShopDoc) -> DocRead:
    return read_shop_file(folder, doc.value)


def read_shop_file(folder: Path, name: str) -> DocRead:
    """A missing file is Absent only while the folder is a readable directory. An empty file is Unreadable."""
    try:
        raw = (folder / name).read_bytes()
    except FileNotFoundError:
        try:
            folder_ok = folder.is_dir()
        except OSError:
            folder_ok = False
        return Absent() if folder_ok else Unreadable("shop folder is not available")
    except OSError as exc:
        return Unreadable(str(exc))
    if not raw.strip():
        return Unreadable("file is empty")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return Unreadable(f"not JSON: {exc}")
    if not isinstance(payload, dict):
        return Unreadable("not a JSON object")
    return Present(payload)


def write_shop_doc(folder: Path, doc: ShopDoc, payload: Mapping[str, Any], *, hostname: str) -> None:
    """Atomic replace inside the existing folder. Raises OSError, FileNotFoundError when the folder is gone."""
    _replace_in_folder(folder, doc.value, payload, hostname=hostname)


def write_shop_doc_if_absent(folder: Path, name: str, payload: Mapping[str, Any], *, hostname: str) -> bool:
    """Same write, skipped when the target exists. Two machines racing write equivalent content."""
    if os.path.lexists(str(folder / name)):
        return False
    _replace_in_folder(folder, name, payload, hostname=hostname)
    return True


def create_shop_folder(folder: Path) -> str:
    """Make the leaf folder only. Returns an error message, or "" on success."""
    parent = folder.parent
    if not parent.is_dir():
        return f"The folder {parent} does not exist on this computer. Connect the shop share or choose another folder."
    try:
        os.mkdir(str(folder))
    except FileExistsError:
        if not folder.is_dir():
            return f"{folder} exists and is not a folder."
    except OSError as exc:
        return f"Could not create {folder}: {exc.strerror or exc}"
    return ""


def parse_utc(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class LocalShopFiles:
    """This machine's sharing files under local state. Ordinary local writes.

    ``shop_sharing.json`` is the choice file. ``shop_mirror/`` holds the last
    synced copy of each shared document, ``pending.json`` (the journal of ops
    not yet pushed), and ``sync.json`` (``folder`` and ``last_synced_at``).
    ``before_shop/`` is the backup of the local documents written on join.

    The whole ``shop_mirror/`` directory belongs to ``sync.json["folder"]``.
    ``reset_mirror`` is the only way that ownership changes.
    """

    def __init__(self, local_state: Path) -> None:
        self._local_state = local_state
        self._mirror = local_state / MIRROR_DIRNAME

    @property
    def choice_path(self) -> Path:
        return self._local_state / CHOICE_FILENAME

    def read_choice(self) -> ChoiceRead:
        try:
            raw = self.choice_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return NoChoice()
        except OSError as exc:
            return CorruptChoice(str(exc))
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            return CorruptChoice(f"not JSON: {exc}")
        if not isinstance(payload, dict):
            return CorruptChoice("not a JSON object")
        decided_at = payload.get("decided_at") if isinstance(payload.get("decided_at"), str) else ""
        source = payload.get("source")
        if source not in ("settings", "prompt", "converted"):
            source = "settings"
        mode = payload.get("mode")
        if mode == "shop":
            folder = payload.get("folder")
            if not isinstance(folder, str) or not os.path.isabs(folder):
                return CorruptChoice("shop mode without an absolute folder")
            return ShopChoice(folder=logical_path(folder), decided_at=decided_at, source=source)
        if mode == "local":
            declined = payload.get("declined_folder")
            declined_path = logical_path(declined) if isinstance(declined, str) and os.path.isabs(declined) else None
            return LocalChoice(declined_folder=declined_path, decided_at=decided_at, source=source)
        return CorruptChoice(f"unknown mode {mode!r}")

    def write_choice(self, choice: Union[ShopChoice, LocalChoice]) -> None:
        if isinstance(choice, ShopChoice):
            payload = {"mode": "shop", "folder": str(choice.folder), "declined_folder": None}
        else:
            declined = str(choice.declined_folder) if choice.declined_folder is not None else None
            payload = {"mode": "local", "folder": None, "declined_folder": declined}
        _write_local_json(
            self.choice_path,
            {"schema_version": 1, **payload, "decided_at": choice.decided_at, "source": choice.source},
        )

    def mirror_folder(self) -> Optional[Path]:
        folder = self._read_sync().get("folder")
        return Path(folder) if isinstance(folder, str) and folder else None

    def reset_mirror(self, folder: Path) -> None:
        for name in (*(doc.value for doc in ShopDoc), _PENDING_FILENAME):
            try:
                (self._mirror / name).unlink()
            except FileNotFoundError:
                pass
        _write_local_json(self._mirror / _SYNC_FILENAME, {"folder": str(folder), "last_synced_at": None})

    def read_mirror(self, doc: ShopDoc) -> dict[str, Any]:
        payload = _read_local_json(self._mirror / doc.value)
        return payload if payload is not None else doc.empty()

    def write_mirror(self, doc: ShopDoc, payload: Mapping[str, Any]) -> None:
        _write_local_json(self._mirror / doc.value, payload)

    def last_synced_at(self) -> Optional[datetime]:
        return parse_utc(self._read_sync().get("last_synced_at"))

    def mark_synced(self, when: datetime) -> None:
        sync = self._read_sync()
        sync["last_synced_at"] = when.isoformat()
        _write_local_json(self._mirror / _SYNC_FILENAME, sync)

    def read_journal(self) -> list[ShopOp]:
        payload = _read_local_json(self._mirror / _PENDING_FILENAME) or {}
        raw_ops = payload.get("ops")
        ops: list[ShopOp] = []
        for raw in raw_ops if isinstance(raw_ops, list) else []:
            op = op_from_json(raw)
            if op is None:
                _LOGGER.warning("Dropping unreadable pending shop op: %r", raw)
                continue
            ops.append(op)
        return ops

    def append_journal(self, op: ShopOp) -> None:
        """Durable before any share IO: this is the commit point of every shared write."""
        self._write_journal([*self.read_journal(), op])

    def drop_journal_ops(self, op_ids: "set[str]") -> None:
        if op_ids:
            self._write_journal([op for op in self.read_journal() if op.op_id not in op_ids])

    def back_up_local_documents(self) -> None:
        """Copy the local documents that exist into ``before_shop/``, replacing the previous backup."""
        backup = self._local_state / BACKUP_DIRNAME
        backup.mkdir(parents=True, exist_ok=True)
        for name in _LOCAL_DOCUMENT_FILENAMES:
            source = self._local_state / name
            if source.is_file():
                shutil.copy2(str(source), str(backup / name))

    def _write_journal(self, ops: list[ShopOp]) -> None:
        _write_local_json(self._mirror / _PENDING_FILENAME, {"schema_version": 1, "ops": [op.to_json() for op in ops]})

    def _read_sync(self) -> dict[str, Any]:
        return _read_local_json(self._mirror / _SYNC_FILENAME) or {}


def _replace_in_folder(folder: Path, name: str, payload: Mapping[str, Any], *, hostname: str) -> None:
    folder_text = os.path.abspath(str(folder))
    temp = os.path.join(folder_text, f"{name}.{hostname}.{uuid.uuid4().hex[:8]}.tmp")
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, os.path.join(folder_text, name))
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _read_local_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_local_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _logical(path: Path) -> Path:
    return Path(os.path.abspath(str(path)))


def visible_child_dirs(top: Path) -> list[Path]:
    try:
        children = [entry for entry in top.iterdir() if not entry.name.startswith(".") and entry.is_dir()]
    except OSError:
        return []
    return sorted(children, key=lambda entry: entry.name)
