"""Trash backends for user-facing soft-delete operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import shutil
from urllib.parse import quote

from app.bootstrap.paths import PathInput, ensure_directory, global_trash_files_dir, global_trash_info_dir


class _TrashBackendUnavailable(RuntimeError):
    """Raised when a backend is unavailable and next backend should be tried."""


@dataclass(frozen=True)
class TrashMoveResult:
    """Result payload for trash operations."""

    destination_path: str | None
    backend: str


def move_path_to_trash(
    target_path: str | Path,
    *,
    state_root: PathInput | None = None,
) -> TrashMoveResult:
    """Move a file/folder to trash using prioritized backend chain."""
    target = Path(target_path).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")

    errors: list[str] = []
    for backend in (
        _move_with_send2trash,
        _move_with_freedesktop_trash,
        _move_with_app_fallback_trash,
    ):
        try:
            return backend(target, state_root=state_root)
        except _TrashBackendUnavailable as exc:
            errors.append(str(exc))
            continue
        except OSError as exc:
            errors.append(str(exc))
            continue

    detail = "; ".join(error for error in errors if error).strip()
    message = f"Could not move '{target}' to trash."
    if detail:
        message = f"{message} {detail}"
    raise OSError(message)


def _move_with_send2trash(target: Path, *, state_root: PathInput | None = None) -> TrashMoveResult:
    _ = state_root
    try:
        from send2trash import send2trash  # type: ignore[import-not-found]
    except Exception as exc:
        raise _TrashBackendUnavailable("system send2trash backend unavailable") from exc

    try:
        send2trash(str(target))
    except Exception as exc:
        raise OSError(f"system send2trash backend failed: {exc}") from exc

    return TrashMoveResult(destination_path=None, backend="system_send2trash")


def _move_with_freedesktop_trash(target: Path, *, state_root: PathInput | None = None) -> TrashMoveResult:
    _ = state_root
    data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if data_home:
        candidate = Path(data_home).expanduser()
        data_home_path = candidate.resolve() if candidate.is_absolute() else (Path.home() / candidate).resolve()
    else:
        data_home_path = (Path.home() / ".local" / "share").resolve()

    trash_root = data_home_path / "Trash"
    files_dir = trash_root / "files"
    info_dir = trash_root / "info"
    return _move_with_trash_layout(target, files_dir=files_dir, info_dir=info_dir, backend="system_freedesktop")


def _move_with_app_fallback_trash(target: Path, *, state_root: PathInput | None = None) -> TrashMoveResult:
    files_dir = global_trash_files_dir(state_root)
    info_dir = global_trash_info_dir(state_root)
    return _move_with_trash_layout(target, files_dir=files_dir, info_dir=info_dir, backend="app_fallback")


def _move_with_trash_layout(
    target: Path,
    *,
    files_dir: Path,
    info_dir: Path,
    backend: str,
) -> TrashMoveResult:
    ensure_directory(files_dir)
    ensure_directory(info_dir)

    entry_name = _next_entry_name(target.name, files_dir=files_dir, info_dir=info_dir)
    destination = files_dir / entry_name
    info_path = info_dir / f"{entry_name}.trashinfo"

    deletion_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    encoded_source = quote(str(target), safe="/")
    info_payload = (
        "[Trash Info]\n"
        f"Path={encoded_source}\n"
        f"DeletionDate={deletion_time}\n"
    )
    info_path.write_text(info_payload, encoding="utf-8")

    try:
        shutil.move(str(target), str(destination))
    except Exception as exc:
        info_path.unlink(missing_ok=True)
        raise OSError(str(exc)) from exc

    return TrashMoveResult(destination_path=str(destination), backend=backend)


def _next_entry_name(source_name: str, *, files_dir: Path, info_dir: Path) -> str:
    candidate = source_name
    for suffix in range(1, 10000):
        candidate_path = files_dir / candidate
        candidate_info = info_dir / f"{candidate}.trashinfo"
        if not candidate_path.exists() and not candidate_info.exists():
            return candidate
        candidate = f"{source_name}.{suffix}"
    raise OSError(f"Unable to allocate trash entry name for {source_name}")
