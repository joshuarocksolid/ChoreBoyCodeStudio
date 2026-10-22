"""File-lock and SQLite probe for a state directory.

Creating a file is not enough. AppArmor can deny ``fcntl`` on a path that
still accepts ordinary writes, and SQLite then fails with ``database is locked``.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

import fcntl

from app.bootstrap.paths import PathInput


@dataclass(frozen=True)
class StateLockProbeResult:
    """Outcome of one state-directory probe.

    ``operation`` is ``mkdir``, ``write``, ``lock``, or ``sqlite``. On success
    it is ``sqlite``, the last step that had to work.
    """

    ok: bool
    operation: str
    errno: int | None
    message: str


def probe_state_dir(path: PathInput) -> StateLockProbeResult:
    """Create the directory, write a file, lock it, and write a throwaway SQLite database."""
    directory = Path(path).expanduser()
    token = uuid.uuid4().hex
    probe_file = directory / f"cbcs_lock_probe_{token}.tmp"
    database_file = directory / f"cbcs_lock_probe_{token}.sqlite3"
    try:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _failed("mkdir", exc)
        try:
            probe_file.write_text("ok", encoding="utf-8")
        except OSError as exc:
            return _failed("write", exc)
        try:
            _lock_probe_file(probe_file)
        except OSError as exc:
            return _failed("lock", exc)
        try:
            _probe_sqlite(database_file)
        except (sqlite3.Error, OSError) as exc:
            return _failed("sqlite", exc)
        return StateLockProbeResult(
            ok=True,
            operation="sqlite",
            errno=None,
            message="State directory accepts a file lock and a SQLite write.",
        )
    finally:
        _cleanup(probe_file, database_file)


def _lock_probe_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDWR)
    try:
        fcntl.lockf(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)


def _probe_sqlite(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO probe (id) VALUES (1)")
        connection.commit()
    finally:
        connection.close()


def _failed(operation: str, exc: BaseException) -> StateLockProbeResult:
    errno_value = getattr(exc, "errno", None)
    errno = errno_value if isinstance(errno_value, int) else None
    return StateLockProbeResult(
        ok=False,
        operation=operation,
        errno=errno,
        message=str(exc),
    )


def _cleanup(probe_file: Path, database_file: Path) -> None:
    candidates = (
        probe_file,
        database_file,
        Path(str(database_file) + "-wal"),
        Path(str(database_file) + "-shm"),
    )
    for candidate in candidates:
        try:
            candidate.unlink()
        except OSError:
            continue
