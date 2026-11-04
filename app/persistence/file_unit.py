"""Write several project files as one unit, or leave every one of them alone.

The rules match ``atomic_write_text``: the symlink target is what gets
replaced, an existing file keeps its mode bits, and the temp name is unique
in that folder. Line endings follow the file already on disk.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

from app.persistence.atomic_write import detect_newline_style


Replace = Callable[[str, str], None]


def same_text(left: str, right: str) -> bool:
    """True when the two texts match once line endings are ``\\n``."""

    return _norm(left) == _norm(right)


def bytes_for(path: str, text: str) -> bytes:
    """``text`` uses ``\\n``. The result uses the ending already in ``path``."""

    raw = _read(path)
    style = detect_newline_style(raw) if raw else "\n"
    body = _norm(text)
    if style != "\n":
        body = body.replace("\n", style)
    return body.encode("utf-8")


def same_bytes(found: Optional[bytes], expected: Optional[bytes]) -> bool:
    if found is None and expected is None:
        return True
    if found is None or expected is None:
        return False
    return same_text(_decode(found), _decode(expected))


def commit_files(
    items: Sequence[Tuple[str, bytes, Optional[bytes]]],
    replace: Replace = os.replace,
) -> str:
    """Write every ``(path, new, old)``. Empty on success, a sentence on failure."""

    if not items:
        return ""
    staged: list[tuple[str, str, Optional[bytes]]] = []
    done: list[tuple[str, Optional[bytes]]] = []
    try:
        for path, data, old in items:
            resolved = str(Path(path).expanduser().resolve())
            parent = os.path.dirname(resolved) or "."
            if os.path.lexists(resolved) and not os.access(resolved, os.W_OK):
                _cleanup(staged)
                return "Couldn't save %s." % os.path.basename(path)
            os.makedirs(parent, exist_ok=True)
            if not os.access(parent, os.W_OK):
                _cleanup(staged)
                return "Couldn't save %s." % os.path.basename(path)
            mode = _mode(resolved)
            fd, temp = tempfile.mkstemp(prefix=".cbcs-", dir=parent)
            try:
                os.write(fd, data)
                if mode is not None and hasattr(os, "fchmod"):
                    os.fchmod(fd, mode)
                os.fsync(fd)
            finally:
                os.close(fd)
            staged.append((resolved, temp, old))
        for resolved, temp, old in staged:
            replace(temp, resolved)
            done.append((resolved, old))
        _fsync_dir(os.path.dirname(staged[-1][0]) or ".")
    except OSError:
        _cleanup(staged)
        problems = []
        for resolved, old in reversed(done):
            sentence = restore_file(resolved, old, replace)
            if sentence:
                problems.append(sentence)
        if problems:
            return problems[0]
        names = " and ".join(os.path.basename(path) for path, _data, _old in items)
        return "Couldn't save %s. Nothing was changed." % names
    return ""


def restore_file(path: str, old: Optional[bytes], replace: Replace = os.replace) -> str:
    """Put ``old`` back. A sentence when that write fails. ``None`` removes the file."""

    resolved = str(Path(path).expanduser().resolve())
    try:
        if old is None:
            if os.path.lexists(resolved):
                os.remove(resolved)
            return ""
        parent = os.path.dirname(resolved) or "."
        fd, temp = tempfile.mkstemp(prefix=".cbcs-", dir=parent)
        try:
            os.write(fd, old)
            os.fsync(fd)
        finally:
            os.close(fd)
        replace(temp, resolved)
    except OSError:
        return "Couldn't restore %s." % os.path.basename(path)
    return ""


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _decode(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def _read(path: str) -> bytes:
    try:
        return Path(path).expanduser().resolve().read_bytes()
    except OSError:
        return b""


def _mode(path: str) -> Optional[int]:
    try:
        return os.stat(path).st_mode & 0o7777
    except OSError:
        return None


def _cleanup(staged: Sequence[tuple[str, str, Optional[bytes]]]) -> None:
    for _resolved, temp, _old in staged:
        if os.path.isfile(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


def _fsync_dir(directory: str) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        return
    finally:
        os.close(fd)
