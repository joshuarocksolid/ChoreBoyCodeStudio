"""Completion candidate providers used by the completion service."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
import keyword
from pathlib import Path
import re

from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.intelligence.import_resolver import resolve_module_binding
from app.persistence.sqlite_index import SQLiteSymbolIndex
from app.project.file_inventory import iter_python_files

_IDENTIFIER_PREFIX_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_MODULE_MEMBER_CONTEXT_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)?$")
_PROJECT_MODULE_CACHE: dict[tuple[str, str], tuple[int, list[str]]] = {}


@dataclass(frozen=True)
class ModuleMemberCompletionContext:
    """Cursor context for completion requests on module members."""

    base_identifier: str
    member_prefix: str


def detect_module_member_completion_context(source_text: str, cursor_position: int) -> ModuleMemberCompletionContext | None:
    """Detect completion context for `<identifier>.<member_prefix?>`."""
    safe_position = max(0, min(cursor_position, len(source_text)))
    snippet = source_text[:safe_position]
    match = _MODULE_MEMBER_CONTEXT_PATTERN.search(snippet)
    if match is None:
        return None
    base_identifier = match.group(1)
    if not base_identifier.isidentifier():
        return None
    member_prefix = match.group(2) or ""
    return ModuleMemberCompletionContext(base_identifier=base_identifier, member_prefix=member_prefix)


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

    symbol_names = sorted(_collect_symbols_from_ast(syntax_tree))
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
) -> list[CompletionItem]:
    """Return completion candidates from persisted project symbol cache."""
    if not project_root:
        return []

    cache = SQLiteSymbolIndex(cache_db_path)
    symbols = cache.search_by_prefix(project_root, prefix, limit=limit)
    items: list[CompletionItem] = []
    for symbol in symbols:
        items.append(
            CompletionItem(
                label=symbol.name,
                insert_text=symbol.name,
                kind=CompletionKind.SYMBOL,
                detail=f"{Path(symbol.file_path).name}:{symbol.line_number}",
                source_file_path=symbol.file_path,
            )
        )
    return items


def provide_project_module_items(
    *,
    project_root: str | None,
    prefix: str,
    limit: int,
    cache_db_path: str | None = None,
) -> list[CompletionItem]:
    """Return completion candidates for project-local importable modules."""
    if project_root is None:
        return []
    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        return []

    candidates: list[str] = []
    if cache_db_path:
        cache_path = Path(cache_db_path).expanduser().resolve()
        cache_stamp = int(cache_path.stat().st_mtime_ns) if cache_path.exists() else -1
        cache_key = (str(root), str(cache_path))
        cached_entry = _PROJECT_MODULE_CACHE.get(cache_key)
        if cached_entry is not None and cached_entry[0] == cache_stamp:
            return _module_completion_items(
                _filter_module_names(cached_entry[1], prefix=prefix, limit=limit)
            )

        indexed_files = SQLiteSymbolIndex(str(cache_path)).list_indexed_python_files(str(root))
        if indexed_files:
            candidates = _module_names_from_indexed_paths(
                project_root=root,
                indexed_file_paths=indexed_files,
            )
            _PROJECT_MODULE_CACHE[cache_key] = (cache_stamp, candidates)
            return _module_completion_items(_filter_module_names(candidates, prefix=prefix, limit=limit))

    for file_path in iter_python_files(root):
        module_name = _module_name_from_path(root, file_path)
        if module_name is None:
            continue
        if not _matches_prefix(module_name, prefix):
            continue
        candidates.append(module_name)
        if len(candidates) >= limit:
            break

    deduped = sorted(set(candidates))
    return _module_completion_items(deduped)


def provide_module_member_items(
    *,
    project_root: str | None,
    source_text: str,
    cursor_position: int,
    limit: int,
) -> list[CompletionItem]:
    """Return completion candidates for `<imported_module>.<member>` contexts."""
    if project_root is None:
        return []
    context = detect_module_member_completion_context(source_text, cursor_position)
    if context is None:
        return []

    bindings = collect_import_module_bindings(source_text)
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


def _collect_symbols_from_ast(syntax_tree: ast.AST) -> set[str]:
    symbols: set[str] = set()
    for node in ast.walk(syntax_tree):
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
                symbols.add(alias.asname or alias.name)
    return {symbol for symbol in symbols if symbol and symbol.isidentifier()}


def _collect_module_symbols_from_file(*, file_path: Path, member_prefix: str) -> set[str]:
    try:
        source_text = file_path.read_text(encoding="utf-8")
    except OSError:
        return set()

    syntax_tree = _parse_source_with_recovery(source_text)
    if syntax_tree is None:
        return set()

    symbols = _collect_top_level_symbols_from_ast(syntax_tree)
    if not member_prefix.startswith("_"):
        symbols = {name for name in symbols if not name.startswith("_")}
    return {name for name in symbols if _matches_prefix(name, member_prefix)}


def _module_names_from_indexed_paths(
    *,
    project_root: Path,
    indexed_file_paths: list[str],
) -> list[str]:
    normalized_root = project_root.as_posix().rstrip("/")
    root_prefix = f"{normalized_root}/"
    module_names: set[str] = set()
    for file_path in indexed_file_paths:
        normalized_path = file_path.replace("\\", "/")
        if not normalized_path.startswith(root_prefix):
            continue
        relative_path = normalized_path[len(root_prefix) :]
        module_name = _module_name_from_relative_path(relative_path)
        if module_name is None:
            continue
        module_names.add(module_name)
    return sorted(module_names)


def _filter_module_names(module_names: list[str], *, prefix: str, limit: int) -> list[str]:
    filtered: list[str] = []
    for module_name in module_names:
        if not _matches_prefix(module_name, prefix):
            continue
        filtered.append(module_name)
        if len(filtered) >= limit:
            break
    return filtered


def _module_completion_items(module_names: list[str]) -> list[CompletionItem]:
    return [
        CompletionItem(
            label=module_name,
            insert_text=module_name,
            kind=CompletionKind.MODULE,
            detail="project module",
        )
        for module_name in module_names
    ]


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
    return {symbol for symbol in symbols if symbol and symbol.isidentifier()}


def _extract_target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_extract_target_names(element))
        return names
    return set()


def _module_name_from_path(project_root: Path, file_path: Path) -> str | None:
    relative_path = file_path.relative_to(project_root).as_posix()
    return _module_name_from_relative_path(relative_path)


def _module_name_from_relative_path(relative_path: str) -> str | None:
    if not relative_path.endswith(".py"):
        return None
    module_path = relative_path[:-3]
    if module_path.endswith("/__init__"):
        module_path = module_path[: -len("/__init__")]
    module_path = module_path.strip("/")
    if not module_path:
        return None
    return module_path.replace("/", ".")


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
