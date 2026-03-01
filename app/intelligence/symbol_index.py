"""Project symbol indexing helpers for Python files."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


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
