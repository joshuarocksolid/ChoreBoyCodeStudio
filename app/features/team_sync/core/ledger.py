"""Local sqlite ledger. Never opened on a share path the caller did not already move aside."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from app.features.team_sync.core import TeamSyncError


def _guard(method):  # type: ignore[no-untyped-def]
    """One connection serves the shell thread pool. Hold the lock for the whole call."""

    def wrapped(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        with self._lock:
            return method(self, *args, **kwargs)

    wrapped.__name__ = method.__name__
    wrapped.__doc__ = method.__doc__
    return wrapped


@dataclass(frozen=True)
class OutboxRow:
    bundle_id: str
    recipient: str
    part_idx: int
    part_total: int
    verb: str
    change_id: str
    tip: str
    created_at: str
    out_folder: str
    state: str
    sent_at: str
    delivered_at: str
    accepted_at: str


@dataclass(frozen=True)
class PartRow:
    bundle_id: str
    idx: int
    total: int
    sha256: str
    path: str


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._create()

    @_guard
    def close(self) -> None:
        self._db.close()

    @_guard
    def add_outbox(
        self,
        *,
        bundle_id: str,
        recipient: str,
        part_idx: int,
        part_total: int,
        verb: str,
        change_id: str,
        tip: str,
        created_at: str,
        out_folder: str,
        state: str,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO outbox (
                bundle_id, recipient, part_idx, part_total, verb, change_id, tip,
                created_at, out_folder, state, sent_at, delivered_at, accepted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '')
            """,
            (
                bundle_id,
                recipient,
                part_idx,
                part_total,
                verb,
                change_id,
                tip,
                created_at,
                out_folder,
                state,
            ),
        )
        self._db.commit()

    @_guard
    def set_state(
        self,
        bundle_id: str,
        recipient: str,
        part_idx: int,
        state: str,
        *,
        sent_at: str = "",
        delivered_at: str = "",
        accepted_at: str = "",
    ) -> None:
        current = self._one(bundle_id, recipient, part_idx)
        if current is None:
            return
        self._db.execute(
            """
            UPDATE outbox
               SET state = ?, sent_at = ?, delivered_at = ?, accepted_at = ?
             WHERE bundle_id = ? AND recipient = ? AND part_idx = ?
            """,
            (
                state,
                sent_at or current.sent_at,
                delivered_at or current.delivered_at,
                accepted_at or current.accepted_at,
                bundle_id,
                recipient,
                part_idx,
            ),
        )
        self._db.commit()

    @_guard
    def rows(self, states: Optional[List[str]] = None) -> List[OutboxRow]:
        if states:
            marks = ",".join("?" for _ in states)
            cursor = self._db.execute(
                f"SELECT * FROM outbox WHERE state IN ({marks}) ORDER BY created_at",
                states,
            )
        else:
            cursor = self._db.execute("SELECT * FROM outbox ORDER BY created_at")
        return [_row(item) for item in cursor.fetchall()]

    @_guard
    def for_change(self, change_id: str) -> List[OutboxRow]:
        cursor = self._db.execute(
            "SELECT * FROM outbox WHERE change_id = ? ORDER BY recipient, part_idx",
            (change_id,),
        )
        return [_row(item) for item in cursor.fetchall()]

    @_guard
    def outbox_part(self, bundle_id: str, recipient: str, part_idx: int) -> Optional[OutboxRow]:
        return self._one(bundle_id, recipient, part_idx)

    @_guard
    def for_tip(self, recipient: str, tip: str) -> List[OutboxRow]:
        cursor = self._db.execute(
            "SELECT * FROM outbox WHERE recipient = ? AND tip = ? ORDER BY part_idx",
            (recipient, tip),
        )
        return [_row(item) for item in cursor.fetchall()]

    @_guard
    def latest(self) -> Optional[OutboxRow]:
        cursor = self._db.execute(
            "SELECT * FROM outbox WHERE verb = 'push' ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return _row(row) if row is not None else None

    @_guard
    def mark_seen(self, message_key: str, seen_at: str, result: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO seen (message_key, seen_at, result) VALUES (?, ?, ?)",
            (message_key, seen_at, result),
        )
        self._db.commit()

    @_guard
    def has_seen(self, message_key: str) -> bool:
        cursor = self._db.execute(
            "SELECT 1 FROM seen WHERE message_key = ? LIMIT 1", (message_key,)
        )
        return cursor.fetchone() is not None

    @_guard
    def bump_retry(self, message_key: str) -> int:
        cursor = self._db.execute(
            "SELECT attempts FROM retries WHERE message_key = ?", (message_key,)
        )
        row = cursor.fetchone()
        attempts = int(row[0]) + 1 if row is not None else 1
        self._db.execute(
            "INSERT OR REPLACE INTO retries (message_key, attempts) VALUES (?, ?)",
            (message_key, attempts),
        )
        self._db.commit()
        return attempts

    @_guard
    def delete_outbox(self, bundle_id: str, recipient: str, part_idx: int) -> None:
        self._db.execute(
            "DELETE FROM outbox WHERE bundle_id = ? AND recipient = ? AND part_idx = ?",
            (bundle_id, recipient, part_idx),
        )
        self._db.commit()

    @_guard
    def set_folder(self, bundle_id: str, recipient: str, part_idx: int, out_folder: str) -> None:
        self._db.execute(
            """
            UPDATE outbox SET out_folder = ?
             WHERE bundle_id = ? AND recipient = ? AND part_idx = ?
            """,
            (out_folder, bundle_id, recipient, part_idx),
        )
        self._db.commit()

    @_guard
    def commit_files(self, sha: str) -> Optional[List[Tuple[str, str]]]:
        """Cached changed paths for one immutable commit. ``None`` means not stored yet."""
        cursor = self._db.execute("SELECT payload FROM commit_files WHERE sha = ?", (sha,))
        row = cursor.fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["payload"]))
        return [(str(item[0]), str(item[1])) for item in payload]

    @_guard
    def remember_commit_files(self, sha: str, files: Sequence[Tuple[str, str]]) -> None:
        payload = json.dumps([[path, kind] for path, kind in files])
        self._db.execute(
            "INSERT OR REPLACE INTO commit_files (sha, payload) VALUES (?, ?)",
            (sha, payload),
        )
        self._db.commit()

    @_guard
    def unverified_count(self) -> int:
        cursor = self._db.execute(
            "SELECT COUNT(*) FROM seen WHERE result = 'unverified'"
        )
        row = cursor.fetchone()
        return int(row[0] if row is not None else 0)

    @_guard
    def add_part(self, bundle_id: str, idx: int, total: int, sha256: str, path: str) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO parts (bundle_id, idx, total, sha256, path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bundle_id, idx, total, sha256, path),
        )
        self._db.commit()

    @_guard
    def parts_for(self, bundle_id: str) -> List[PartRow]:
        cursor = self._db.execute(
            "SELECT * FROM parts WHERE bundle_id = ? ORDER BY idx", (bundle_id,)
        )
        return [
            PartRow(
                bundle_id=str(item["bundle_id"]),
                idx=int(item["idx"]),
                total=int(item["total"]),
                sha256=str(item["sha256"]),
                path=str(item["path"]),
            )
            for item in cursor.fetchall()
        ]

    def _one(self, bundle_id: str, recipient: str, part_idx: int) -> Optional[OutboxRow]:
        cursor = self._db.execute(
            "SELECT * FROM outbox WHERE bundle_id = ? AND recipient = ? AND part_idx = ?",
            (bundle_id, recipient, part_idx),
        )
        row = cursor.fetchone()
        return _row(row) if row is not None else None

    def _create(self) -> None:
        try:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS outbox (
                    bundle_id TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    part_idx INTEGER NOT NULL,
                    part_total INTEGER NOT NULL,
                    verb TEXT NOT NULL,
                    change_id TEXT,
                    tip TEXT,
                    created_at TEXT NOT NULL,
                    out_folder TEXT,
                    state TEXT NOT NULL,
                    sent_at TEXT,
                    delivered_at TEXT,
                    accepted_at TEXT,
                    PRIMARY KEY (bundle_id, recipient, part_idx)
                );
                CREATE TABLE IF NOT EXISTS seen (
                    message_key TEXT PRIMARY KEY,
                    seen_at TEXT NOT NULL,
                    result TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS parts (
                    bundle_id TEXT NOT NULL,
                    idx INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    path TEXT NOT NULL,
                    PRIMARY KEY (bundle_id, idx)
                );
                CREATE TABLE IF NOT EXISTS retries (
                    message_key TEXT PRIMARY KEY,
                    attempts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commit_files (
                    sha TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                """
            )
            self._db.commit()
        except sqlite3.Error as exc:
            raise TeamSyncError(f"Could not open the Team Sync ledger: {exc}") from exc


def _row(item: sqlite3.Row) -> OutboxRow:
    return OutboxRow(
        bundle_id=str(item["bundle_id"]),
        recipient=str(item["recipient"]),
        part_idx=int(item["part_idx"]),
        part_total=int(item["part_total"]),
        verb=str(item["verb"]),
        change_id=str(item["change_id"] or ""),
        tip=str(item["tip"] or ""),
        created_at=str(item["created_at"]),
        out_folder=str(item["out_folder"] or ""),
        state=str(item["state"]),
        sent_at=str(item["sent_at"] or ""),
        delivered_at=str(item["delivered_at"] or ""),
        accepted_at=str(item["accepted_at"] or ""),
    )


def iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")
