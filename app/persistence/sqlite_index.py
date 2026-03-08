"""SQLite-backed cache for symbol indexing acceleration."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

CURRENT_SYMBOL_INDEX_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class IndexedSymbol:
    name: str
    file_path: str
    line_number: int
    symbol_kind: str = "symbol"
    container_name: str = ""
    signature_text: str = ""
    doc_excerpt: str = ""
    column_number: int | None = None
    fingerprint_version: int = 1


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
            connection.execute("DELETE FROM indexed_files WHERE project_root = ?", (project,))
            connection.executemany(
                """
                INSERT INTO symbols(
                    project_root,
                    name,
                    file_path,
                    line_number,
                    symbol_kind,
                    container_name,
                    signature_text,
                    doc_excerpt,
                    column_number,
                    fingerprint_version
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        project,
                        symbol.name,
                        symbol.file_path,
                        symbol.line_number,
                        symbol.symbol_kind,
                        symbol.container_name,
                        symbol.signature_text,
                        symbol.doc_excerpt,
                        symbol.column_number,
                        symbol.fingerprint_version,
                    )
                    for symbol in symbols
                ],
            )
            connection.commit()

    def lookup(self, project_root: str, symbol_name: str) -> list[IndexedSymbol]:
        project = str(Path(project_root).expanduser().resolve())
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    name,
                    file_path,
                    line_number,
                    COALESCE(symbol_kind, 'symbol'),
                    COALESCE(container_name, ''),
                    COALESCE(signature_text, ''),
                    COALESCE(doc_excerpt, ''),
                    column_number,
                    COALESCE(fingerprint_version, 1)
                FROM symbols
                WHERE project_root = ? AND name = ?
                ORDER BY file_path, line_number
                """,
                (project, symbol_name),
            ).fetchall()
        return [
            IndexedSymbol(
                name=row[0],
                file_path=row[1],
                line_number=int(row[2]),
                symbol_kind=str(row[3]),
                container_name=str(row[4]),
                signature_text=str(row[5]),
                doc_excerpt=str(row[6]),
                column_number=None if row[7] is None else int(row[7]),
                fingerprint_version=int(row[8]),
            )
            for row in rows
        ]

    def search_by_prefix(self, project_root: str, prefix: str, *, limit: int = 100) -> list[IndexedSymbol]:
        """Return symbols where name matches prefix (case-insensitive)."""
        project = str(Path(project_root).expanduser().resolve())
        normalized_limit = max(1, int(limit))
        with sqlite3.connect(self._db_path) as connection:
            if prefix:
                rows = connection.execute(
                    """
                    SELECT
                        name,
                        file_path,
                        line_number,
                        COALESCE(symbol_kind, 'symbol'),
                        COALESCE(container_name, ''),
                        COALESCE(signature_text, ''),
                        COALESCE(doc_excerpt, ''),
                        column_number,
                        COALESCE(fingerprint_version, 1)
                    FROM symbols
                    WHERE project_root = ? AND lower(name) LIKE ?
                    ORDER BY name, file_path, line_number
                    LIMIT ?
                    """,
                    (project, f"{prefix.lower()}%", normalized_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        name,
                        file_path,
                        line_number,
                        COALESCE(symbol_kind, 'symbol'),
                        COALESCE(container_name, ''),
                        COALESCE(signature_text, ''),
                        COALESCE(doc_excerpt, ''),
                        column_number,
                        COALESCE(fingerprint_version, 1)
                    FROM symbols
                    WHERE project_root = ?
                    ORDER BY name, file_path, line_number
                    LIMIT ?
                    """,
                    (project, normalized_limit),
                ).fetchall()
        return [
            IndexedSymbol(
                name=row[0],
                file_path=row[1],
                line_number=int(row[2]),
                symbol_kind=str(row[3]),
                container_name=str(row[4]),
                signature_text=str(row[5]),
                doc_excerpt=str(row[6]),
                column_number=None if row[7] is None else int(row[7]),
                fingerprint_version=int(row[8]),
            )
            for row in rows
        ]

    def count_symbols(self, project_root: str) -> int:
        project = str(Path(project_root).expanduser().resolve())
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM symbols WHERE project_root = ?",
                (project,),
            ).fetchone()
        return int(row[0]) if row else 0

    def lookup_file_fingerprints(self, project_root: str) -> dict[str, tuple[int, int]]:
        project = str(Path(project_root).expanduser().resolve())
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT file_path, mtime_ns, size_bytes FROM indexed_files WHERE project_root = ?",
                (project,),
            ).fetchall()
        return {str(row[0]): (int(row[1]), int(row[2])) for row in rows}

    def upsert_file_fingerprints(self, project_root: str, fingerprints: dict[str, tuple[int, int]]) -> None:
        if not fingerprints:
            return
        project = str(Path(project_root).expanduser().resolve())
        payload = [
            (project, file_path, int(values[0]), int(values[1]))
            for file_path, values in fingerprints.items()
        ]
        with sqlite3.connect(self._db_path) as connection:
            connection.executemany(
                """
                INSERT INTO indexed_files(project_root, file_path, mtime_ns, size_bytes)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(project_root, file_path)
                DO UPDATE SET mtime_ns=excluded.mtime_ns, size_bytes=excluded.size_bytes
                """,
                payload,
            )
            connection.commit()

    def remove_file_fingerprints(self, project_root: str, file_paths: list[str]) -> None:
        if not file_paths:
            return
        project = str(Path(project_root).expanduser().resolve())
        placeholders = ",".join(["?"] * len(file_paths))
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                f"DELETE FROM indexed_files WHERE project_root = ? AND file_path IN ({placeholders})",
                [project, *file_paths],
            )
            connection.commit()

    def remove_symbols_for_files(self, project_root: str, file_paths: list[str]) -> None:
        if not file_paths:
            return
        project = str(Path(project_root).expanduser().resolve())
        placeholders = ",".join(["?"] * len(file_paths))
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                f"DELETE FROM symbols WHERE project_root = ? AND file_path IN ({placeholders})",
                [project, *file_paths],
            )
            connection.commit()

    def list_indexed_python_files(self, project_root: str) -> list[str]:
        """Return indexed Python file paths for project in deterministic order."""
        project = str(Path(project_root).expanduser().resolve())
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT file_path
                FROM indexed_files
                WHERE project_root = ? AND file_path LIKE '%.py'
                ORDER BY file_path
                """,
                (project,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def upsert_symbols_for_files(self, project_root: str, symbols_by_file: dict[str, list[IndexedSymbol]]) -> None:
        if not symbols_by_file:
            return
        project = str(Path(project_root).expanduser().resolve())
        with sqlite3.connect(self._db_path) as connection:
            for file_path, file_symbols in symbols_by_file.items():
                connection.execute(
                    "DELETE FROM symbols WHERE project_root = ? AND file_path = ?",
                    (project, file_path),
                )
                if not file_symbols:
                    continue
                connection.executemany(
                    """
                    INSERT INTO symbols(
                        project_root,
                        name,
                        file_path,
                        line_number,
                        symbol_kind,
                        container_name,
                        signature_text,
                        doc_excerpt,
                        column_number,
                        fingerprint_version
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            project,
                            symbol.name,
                            symbol.file_path,
                            symbol.line_number,
                            symbol.symbol_kind,
                            symbol.container_name,
                            symbol.signature_text,
                            symbol.doc_excerpt,
                            symbol.column_number,
                            symbol.fingerprint_version,
                        )
                        for symbol in file_symbols
                    ],
                )
            connection.commit()

    def _initialize_schema(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS symbols(
                    project_root TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER NOT NULL,
                    symbol_kind TEXT NOT NULL DEFAULT 'symbol',
                    container_name TEXT NOT NULL DEFAULT '',
                    signature_text TEXT NOT NULL DEFAULT '',
                    doc_excerpt TEXT NOT NULL DEFAULT '',
                    column_number INTEGER,
                    fingerprint_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            self._ensure_symbols_column(connection, "symbol_kind", "TEXT NOT NULL DEFAULT 'symbol'")
            self._ensure_symbols_column(connection, "container_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_symbols_column(connection, "signature_text", "TEXT NOT NULL DEFAULT ''")
            self._ensure_symbols_column(connection, "doc_excerpt", "TEXT NOT NULL DEFAULT ''")
            self._ensure_symbols_column(connection, "column_number", "INTEGER")
            self._ensure_symbols_column(connection, "fingerprint_version", "INTEGER NOT NULL DEFAULT 1")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_files(
                    project_root TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    PRIMARY KEY(project_root, file_path)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_project_name ON symbols(project_root, name)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_project_file ON symbols(project_root, file_path)"
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
                ("schema_version", str(CURRENT_SYMBOL_INDEX_SCHEMA_VERSION)),
            )
            connection.commit()

    def _ensure_symbols_column(self, connection: sqlite3.Connection, column_name: str, definition: str) -> None:
        existing_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(symbols)").fetchall()
        }
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE symbols ADD COLUMN {column_name} {definition}")
