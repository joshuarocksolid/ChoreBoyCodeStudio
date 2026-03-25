"""Hover metadata resolution helpers for Python editor symbols."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
import inspect
from pathlib import Path

from app.intelligence.semantic_facade import SemanticFacade
from app.intelligence.semantic_models import SemanticOperationMetadata, approximate_metadata
from app.intelligence.navigation_service import lookup_definition_with_cache

_FACADE_BY_CACHE_DB_PATH: dict[str, SemanticFacade] = {}


@dataclass(frozen=True)
class HoverInfo:
    """Resolved hover metadata for one symbol."""

    symbol_name: str
    symbol_kind: str
    file_path: str | None
    line_number: int | None
    doc_summary: str
    source: str
    metadata: SemanticOperationMetadata | None = None


def resolve_hover_info(
    *,
    source_text: str,
    cursor_position: int,
    current_file_path: str,
    project_root: str | None,
    cache_db_path: str | None,
) -> HoverInfo | None:
    """Resolve hover details for the symbol under cursor."""
    if project_root and cache_db_path:
        try:
            semantic_hover = _facade(cache_db_path).resolve_hover_info(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
                cursor_position=cursor_position,
            )
        except Exception:
            semantic_hover = None
        if semantic_hover is not None and not semantic_hover.metadata.unsupported_reason:
            return HoverInfo(
                symbol_name=semantic_hover.symbol_name,
                symbol_kind=semantic_hover.symbol_kind,
                file_path=semantic_hover.file_path,
                line_number=semantic_hover.line_number,
                doc_summary=semantic_hover.doc_summary,
                source=semantic_hover.metadata.source,
                metadata=semantic_hover.metadata,
            )

    symbol_name = _extract_symbol_under_cursor(source_text, cursor_position)
    if not symbol_name:
        return None

    metadata = _lookup_symbol_in_source(source_text, symbol_name)
    if metadata is not None:
        kind, line_number, doc_summary = metadata
        return HoverInfo(
            symbol_name=symbol_name,
            symbol_kind=kind,
            file_path=current_file_path,
            line_number=line_number,
            doc_summary=doc_summary,
            source="current_file",
            metadata=approximate_metadata("ast_hover", source="approximate", fallback_reason="current_file_ast"),
        )

    if project_root and cache_db_path:
        definition = lookup_definition_with_cache(
            project_root=project_root,
            current_file_path=current_file_path,
            symbol_name=symbol_name,
            cache_db_path=cache_db_path,
        )
        if definition.found and definition.locations:
            first_location = definition.locations[0]
            kind, line_number, doc_summary = _lookup_symbol_in_file(first_location.file_path, symbol_name)
            return HoverInfo(
                symbol_name=symbol_name,
                symbol_kind=kind,
                file_path=first_location.file_path,
                line_number=line_number,
                doc_summary=doc_summary,
                source="project_index",
                metadata=approximate_metadata("project_index", source="approximate", fallback_reason="index_lookup"),
            )

    builtin_hover = _resolve_builtin_hover(symbol_name)
    if builtin_hover is not None:
        return builtin_hover
    return None


def _extract_symbol_under_cursor(source_text: str, cursor_position: int) -> str:
    safe_cursor = max(0, min(cursor_position, len(source_text)))
    if safe_cursor == 0:
        return ""

    left = safe_cursor
    while left > 0 and _is_symbol_character(source_text[left - 1]):
        left -= 1

    right = safe_cursor
    while right < len(source_text) and _is_symbol_character(source_text[right]):
        right += 1

    symbol = source_text[left:right].strip()
    if not symbol.isidentifier():
        return ""
    return symbol


def _lookup_symbol_in_file(file_path: str, symbol_name: str) -> tuple[str, int | None, str]:
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return ("symbol", None, "")
    metadata = _lookup_symbol_in_source(source, symbol_name)
    if metadata is None:
        return ("symbol", None, "")
    return metadata


def _lookup_symbol_in_source(source_text: str, symbol_name: str) -> tuple[str, int | None, str] | None:
    syntax_tree = _parse_source_with_recovery(source_text)
    if syntax_tree is None:
        return None

    for node in ast.walk(syntax_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol_name:
            return ("function", int(node.lineno), _doc_summary(ast.get_docstring(node)))
        if isinstance(node, ast.ClassDef) and node.name == symbol_name:
            return ("class", int(node.lineno), _doc_summary(ast.get_docstring(node)))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol_name:
                    return ("variable", int(node.lineno), "")
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == symbol_name:
                return ("variable", int(node.lineno), "")
        if isinstance(node, ast.Import):
            for alias in node.names:
                alias_name = alias.asname or alias.name.split(".")[0]
                if alias_name == symbol_name:
                    return ("import", int(node.lineno), "")
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                alias_name = alias.asname or alias.name
                if alias_name == symbol_name:
                    return ("import", int(node.lineno), "")
    return None


def _resolve_builtin_hover(symbol_name: str) -> HoverInfo | None:
    candidate = getattr(builtins, symbol_name, None)
    if candidate is None:
        return None
    doc = inspect.getdoc(candidate) or ""
    return HoverInfo(
        symbol_name=symbol_name,
        symbol_kind="builtin",
        file_path=None,
        line_number=None,
        doc_summary=_doc_summary(doc),
        source="builtin",
        metadata=approximate_metadata("builtin", source="builtin", fallback_reason="builtin_lookup"),
    )


def _doc_summary(doc_text: str | None) -> str:
    if not doc_text:
        return ""
    return doc_text.strip().splitlines()[0]


def _parse_source_with_recovery(source_text: str) -> ast.AST | None:
    try:
        return ast.parse(source_text)
    except SyntaxError:
        pass

    lines = source_text.splitlines()
    while lines:
        lines.pop()
        candidate = "\n".join(lines).strip()
        if not candidate:
            return None
        try:
            return ast.parse(candidate + "\n")
        except SyntaxError:
            continue
    return None


def _is_symbol_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def _facade(cache_db_path: str) -> SemanticFacade:
    normalized_cache_path = str(Path(cache_db_path).expanduser().resolve())
    cached = _FACADE_BY_CACHE_DB_PATH.get(normalized_cache_path)
    if cached is None:
        cached = SemanticFacade(cache_db_path=normalized_cache_path)
        _FACADE_BY_CACHE_DB_PATH[normalized_cache_path] = cached
    return cached
