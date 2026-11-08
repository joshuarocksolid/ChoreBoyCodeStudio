"""Choose the directory that holds this machine's settings JSON files.

Local state is the product dest, or an explicit argument. It holds logs,
caches, history, plugins, crash reports, trash, and SQLite. ``CBCS_STATE_ROOT``
never moves it.

``CBCS_STATE_ROOT`` (advanced/dev) moves the settings JSON only. Shop sharing
never moves this root: ``app.features.shop_sharing`` routes the shared
documents when they are opened, so migration and logging never touch the share.
The final symlink hop is not resolved.
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

_cached_choice: Optional["SettingsRootChoice"] = None
_cached_key: Optional[tuple[object, ...]] = None


@dataclass(frozen=True)
class SettingsRootChoice:
    """Settings directory of this machine for this process. Never the shop folder.

    ``source`` is ``explicit``, ``env``, ``local``, or ``local-fallback``.
    ``local-fallback`` means ``CBCS_STATE_ROOT`` could not be written, so
    settings stay on the local root for this session.
    """

    path: Path
    source: str
    requested_path: Optional[Path]
    error: str

    @property
    def fell_back_to_local(self) -> bool:
        return self.source == "local-fallback"


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
    choice = _resolve_env_or_local()
    _cached_choice = choice
    _cached_key = key
    return choice


def _resolve_env_or_local() -> SettingsRootChoice:
    from app.bootstrap.paths import _state_root_from_env

    local = resolve_global_state_root(None)
    requested = _state_root_from_env()
    if requested is None:
        return SettingsRootChoice(path=local, source="local", requested_path=None, error="")
    if normalize_state_root_identity(requested) == local:
        return SettingsRootChoice(path=local, source="env", requested_path=requested, error="")
    ok, error = settings_dir_writable(requested)
    if ok:
        return SettingsRootChoice(
            path=normalize_state_root_identity(requested), source="env", requested_path=requested, error=""
        )
    return SettingsRootChoice(path=local, source="local-fallback", requested_path=requested, error=error)


def settings_dir_writable(path: Path) -> tuple[bool, str]:
    """Return whether JSON can be written. This does not lock or open SQLite.

    Only the last folder is created. A missing parent usually means the folder
    is on a drive that is not connected, and creating it would split settings.
    """
    probe = path / f"cbcs_settings_write_probe_{uuid.uuid4().hex}.tmp"
    try:
        path.mkdir(exist_ok=True)
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


def _resolution_key() -> tuple[object, ...]:
    return (
        os.environ.get(constants.CBCS_STATE_ROOT_ENV_NAME, ""),
        str(Path.home()),
        str(path_api.DEFAULT_PRODUCT_STATE_LAYOUT.state_root),
    )
