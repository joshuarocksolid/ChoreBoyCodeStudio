"""Current-file symbol outline helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutlineSymbol:
    """One symbol entry for outline presentation."""

    name: str
    kind: str
    line_number: int


def build_file_outline(file_path: str) -> list[OutlineSymbol]:
    """Build ordered outline for classes/functions in one Python file."""
    path = Path(file_path).expanduser().resolve()
    if path.suffix.lower() != ".py":
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    outline: list[OutlineSymbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            outline.append(OutlineSymbol(name=node.name, kind="class", line_number=int(node.lineno)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            outline.append(OutlineSymbol(name=node.name, kind="function", line_number=int(node.lineno)))
    outline.sort(key=lambda item: item.line_number)
    return outline
