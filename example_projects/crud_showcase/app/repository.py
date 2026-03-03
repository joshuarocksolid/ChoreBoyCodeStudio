"""SQLite-backed task repository demonstrating CRUD operations.

The database file is stored alongside the project so everything stays
filesystem-first and portable.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


DB_FILENAME = "tasks.sqlite3"


@dataclass
class Task:
    """A single task record."""

    task_id: int
    title: str
    description: str
    status: str  # "pending", "in_progress", "done"


class TaskRepository:
    """Thin wrapper around a local SQLite database for task CRUD."""

    VALID_STATUSES = ("pending", "in_progress", "done")

    def __init__(self, project_root: str | Path) -> None:
        db_path = Path(project_root) / DB_FILENAME
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'pending'
            )
            """
        )
        self._conn.commit()

    def create(self, title: str, description: str = "", status: str = "pending") -> Task:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status!r}")
        cursor = self._conn.execute(
            "INSERT INTO tasks (title, description, status) VALUES (?, ?, ?)",
            (title, description, status),
        )
        self._conn.commit()
        return Task(task_id=cursor.lastrowid or 0, title=title, description=description, status=status)

    def read_all(self, status_filter: Optional[str] = None, search: str = "") -> List[Task]:
        query = "SELECT id, title, description, status FROM tasks WHERE 1=1"
        params: list[str] = []
        if status_filter and status_filter in self.VALID_STATUSES:
            query += " AND status = ?"
            params.append(status_filter)
        if search.strip():
            query += " AND (title LIKE ? OR description LIKE ?)"
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern])
        query += " ORDER BY id DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [Task(task_id=r[0], title=r[1], description=r[2], status=r[3]) for r in rows]

    def update(self, task_id: int, title: str, description: str, status: str) -> bool:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status!r}")
        cursor = self._conn.execute(
            "UPDATE tasks SET title = ?, description = ?, status = ? WHERE id = ?",
            (title, description, status, task_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, task_id: int) -> bool:
        cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count_by_status(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        ).fetchall()
        counts = {s: 0 for s in self.VALID_STATUSES}
        for status, count in rows:
            counts[status] = count
        return counts

    def close(self) -> None:
        self._conn.close()
