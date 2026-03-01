"""SQLite-backed cache for symbol indexing acceleration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexedSymbol:
    name: str
    file_path: str
    line_number: int


class SQLiteSymbolIndex:
    """Small SQLite cache for project symbol lookup."""

    def __init__(self, db_path: str) -> None:
        self._db_path = str(Path(db_path).expanduser().resolve())
        self._initialize_schema()

    @property
    def db_path(self) -> str:
        return self._db_path

    def replace_symbols_for_project(self, project_root: str, symbols: list[IndexedSymbol]) -> None:
        project = str(Path(project_root).expanduser().resolve())
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("DELETE FROM symbols WHERE project_root = ?", (project,))
            connection.executemany(
                "INSERT INTO symbols(project_root, name, file_path, line_number) VALUES(?, ?, ?, ?)",
                [(project, symbol.name, symbol.file_path, symbol.line_number) for symbol in symbols],
            )
            connection.commit()

    def lookup(self, project_root: str, symbol_name: str) -> list[IndexedSymbol]:
        project = str(Path(project_root).expanduser().resolve())
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT name, file_path, line_number FROM symbols WHERE project_root = ? AND name = ? ORDER BY file_path, line_number",
                (project, symbol_name),
            ).fetchall()
        return [IndexedSymbol(name=row[0], file_path=row[1], line_number=int(row[2])) for row in rows]

    def _initialize_schema(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS symbols(
                    project_root TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_project_name ON symbols(project_root, name)"
            )
            connection.commit()
