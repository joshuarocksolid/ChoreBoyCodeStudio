"""Per-machine connection secrets (CONTRACTS.md section 19.3).

The file lives under the CBCS state root, never inside the project. The
directory is mode 0700 and the file is mode 0600. chmod runs after create
because umask would otherwise widen the mode passed to open.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.logic.codec import JsonObject, JsonValue, parse_json, write_json

_SHARED_BITS = 0o077


@dataclass(frozen=True)
class MachineEntry:
    password: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None


@dataclass(frozen=True)
class MachineFile:
    """``shared`` is set when the file mode allows group or other access. The data is still returned."""

    entries: Tuple[Tuple[str, MachineEntry], ...] = ()
    shared: bool = False
    readable: bool = True


def machine_path(state_root: str, slug: str) -> str:
    """``{state_root}/connections/{slug}.json``. The caller supplies the slug."""

    return os.path.join(state_root, "connections", slug + ".json")


def load_machine(path: str) -> MachineFile:
    """Read the machine file. A missing file is empty. A loose mode is flagged, not refused."""

    if not os.path.isfile(path):
        return MachineFile()
    shared = _shared(path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError):
        return MachineFile(shared=shared, readable=False)
    parsed = parse_json(text)
    if parsed.error is not None or not isinstance(parsed.value, JsonObject):
        return MachineFile(shared=shared, readable=False)
    if parsed.value.get("version") != 1:
        return MachineFile(shared=shared, readable=False)
    raw = parsed.value.get("connections")
    if raw is None:
        return MachineFile(shared=shared)
    if not isinstance(raw, JsonObject):
        return MachineFile(shared=shared, readable=False)
    entries = []
    for name, value in raw.pairs:
        entry = _entry(value)
        if entry is None:
            return MachineFile(shared=shared, readable=False)
        entries.append((name, entry))
    return MachineFile(tuple(entries), shared=shared)


def save_machine(
    path: str,
    entries: Tuple[Tuple[str, MachineEntry], ...],
    *,
    project_root: str,
) -> None:
    """Write the machine file outside the project. The temp file is created mode 0600, then replaced."""

    _refuse_inside_project(project_root, path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    os.chmod(directory, 0o700)
    text = _text(entries)
    tmp = os.path.join(directory, "cbcs_machine_%s_%s.tmp" % (os.getpid(), _token()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        payload = text.encode("utf-8")
        os.write(fd, payload)
        os.fsync(fd)
    except Exception:
        os.close(fd)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    os.close(fd)
    os.chmod(tmp, 0o600)
    try:
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    os.chmod(path, 0o600)
    os.chmod(directory, 0o700)


def rename_entry(path: str, old: str, new: str, *, project_root: str) -> None:
    """Move one key. A missing file or a missing old key is a no-op."""

    if old == new:
        return
    current = load_machine(path)
    if not current.readable:
        return
    found = None
    rest = []
    for name, entry in current.entries:
        if name == old and found is None:
            found = entry
            continue
        if name == new:
            continue
        rest.append((name, entry))
    if found is None:
        return
    rest.append((new, found))
    save_machine(path, tuple(rest), project_root=project_root)


def _entry(value: JsonValue) -> Optional[MachineEntry]:
    if not isinstance(value, JsonObject):
        return None
    password = value.get("password")
    host = value.get("host")
    port = value.get("port")
    if password is not None and not isinstance(password, str):
        return None
    if host is not None and not isinstance(host, str):
        return None
    if port is not None and (isinstance(port, bool) or not isinstance(port, int)):
        return None
    return MachineEntry(
        password if isinstance(password, str) and password else None,
        host if isinstance(host, str) and host else None,
        port if isinstance(port, int) and not isinstance(port, bool) else None,
    )


def _text(entries: Tuple[Tuple[str, MachineEntry], ...]) -> str:
    rows = []
    for name, entry in entries:
        pairs = []
        if entry.password is not None:
            pairs.append(("password", entry.password))
        if entry.host:
            pairs.append(("host", entry.host))
        if entry.port is not None:
            pairs.append(("port", entry.port))
        rows.append((name, JsonObject(tuple(pairs))))
    payload = JsonObject((("version", 1), ("connections", JsonObject(tuple(rows)))))
    return write_json(payload) + "\n"


def _shared(path: str) -> bool:
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return bool(stat.S_IMODE(mode) & _SHARED_BITS)


def _refuse_inside_project(project_root: str, path: str) -> None:
    root = os.path.abspath(project_root)
    target = os.path.abspath(path)
    try:
        inside = os.path.commonpath((root, target)) == root
    except ValueError:
        inside = False
    if inside:
        raise ValueError("The machine file must stay outside the project.")


def _token() -> str:
    return os.urandom(8).hex()
