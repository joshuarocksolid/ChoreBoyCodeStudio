"""Code navigation services built on project symbol index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.symbol_index import SymbolLocation, build_python_symbol_index, to_indexed_symbols
from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex


@dataclass(frozen=True)
class DefinitionLookupResult:
    """Result for go-to-definition lookup."""

    found: bool
    symbol_name: str
    locations: list[SymbolLocation]


def lookup_definition(project_root: str, current_file_path: str, symbol_name: str) -> DefinitionLookupResult:
    """Lookup symbol definitions preferring current file first."""
    clean_name = symbol_name.strip()
    if not clean_name:
        return DefinitionLookupResult(found=False, symbol_name=clean_name, locations=[])

    index = build_python_symbol_index(project_root)
    candidates = list(index.get(clean_name, []))
    if not candidates:
        return DefinitionLookupResult(found=False, symbol_name=clean_name, locations=[])

    current_file = str(Path(current_file_path).expanduser().resolve())
    candidates.sort(key=lambda location: (location.file_path != current_file, location.file_path, location.line_number))
    return DefinitionLookupResult(found=True, symbol_name=clean_name, locations=candidates)


def lookup_definition_with_cache(
    *,
    project_root: str,
    current_file_path: str,
    symbol_name: str,
    cache_db_path: str,
) -> DefinitionLookupResult:
    """Lookup symbol definitions using SQLite cache with filesystem fallback."""
    clean_name = symbol_name.strip()
    if not clean_name:
        return DefinitionLookupResult(found=False, symbol_name=clean_name, locations=[])

    cache = SQLiteSymbolIndex(cache_db_path)
    cached = cache.lookup(project_root, clean_name)
    if not cached:
        fresh_index = build_python_symbol_index(project_root)
        indexed_symbols = [
            IndexedSymbol(name=location.name, file_path=location.file_path, line_number=location.line_number)
            for location in to_indexed_symbols(fresh_index)
        ]
        cache.replace_symbols_for_project(project_root, indexed_symbols)
        cached = cache.lookup(project_root, clean_name)

    if not cached:
        return DefinitionLookupResult(found=False, symbol_name=clean_name, locations=[])

    candidates = [
        SymbolLocation(name=entry.name, file_path=entry.file_path, line_number=entry.line_number) for entry in cached
    ]
    current_file = str(Path(current_file_path).expanduser().resolve())
    candidates.sort(key=lambda location: (location.file_path != current_file, location.file_path, location.line_number))
    return DefinitionLookupResult(found=True, symbol_name=clean_name, locations=candidates)
