"""Project symbol indexing helpers for Python files."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Sequence

from app.intelligence.python_structure import SymbolLocation, extract_symbol_locations
from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex
from app.project.file_inventory import build_project_inventory_snapshot


def to_indexed_symbols(index: dict[str, list[SymbolLocation]]) -> list[SymbolLocation]:
    """Flatten symbol index map into deterministic list."""
    flattened: list[SymbolLocation] = []
    for symbol_name in sorted(index.keys()):
        locations = sorted(index[symbol_name], key=lambda item: (item.file_path, item.line_number))
        flattened.extend(locations)
    return flattened


def build_python_symbol_index(
    project_root: str,
    *,
    exclude_patterns: Sequence[str] = (),
) -> dict[str, list[SymbolLocation]]:
    """Build symbol index for Python source files under project root."""
    python_files = _list_python_source_files(project_root, exclude_patterns)
    index: dict[str, list[SymbolLocation]] = {}
    for file_path in python_files:
        symbols = extract_symbol_locations(file_path)
        for symbol in symbols:
            index.setdefault(symbol.name, []).append(symbol)
    return index


def update_symbol_index_cache(
    *,
    project_root: str,
    cache_db_path: str,
    exclude_patterns: Sequence[str] = (),
    cancel_event: threading.Event | None = None,
    should_commit: Callable[[], bool] | None = None,
) -> int:
    """Update persisted symbol cache and return indexed symbol count."""

    def _can_commit() -> bool:
        if cancel_event is not None and cancel_event.is_set():
            return False
        if should_commit is not None and not should_commit():
            return False
        return True

    if not _can_commit():
        return 0

    project_root_text = str(Path(project_root).expanduser().resolve())
    cache_path = str(Path(cache_db_path).expanduser().resolve())
    python_files = _list_python_source_files(project_root_text, exclude_patterns)
    current_fingerprints = {str(path): _file_fingerprint(path) for path in python_files}
    cache = SQLiteSymbolIndex(cache_path)
    cached_fingerprints = cache.lookup_file_fingerprints(project_root_text)
    if not _can_commit():
        return 0

    deleted_files = sorted(path for path in cached_fingerprints.keys() if path not in current_fingerprints)
    changed_files = sorted(
        path
        for path, fingerprint in current_fingerprints.items()
        if cached_fingerprints.get(path) != fingerprint
    )

    if deleted_files:
        if not _can_commit():
            return 0
        cache.remove_symbols_for_files(project_root_text, deleted_files)
        cache.remove_file_fingerprints(project_root_text, deleted_files)

    symbols_by_file: dict[str, list[IndexedSymbol]] = {}
    for file_path in changed_files:
        if not _can_commit():
            return 0
        extracted = extract_symbol_locations(Path(file_path))
        symbols_by_file[file_path] = [
            IndexedSymbol(
                name=symbol.name,
                file_path=symbol.file_path,
                line_number=symbol.line_number,
                symbol_kind=symbol.symbol_kind,
                container_name=symbol.container_name,
                signature_text=symbol.signature_text,
                doc_excerpt=symbol.doc_excerpt,
                column_number=symbol.column_number,
                fingerprint_version=1,
            )
            for symbol in extracted
        ]

    if symbols_by_file:
        if not _can_commit():
            return 0
        cache.upsert_symbols_for_files(project_root_text, symbols_by_file)
    if changed_files:
        if not _can_commit():
            return 0
        cache.upsert_file_fingerprints(
            project_root_text,
            {file_path: current_fingerprints[file_path] for file_path in changed_files},
        )
    if not _can_commit():
        return 0
    return cache.count_symbols(project_root_text)


def _list_python_source_files(
    project_root: str | Path,
    exclude_patterns: Sequence[str] = (),
) -> list[Path]:
    snapshot = build_project_inventory_snapshot(project_root, exclude_patterns=exclude_patterns)
    return [Path(path) for path in snapshot.python_file_paths]


def _file_fingerprint(file_path: Path) -> tuple[int, int]:
    file_stat = file_path.stat()
    return (int(file_stat.st_mtime_ns), int(file_stat.st_size))
