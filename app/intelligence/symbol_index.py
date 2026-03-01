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
            index = build_python_symbol_index(self._project_root)
            if self._cancel_event.is_set():
                return
            flattened = to_indexed_symbols(index)
            cache = SQLiteSymbolIndex(self._cache_db_path)
            cached_symbols = [
                IndexedSymbol(name=entry.name, file_path=entry.file_path, line_number=entry.line_number)
                for entry in flattened
            ]
            cache.replace_symbols_for_project(self._project_root, cached_symbols)
            if self._cancel_event.is_set():
                return
            if self._on_done is not None:
                self._on_done(len(cached_symbols))
        except Exception as exc:  # pragma: no cover - defensive thread guard
            if self._on_error is not None:
                self._on_error(str(exc))


def build_python_symbol_index(project_root: str) -> dict[str, list[SymbolLocation]]:
    """Build symbol index for Python source files under project root."""
    root = Path(project_root).expanduser().resolve()
    index: dict[str, list[SymbolLocation]] = {}
    for file_path in sorted(root.rglob("*.py")):
        if ".cbcs" in file_path.parts:
            continue
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
