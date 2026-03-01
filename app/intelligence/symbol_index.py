"""Project symbol indexing helpers for Python files."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable

from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex


@dataclass(frozen=True)
class SymbolLocation:
    """One symbol definition location."""

    name: str
    file_path: str
    line_number: int


def to_indexed_symbols(index: dict[str, list["SymbolLocation"]]) -> list["SymbolLocation"]:
    """Flatten symbol index map into deterministic list."""
    flattened: list[SymbolLocation] = []
    for symbol_name in sorted(index.keys()):
        locations = sorted(index[symbol_name], key=lambda item: (item.file_path, item.line_number))
        flattened.extend(locations)
    return flattened


class SymbolIndexWorker:
    """Background worker that builds and persists symbol cache."""

    def __init__(
        self,
        *,
        project_root: str,
        cache_db_path: str,
        on_done: Callable[[int], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self._project_root = str(Path(project_root).expanduser().resolve())
        self._cache_db_path = str(Path(cache_db_path).expanduser().resolve())
        self._on_done = on_done
        self._on_error = on_error
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        try:
            if self._cancel_event.is_set():
                return
            python_files = _list_python_source_files(self._project_root)
            current_fingerprints = {str(path): _file_fingerprint(path) for path in python_files}
            cache = SQLiteSymbolIndex(self._cache_db_path)
            cached_fingerprints = cache.lookup_file_fingerprints(self._project_root)
            if self._cancel_event.is_set():
                return

            deleted_files = sorted(path for path in cached_fingerprints.keys() if path not in current_fingerprints)
            changed_files = sorted(
                path
                for path, fingerprint in current_fingerprints.items()
                if cached_fingerprints.get(path) != fingerprint
            )

            if deleted_files:
                cache.remove_symbols_for_files(self._project_root, deleted_files)
                cache.remove_file_fingerprints(self._project_root, deleted_files)

            symbols_by_file: dict[str, list[IndexedSymbol]] = {}
            for file_path in changed_files:
                if self._cancel_event.is_set():
                    return
                extracted = _extract_symbols(Path(file_path))
                symbols_by_file[file_path] = [
                    IndexedSymbol(name=symbol.name, file_path=symbol.file_path, line_number=symbol.line_number)
                    for symbol in extracted
                ]

            if symbols_by_file:
                cache.upsert_symbols_for_files(self._project_root, symbols_by_file)
            if changed_files:
                cache.upsert_file_fingerprints(
                    self._project_root,
                    {file_path: current_fingerprints[file_path] for file_path in changed_files},
                )
            if self._cancel_event.is_set():
                return
            symbol_count = cache.count_symbols(self._project_root)
            if self._on_done is not None:
                self._on_done(symbol_count)
        except Exception as exc:  # pragma: no cover - defensive thread guard
            if self._on_error is not None:
                self._on_error(str(exc))


def build_python_symbol_index(project_root: str) -> dict[str, list[SymbolLocation]]:
    """Build symbol index for Python source files under project root."""
    python_files = _list_python_source_files(project_root)
    index: dict[str, list[SymbolLocation]] = {}
    for file_path in python_files:
        symbols = _extract_symbols(file_path)
        for symbol in symbols:
            index.setdefault(symbol.name, []).append(symbol)
    return index


def _extract_symbols(file_path: Path) -> list[SymbolLocation]:
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    symbols: list[SymbolLocation] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(
                SymbolLocation(
                    name=node.name,
                    file_path=str(file_path.resolve()),
                    line_number=int(node.lineno),
                )
            )
    return symbols


def _list_python_source_files(project_root: str | Path) -> list[Path]:
    root = Path(project_root).expanduser().resolve()
    python_files: list[Path] = []
    for file_path in sorted(root.rglob("*.py")):
        if ".cbcs" in file_path.parts:
            continue
        python_files.append(file_path.resolve())
    return python_files


def _file_fingerprint(file_path: Path) -> tuple[int, int]:
    file_stat = file_path.stat()
    return (int(file_stat.st_mtime_ns), int(file_stat.st_size))
