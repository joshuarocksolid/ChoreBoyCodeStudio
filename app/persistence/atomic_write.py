"""Atomic text-file write helpers for editor-managed files."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from app.bootstrap.paths import PathInput, ensure_directory


def atomic_write_text(path: PathInput, content: str, *, encoding: str = "utf-8") -> Path:
    """Write text to ``path`` via temp file + replace."""
    resolved_path = Path(path).expanduser().resolve()
    parent_dir = ensure_directory(resolved_path.parent)
    fd, temp_name = tempfile.mkstemp(
        dir=str(parent_dir),
        prefix=f"{resolved_path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(resolved_path))
        _fsync_directory(parent_dir)
        return resolved_path
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _fsync_directory(directory: Path) -> None:
    """Best-effort fsync for the containing directory after replace."""
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        return
    finally:
        os.close(fd)
