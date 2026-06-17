"""Completion candidate providers used by the completion service."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
import keyword
from pathlib import Path
import re

from app.intelligence.api_index import provide_api_index_member_items
from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.intelligence.import_resolver import resolve_module_binding
from app.intelligence.python_structure import collect_completion_symbol_names, extract_symbol_locations
from app.persistence.sqlite_index import SQLiteSymbolIndex
from app.project.dependency_classifier import STDLIB_TOP_LEVELS
from app.project.file_inventory import (
    ProjectInventorySnapshot,
    iter_python_files,
    module_names_from_snapshot,
)
from app.project.import_layout import load_project_import_layout, module_name_for_file

_IDENTIFIER_PREFIX_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_DOTTED_NAME = r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
_MODULE_MEMBER_CONTEXT_PATTERN = re.compile(r"(" + _DOTTED_NAME + r")\.([A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True)
class ModuleMemberCompletionContext:
    """Cursor context for completion requests on module members."""

    base_identifier: str
    member_prefix: str
    base_expression: str = ""


def detect_module_member_completion_context(source_text: str, cursor_position: int) -> ModuleMemberCompletionContext | None:
    """Detect completion context for `<identifier>.<member_prefix?>`."""
    safe_position = max(0, min(cursor_position, len(source_text)))
    snippet = source_text[:safe_position]
    match = _MODULE_MEMBER_CONTEXT_PATTERN.search(snippet)
    if match is None:
        return None
    base_expression = match.group(1)
    base_identifier = base_expression.split(".")[0]
    if not base_identifier.isidentifier():
        return None
    member_prefix = match.group(2) or ""
    return ModuleMemberCompletionContext(
        base_identifier=base_identifier,
        member_prefix=member_prefix,
        base_expression=base_expression,
    )


def collect_import_module_bindings(source_text: str) -> dict[str, str]:
    """Collect import aliases mapped to module-name candidates from source."""
    syntax_tree = _parse_source_with_recovery(source_text)
    if syntax_tree is None:
        return {}

    bindings: dict[str, str] = {}
    for node in getattr(syntax_tree, "body", []):
        if isinstance(node, ast.Import):
            for alias in node.names:
                alias_name = alias.asname or alias.name.split(".")[0]
                if alias_name.isidentifier():
                    bindings[alias_name] = alias.name
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module is None or node.level > 0:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            alias_name = alias.asname or alias.name
            if not alias_name.isidentifier():
                continue
            bindings[alias_name] = f"{node.module}.{alias.name}"
    return bindings


def extract_completion_prefix(source_text: str, cursor_position: int) -> str:
    """Return identifier prefix immediately before cursor."""
    safe_position = max(0, min(cursor_position, len(source_text)))
    snippet = source_text[:safe_position]
    match = _IDENTIFIER_PREFIX_PATTERN.search(snippet)
    if match is None:
        return ""
    return match.group(0)


def provide_keyword_items(prefix: str) -> list[CompletionItem]:
    """Return keyword completion candidates."""
    return [
        CompletionItem(label=word, insert_text=word, kind=CompletionKind.KEYWORD, detail="keyword")
        for word in sorted(keyword.kwlist)
        if _matches_prefix(word, prefix)
    ]


def provide_builtin_items(prefix: str) -> list[CompletionItem]:
    """Return Python builtin completion candidates."""
    names = sorted(name for name in dir(builtins) if name and not name.startswith("__"))
    return [
        CompletionItem(label=name, insert_text=name, kind=CompletionKind.BUILTIN, detail="builtin")
        for name in names
        if _matches_prefix(name, prefix)
    ]


def provide_current_file_symbol_items(
    source_text: str,
    *,
    prefix: str,
    file_path: str,
) -> list[CompletionItem]:
    """Return completion candidates extracted from current file AST."""
    try:
        syntax_tree = ast.parse(source_text)
    except SyntaxError:
        return []

    symbol_names = collect_completion_symbol_names(syntax_tree)
    return [
        CompletionItem(
            label=name,
            insert_text=name,
            kind=CompletionKind.SYMBOL,
            detail="current file",
            source_file_path=file_path,
        )
        for name in symbol_names
        if _matches_prefix(name, prefix)
    ]


def provide_project_symbol_items(
    *,
    project_root: str | None,
    cache_db_path: str,
    prefix: str,
    limit: int,
    inventory_snapshot: ProjectInventorySnapshot | None = None,
) -> list[CompletionItem]:
    """Return completion candidates from persisted project symbol cache."""
    if not project_root:
        return []

    project_root_text = str(Path(project_root).expanduser().resolve())
    cache = SQLiteSymbolIndex(cache_db_path)
    symbols = cache.search_by_prefix(project_root_text, prefix, limit=limit)
    if symbols:
        return [
            CompletionItem(
                label=symbol.name,
                insert_text=symbol.name,
                kind=CompletionKind.SYMBOL,
                detail=f"{Path(symbol.file_path).name}:{symbol.line_number}",
                source_file_path=symbol.file_path,
                source="cache",
                confidence="exact",
            )
            for symbol in symbols
        ]

    if cache.count_symbols(project_root_text) > 0:
        return []

    if inventory_snapshot is None:
        return []

    approximate_items: list[CompletionItem] = []
    for file_path in inventory_snapshot.python_file_paths:
        for symbol in extract_symbol_locations(Path(file_path)):
            if not _matches_prefix(symbol.name, prefix):
                continue
            approximate_items.append(
                CompletionItem(
                    label=symbol.name,
                    insert_text=symbol.name,
                    kind=CompletionKind.SYMBOL,
                    detail=f"{Path(symbol.file_path).name}:{symbol.line_number} • approximate",
                    source_file_path=symbol.file_path,
                    source="approximate",
                    confidence="approximate",
                )
            )
            if len(approximate_items) >= limit:
                break
        if len(approximate_items) >= limit:
            break
    return sorted(approximate_items, key=lambda item: item.label)[:limit]


def provide_project_module_items(
    *,
    project_root: str | None,
    prefix: str,
    limit: int,
    cache_db_path: str | None = None,
    inventory_snapshot: ProjectInventorySnapshot | None = None,
) -> list[CompletionItem]:
    """Return completion candidates for project-local importable modules."""
    if project_root is None:
        return []
    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        return []

    if cache_db_path:
        cache_path = Path(cache_db_path).expanduser().resolve()
        if cache_path.exists():
            indexed_files = SQLiteSymbolIndex(str(cache_path)).list_indexed_python_files(str(root))
            if indexed_files and _indexed_files_match_snapshot(indexed_files, inventory_snapshot):
                if inventory_snapshot is not None:
                    module_names = module_names_from_snapshot(inventory_snapshot)
                else:
                    layout = load_project_import_layout(root)
                    module_names = sorted(
                        {
                            name
                            for path in indexed_files
                            if (name := module_name_for_file(layout, Path(path))) is not None
                        }
                    )
                filtered = _filter_module_names(
                    module_names,
                    prefix=prefix,
                    limit=limit,
                )
                return _module_completion_items(filtered, source="cache")

    if inventory_snapshot is None:
        return []

    filtered = _filter_module_names(
        module_names_from_snapshot(inventory_snapshot),
        prefix=prefix,
        limit=limit,
    )
    return _module_completion_items(filtered)


def provide_module_member_items(
    *,
    project_root: str | None,
    source_text: str,
    cursor_position: int,
    limit: int,
) -> list[CompletionItem]:
    """Return completion candidates for `<imported_module>.<member>` contexts."""
    context = detect_module_member_completion_context(source_text, cursor_position)
    if context is None:
        return []

    bindings = collect_import_module_bindings(source_text)
    api_module_name = _resolve_api_index_name(context, bindings)
    if api_module_name:
        indexed_items = provide_api_index_member_items(
            module_name=api_module_name,
            member_prefix=context.member_prefix,
            limit=limit,
        )
        if indexed_items:
            return indexed_items
    if context.base_identifier in STDLIB_TOP_LEVELS:
        indexed_items = provide_api_index_member_items(
            module_name=context.base_identifier,
            member_prefix=context.member_prefix,
            limit=limit,
        )
        if indexed_items:
            return indexed_items
    if project_root is None:
        return []
    resolution = resolve_module_binding(project_root, bindings=bindings, binding_name=context.base_identifier)
    if not resolution.is_resolved or not resolution.resolved_path:
        return []

    module_symbols = _collect_module_symbols_from_file(
        file_path=Path(resolution.resolved_path),
        member_prefix=context.member_prefix,
    )
    if not module_symbols:
        return []

    return [
        CompletionItem(
            label=name,
            insert_text=name,
            kind=CompletionKind.SYMBOL,
            detail=f"{Path(resolution.resolved_path).name} member",
            source_file_path=resolution.resolved_path,
        )
        for name in sorted(module_symbols)[: max(1, int(limit))]
    ]


def _resolve_api_index_name(context: ModuleMemberCompletionContext, bindings: dict[str, str]) -> str:
    expression_parts = context.base_expression.split(".") if context.base_expression else [context.base_identifier]
    first = expression_parts[0]
    bound = bindings.get(first, first)
    if bound == first:
        return context.base_expression or first
    if len(expression_parts) == 1:
        return bound
    return ".".join([bound, *expression_parts[1:]])


def _collect_module_symbols_from_file(*, file_path: Path, member_prefix: str) -> set[str]:
    try:
        source_text = file_path.read_text(encoding="utf-8")
    except OSError:
        return set()

    syntax_tree = _parse_source_with_recovery(source_text)
    if syntax_tree is None:
        return set()

    symbols = set(collect_completion_symbol_names(syntax_tree))
    if not member_prefix.startswith("_"):
        symbols = {name for name in symbols if not name.startswith("_")}
    return {name for name in symbols if _matches_prefix(name, member_prefix)}


def _filter_module_names(module_names: list[str], *, prefix: str, limit: int) -> list[str]:
    filtered: list[str] = []
    for module_name in module_names:
        if not _matches_prefix(module_name, prefix):
            continue
        filtered.append(module_name)
        if len(filtered) >= limit:
            break
    return filtered


def _module_completion_items(module_names: list[str], *, source: str = "approximate") -> list[CompletionItem]:
    confidence = "exact" if source == "cache" else "approximate"
    return [
        CompletionItem(
            label=module_name,
            insert_text=module_name,
            kind=CompletionKind.MODULE,
            detail="project module",
            source=source,
            confidence=confidence,
        )
        for module_name in module_names
    ]


def _indexed_files_match_snapshot(
    indexed_files: list[str],
    inventory_snapshot: ProjectInventorySnapshot | None,
) -> bool:
    if inventory_snapshot is None:
        return True
    return set(indexed_files) == set(inventory_snapshot.python_file_paths)


def _matches_prefix(candidate: str, prefix: str) -> bool:
    if not prefix:
        return True
    candidate_lower = candidate.lower()
    prefix_lower = prefix.lower()
    return candidate_lower.startswith(prefix_lower) or prefix_lower in candidate_lower


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
