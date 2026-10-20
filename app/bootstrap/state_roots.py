"""Choose the local state root and the optional shared settings root.

Local state is the product dest, or an explicit argument. It holds logs,
caches, history, plugins, crash reports, trash, and SQLite. The shop pointer
and ``CBCS_STATE_ROOT`` never move it.

Shared settings are opt-in and hold only JSON preferences. Pointer files are
accepted at ``/home/default/share/Chore_Boy/CBCS/cbcs_state_root`` and at that
same relative path under one ``~/share/<child>/`` directory, for example
``~/share/net1/Chore_Boy/CBCS/cbcs_state_root``. A client machine sees the
shop share under a child named for the server. The lab measured ``~/share``
on the home filesystem, with no ``net*`` child. Real shops share that folder
across machines, so SQLite stays off it.

The final symlink hop is not resolved. A legacy ``~/choreboy_code_studio_state``
symlink whose target is inside ``~/share`` is a shared settings root, not the
local state root.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.bootstrap import paths as path_api
from app.bootstrap.paths import PathInput, normalize_state_root_identity, resolve_global_state_root
from app.core import constants

_SHARE_POINTER_TAIL = (
    "Chore_Boy",
    "CBCS",
    constants.CBCS_STATE_ROOT_POINTER_FILENAME,
)

_cached_choice: Optional["SettingsRootChoice"] = None
_cached_key: Optional[tuple[object, ...]] = None


@dataclass(frozen=True)
class SettingsRootChoice:
    """Active settings directory for this process.

    ``source`` is ``explicit``, ``env``, ``pointer``, ``legacy-symlink``,
    ``local``, or ``local-fallback``. ``local-fallback`` means a shared root
    was requested and could not be written, so settings stay on the local root
    for this session.
    """

    path: Path
    source: str
    requested_path: Optional[Path]
    error: str

    @property
    def fell_back_to_local(self) -> bool:
        return self.source == "local-fallback"


def shop_pointer_candidates(home: Path) -> tuple[Path, ...]:
    """Return pointer files in the order the resolver reads them."""
    ordered: list[Path] = []

    def add(path: Path) -> None:
        if path not in ordered:
            ordered.append(path)

    add(path_api.DEFAULT_PRODUCT_STATE_LAYOUT.shop_pointer_path)
    share = home / "share"
    add(share.joinpath(*_SHARE_POINTER_TAIL))
    try:
        children = [entry for entry in share.iterdir() if entry.is_dir() and not entry.name.startswith(".")]
    except OSError:
        children = []
    for child in sorted(children, key=lambda entry: entry.name):
        add(child.joinpath(*_SHARE_POINTER_TAIL))
    return tuple(ordered)


def resolve_settings_root(state_root: Optional[PathInput] = None) -> SettingsRootChoice:
    """Return the settings directory. Explicit argument wins and is not probed."""
    if state_root is not None:
        return SettingsRootChoice(
            path=normalize_state_root_identity(state_root),
            source="explicit",
            requested_path=None,
            error="",
        )

    key = _resolution_key()
    global _cached_choice, _cached_key
    if _cached_choice is not None and _cached_key == key:
        return _cached_choice
    choice = _resolve_shared_or_local()
    _cached_choice = choice
    _cached_key = key
    return choice


def _resolve_shared_or_local() -> SettingsRootChoice:
    local = resolve_global_state_root(None)
    requested = _requested_shared_root()
    if requested is None:
        return SettingsRootChoice(path=local, source="local", requested_path=None, error="")
    path, source = requested
    if normalize_state_root_identity(path) == local:
        return SettingsRootChoice(path=local, source=source, requested_path=path, error="")
    ok, error = settings_dir_writable(path)
    if ok:
        return SettingsRootChoice(path=normalize_state_root_identity(path), source=source, requested_path=path, error="")
    return SettingsRootChoice(path=local, source="local-fallback", requested_path=path, error=error)


def settings_dir_writable(path: Path) -> tuple[bool, str]:
    """Return whether JSON can be written. This does not lock or open SQLite."""
    probe = path / f"cbcs_settings_write_probe_{uuid.uuid4().hex}.tmp"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        return True, ""
    except OSError as exc:
        return False, os_error_text(exc)
    finally:
        try:
            if probe.is_file() or probe.is_symlink():
                probe.unlink()
        except OSError:
            pass


def os_error_text(exc: OSError) -> str:
    reason = exc.strerror or exc.__class__.__name__
    if exc.errno is None:
        return reason
    return f"{reason} (errno {exc.errno})"


def _requested_shared_root() -> Optional[tuple[Path, str]]:
    from app.bootstrap.paths import _state_root_from_env, _state_root_from_pointer_file

    env_root = _state_root_from_env()
    if env_root is not None:
        return env_root, "env"
    home = Path.home()
    for candidate in shop_pointer_candidates(home):
        pointed = _state_root_from_pointer_file(candidate)
        if pointed is not None:
            return pointed, "pointer"
    legacy = _legacy_share_symlink(home)
    if legacy is not None:
        return legacy, "legacy-symlink"
    return None


def _legacy_share_symlink(home: Path) -> Optional[Path]:
    link = home / constants.GLOBAL_STATE_DIRNAME
    if not link.is_symlink():
        return None
    try:
        raw_target = os.readlink(link)
    except OSError:
        return None
    target = Path(raw_target)
    if not target.is_absolute():
        target = link.parent / target
    target_abs = Path(os.path.abspath(str(target)))
    share_abs = Path(os.path.abspath(str(home / "share")))
    if target_abs == share_abs or share_abs in target_abs.parents:
        return normalize_state_root_identity(link)
    return None


def _resolution_key() -> tuple[object, ...]:
    home = Path.home()
    link = home / constants.GLOBAL_STATE_DIRNAME
    try:
        link_target = os.readlink(link) if link.is_symlink() else ""
    except OSError:
        link_target = "unreadable"
    pointer_bits = []
    for candidate in shop_pointer_candidates(home):
        try:
            text = candidate.read_text(encoding="utf-8") if candidate.is_file() else ""
        except OSError:
            text = "unreadable"
        pointer_bits.append((str(candidate), text))
    return (
        os.environ.get(constants.CBCS_STATE_ROOT_ENV_NAME, ""),
        str(home),
        str(path_api.DEFAULT_PRODUCT_STATE_LAYOUT.state_root),
        str(path_api.DEFAULT_PRODUCT_STATE_LAYOUT.shop_pointer_path),
        link_target,
        tuple(pointer_bits),
    )
