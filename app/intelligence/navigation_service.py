"""Code navigation services backed by semantic and heuristic layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.semantic_facade import SemanticFacade
from app.intelligence.semantic_models import SemanticOperationMetadata, approximate_metadata
from app.intelligence.symbol_index import SymbolLocation, build_python_symbol_index, to_indexed_symbols
from app.persistence.sqlite_index import IndexedSymbol, SQLiteSymbolIndex

_FACADE_BY_CACHE_DB_PATH: dict[str, SemanticFacade] = {}


@dataclass(frozen=True)
class DefinitionLookupResult:
    """Result for go-to-definition lookup."""

    found: bool
    symbol_name: str
    locations: list[SymbolLocation]
    metadata: SemanticOperationMetadata | None = None


def lookup_definition(project_root: str, current_file_path: str, symbol_name: str) -> DefinitionLookupResult:
    """Lookup symbol definitions preferring current file first."""
    return _lookup_definition_heuristic(project_root, current_file_path, symbol_name)


def lookup_definition_with_cache(
    *,
    project_root: str,
    current_file_path: str,
    symbol_name: str,
    cache_db_path: str,
    source_text: str | None = None,
    cursor_position: int | None = None,
) -> DefinitionLookupResult:
    """Lookup symbol definitions using semantic resolution with cached fallback."""
    clean_name = symbol_name.strip()
    if not clean_name:
        return DefinitionLookupResult(found=False, symbol_name=clean_name, locations=[], metadata=None)

    if source_text is not None and cursor_position is not None:
        try:
            semantic_result = _facade(cache_db_path).lookup_definition(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            )
        except Exception:
            semantic_result = None
        if semantic_result is not None and (semantic_result.found or semantic_result.metadata.unsupported_reason):
            return DefinitionLookupResult(
                found=semantic_result.found,
                symbol_name=semantic_result.symbol_name,
                locations=[
                    SymbolLocation(
                        name=location.name,
                        file_path=location.file_path,
                        line_number=location.line_number,
                        column_number=location.column_number,
                        symbol_kind=location.symbol_kind,
                        container_name=location.container_name,
                        signature_text=location.signature_text,
                        doc_excerpt=location.doc_excerpt,
                    )
                    for location in semantic_result.locations
                ],
                metadata=semantic_result.metadata,
            )

    return _lookup_definition_with_cache_heuristic(
        project_root=project_root,
        current_file_path=current_file_path,
        symbol_name=clean_name,
        cache_db_path=cache_db_path,
    )


def _lookup_definition_heuristic(project_root: str, current_file_path: str, symbol_name: str) -> DefinitionLookupResult:
    clean_name = symbol_name.strip()
    if not clean_name:
        return DefinitionLookupResult(found=False, symbol_name=clean_name, locations=[], metadata=None)

    index = build_python_symbol_index(project_root)
    candidates = list(index.get(clean_name, []))
    if not candidates:
        return DefinitionLookupResult(
            found=False,
            symbol_name=clean_name,
            locations=[],
            metadata=approximate_metadata("ast_index", source="approximate", fallback_reason="heuristic_lookup"),
        )

    current_file = str(Path(current_file_path).expanduser().resolve())
    candidates.sort(key=lambda location: (location.file_path != current_file, location.file_path, location.line_number))
    return DefinitionLookupResult(
        found=True,
        symbol_name=clean_name,
        locations=candidates,
        metadata=approximate_metadata("ast_index", source="approximate", fallback_reason="heuristic_lookup"),
    )


def _lookup_definition_with_cache_heuristic(
    *,
    project_root: str,
    current_file_path: str,
    symbol_name: str,
    cache_db_path: str,
) -> DefinitionLookupResult:
    cache = SQLiteSymbolIndex(cache_db_path)
    cached = cache.lookup(project_root, symbol_name)
    if not cached:
        fresh_index = build_python_symbol_index(project_root)
        indexed_symbols = [
            IndexedSymbol(name=location.name, file_path=location.file_path, line_number=location.line_number)
            for location in to_indexed_symbols(fresh_index)
        ]
        cache.replace_symbols_for_project(project_root, indexed_symbols)
        cached = cache.lookup(project_root, symbol_name)

    if not cached:
        return DefinitionLookupResult(
            found=False,
            symbol_name=symbol_name,
            locations=[],
            metadata=approximate_metadata("sqlite_index", source="approximate", fallback_reason="cache_miss"),
        )

    candidates = [
        SymbolLocation(name=entry.name, file_path=entry.file_path, line_number=entry.line_number) for entry in cached
    ]
    current_file = str(Path(current_file_path).expanduser().resolve())
    candidates.sort(key=lambda location: (location.file_path != current_file, location.file_path, location.line_number))
    return DefinitionLookupResult(
        found=True,
        symbol_name=symbol_name,
        locations=candidates,
        metadata=approximate_metadata("sqlite_index", source="approximate", fallback_reason="heuristic_lookup"),
    )


def _facade(cache_db_path: str) -> SemanticFacade:
    normalized_cache_path = str(Path(cache_db_path).expanduser().resolve())
    cached = _FACADE_BY_CACHE_DB_PATH.get(normalized_cache_path)
    if cached is None:
        cached = SemanticFacade(cache_db_path=normalized_cache_path)
        _FACADE_BY_CACHE_DB_PATH[normalized_cache_path] = cached
    return cached
