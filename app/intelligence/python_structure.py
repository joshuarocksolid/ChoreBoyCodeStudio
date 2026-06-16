"""Shared Python structure extraction for outline, indexing, and completion."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SymbolLocation:
    """One symbol definition location extracted from Python source."""

    name: str
    file_path: str
    line_number: int
    symbol_kind: str = "symbol"
    container_name: str = ""
    signature_text: str = ""
    doc_excerpt: str = ""
    column_number: int | None = None


def parse_python_source(source: str, *, filename: str = "<unknown>") -> ast.AST | None:
    try:
        return ast.parse(source, filename=filename)
    except SyntaxError:
        return None


def extract_symbol_locations(file_path: Path, *, source: str | None = None) -> list[SymbolLocation]:
    """Extract top-level function and class symbols from one Python file."""
    if source is None:
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError:
            return []
    tree = parse_python_source(source, filename=str(file_path))
    if tree is None:
        return []

    symbols: list[SymbolLocation] = []
    file_path_text = str(file_path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbol_kind = "class" if isinstance(node, ast.ClassDef) else "function"
            signature_text = ""
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                signature_text = f"{node.name}({_format_arguments(node.args)})"
            doc_text = ast.get_docstring(node) or ""
            symbols.append(
                SymbolLocation(
                    name=node.name,
                    file_path=file_path_text,
                    line_number=int(node.lineno),
                    symbol_kind=symbol_kind,
                    signature_text=signature_text,
                    doc_excerpt=doc_text.strip().splitlines()[0] if doc_text else "",
                    column_number=int(node.col_offset),
                )
            )
    return symbols


def collect_completion_symbol_names(syntax_tree: ast.AST) -> list[str]:
    """Collect top-level symbol names suitable for completion ranking."""
    symbols = _collect_top_level_symbols_from_ast(syntax_tree)
    return sorted(name for name in symbols if name.isidentifier())


def _collect_top_level_symbols_from_ast(syntax_tree: ast.AST) -> set[str]:
    symbols: set[str] = set()
    for node in getattr(syntax_tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                symbols.update(_extract_target_names(target))
            continue
        if isinstance(node, ast.AnnAssign):
            symbols.update(_extract_target_names(node.target))
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(alias.asname or alias.name.split(".")[0])
            continue
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                symbols.add(alias.asname or alias.name)
    return symbols


def _extract_target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_extract_target_names(element))
        return names
    return set()


def _format_arguments(arguments: ast.arguments) -> str:
    rendered: list[str] = []
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
    for argument, default in zip(positional, defaults):
        if default is None:
            rendered.append(argument.arg)
        else:
            rendered.append(f"{argument.arg}={_safe_unparse(default)}")
    if arguments.vararg is not None:
        rendered.append(f"*{arguments.vararg.arg}")
    elif arguments.kwonlyargs:
        rendered.append("*")
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
        if default is None:
            rendered.append(argument.arg)
        else:
            rendered.append(f"{argument.arg}={_safe_unparse(default)}")
    if arguments.kwarg is not None:
        rendered.append(f"**{arguments.kwarg.arg}")
    return ", ".join(rendered)


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive fallback
        return "..."
