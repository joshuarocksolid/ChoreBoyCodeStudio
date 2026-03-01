"""Code navigation services built on project symbol index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.symbol_index import SymbolLocation, build_python_symbol_index


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
