"""Atomic text-file write helpers for editor-managed files."""

from __future__ import annotations

import os
from pathlib import Path
import uuid

from app.bootstrap.paths import PathInput, ensure_directory


_SNIFF_LIMIT = 1024 * 1024
_NEWLINE_STYLES = ("\n", "\r\n", "\r")


def detect_newline_style(raw: bytes) -> str:
    """Return the dominant line ending of ``raw``: ``\\n``, ``\\r\\n`` or ``\\r``.

    A mixed file reports its most frequent style; a tie, or no line break at
    all, reports ``\\n``. Mixed files are therefore normalised to the dominant
    style on save (documented limitation: per-line endings are not kept).
    """
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    cr = raw.count(b"\r") - crlf
    best = max(lf, crlf, cr)
    if best == 0 or lf == best:
        return "\n"
    return "\r\n" if crlf == best else "\r"


def _existing_format(path: Path) -> tuple[str, int | None]:
    """Return ``(newline_style, mode_bits)`` of the file at ``path``, if any."""
    try:
        mode = os.stat(path).st_mode & 0o7777
        with open(path, "rb") as handle:
            return detect_newline_style(handle.read(_SNIFF_LIMIT)), mode
    except OSError:
        return "\n", None


def atomic_write_text(
    path: PathInput,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> Path:
    """Write text to ``path`` via temp file, fsync and replace.

    ``content`` uses ``\\n`` line breaks. ``newline`` is the line ending to
    write; when ``None`` it is detected from the existing file (``\\n`` for a
    new file), so a CRLF or CR file keeps its style. Permission bits of an
    existing file are kept; a new file gets ``0666`` minus the umask. A UTF-8
    BOM survives because the BOM is part of ``content`` when read with
    ``utf-8``.
    """
    if newline is not None and newline not in _NEWLINE_STYLES:
        raise ValueError(f"Unsupported newline style: {newline!r}")
    resolved_path = Path(path).expanduser().resolve()
    parent_dir = ensure_directory(resolved_path.parent)
    existing_style, existing_mode = _existing_format(resolved_path)
    style = existing_style if newline is None else newline
    text = content
    if style != "\n":
        text = content.replace("\r\n", "\n").replace("\n", style)

    temp_path, fd = _create_temp_file(parent_dir, resolved_path.name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            if existing_mode is not None and hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), existing_mode)
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


def _create_temp_file(parent_dir: Path, name: str) -> tuple[Path, int]:
    """Create a sibling temp file with mode ``0666`` minus umask (new-file default)."""
    for _attempt in range(100):
        candidate = parent_dir / f"{name}.{uuid.uuid4().hex[:12]}.tmp"
        try:
            fd = os.open(str(candidate), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:
            continue
        return candidate, fd
    raise OSError(f"Could not create a temporary file next to {parent_dir / name}")


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


def atomic_write_batch(writes: dict[str, str], *, encoding: str = "utf-8") -> list[str]:
    """Apply multiple atomic writes with rollback on the first failure."""
    originals: dict[str, str] = {}
    updated_paths: list[str] = []
    try:
        for path, content in writes.items():
            target = Path(path).expanduser().resolve()
            originals[path] = target.read_text(encoding=encoding)
            atomic_write_text(target, content, encoding=encoding)
            updated_paths.append(str(target))
    except OSError:
        for path, payload in originals.items():
            atomic_write_text(path, payload, encoding=encoding)
        raise
    return updated_paths
