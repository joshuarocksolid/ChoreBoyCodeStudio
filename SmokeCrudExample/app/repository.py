"""SQLite-backed task repository demonstrating CRUD operations.

The database file is stored alongside the project so everything stays
filesystem-first and portable.
"""

import sqlite3
# Test comment2
from pathlib import Path


DB_FILENAME = "tasks.sqlite3"


class Task:
    """A single task record."""

    def __init__(self, task_id, title, description="", status="pending"):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.status = status

    def __repr__(self):
        return (
            f"Task(task_id={self.task_id!r}, title={self.title!r}, "
            f"description={self.description!r}, status={self.status!r})"
        )

    def __eq__(self, other):
        if not isinstance(other, Task):
            return NotImplemented
        return (
            self.task_id == other.task_id
            and self.title == other.title
            and self.description == other.description
            and self.status == other.status
        )


class TaskRepository:
    """Thin wrapper around a local SQLite database for task CRUD."""

    VALID_STATUSES = ("pending", "in_progress", "done")

    def __init__(self, project_root):
        db_path = Path(project_root) / DB_FILENAME
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()

    def _ensure_schema(self):
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

    def create(self, title, description="", status="pending"):
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status!r}")
        cursor = self._conn.execute(
            "INSERT INTO tasks (title, description, status) VALUES (?, ?, ?)",
            (title, description, status),
        )
        self._conn.commit()
        return Task(task_id=cursor.lastrowid or 0, title=title, description=description, status=status)

    def read_all(self, status_filter=None, search=""):
        query = "SELECT id, title, description, status FROM tasks WHERE 1=1"
        params = []
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

    def update(self, task_id, title, description, status):
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status!r}")
        cursor = self._conn.execute(
            "UPDATE tasks SET title = ?, description = ?, status = ? WHERE id = ?",
            (title, description, status, task_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, task_id):
        cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count_by_status(self):
        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        ).fetchall()
        counts = {s: 0 for s in self.VALID_STATUSES}
        for status, count in rows:
            counts[status] = count
        return counts

    def close(self):
        self._conn.close()
