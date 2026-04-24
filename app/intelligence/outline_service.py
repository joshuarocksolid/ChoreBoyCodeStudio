"""Hierarchical outline extraction for Python source files.

Uses tree-sitter (already loaded by the app via `app.treesitter.loader`) so
that the outline survives mid-edit syntax errors -- tree-sitter returns a
partial tree with `ERROR` nodes which we walk while ignoring the broken
fragments. Falls back to the standard library `ast` module when the
tree-sitter runtime is unavailable (e.g. in some headless test environments).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from app.bootstrap.logging_setup import get_subsystem_logger
from app.treesitter.language_registry import default_tree_sitter_language_registry
from app.treesitter.loader import initialize_tree_sitter_runtime, runtime_status

_LOGGER = get_subsystem_logger("outline")

OutlineKind = str  # one of: class, function, async_function, method, async_method, property, constant, field

_CONSTANT_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DETAIL_MAX_CHARS = 40


@dataclass(frozen=True)
class OutlineSymbol:
    """One symbol entry in a hierarchical outline."""

    name: str
    qualified_name: str
    kind: OutlineKind
    line_number: int
    end_line_number: int
    detail: str = ""
    children: tuple["OutlineSymbol", ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_outline_from_source(source: str, language: str = "python") -> tuple[OutlineSymbol, ...]:
    """Build a hierarchical outline from in-memory source text.

    Returns an empty tuple for unsupported languages or when parsing produces
    no usable symbols.
    """
    if language != "python":
        return ()
    if not source:
        return ()

    treesitter_outline = _build_outline_with_treesitter(source)
    if treesitter_outline is not None:
        return treesitter_outline
    return _build_outline_with_ast(source)


def build_file_outline(file_path: str) -> tuple[OutlineSymbol, ...]:
    """Build outline for a Python file on disk.

    Convenience wrapper that reads the file and delegates to
    :func:`build_outline_from_source`. Returns an empty tuple for non-Python
    files or when the file cannot be read.
    """
    path = Path(file_path).expanduser().resolve()
    if path.suffix.lower() not in {".py", ".pyw", ".pyi"}:
        return ()
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    return build_outline_from_source(source)


def find_innermost_symbol(
    symbols: Iterable[OutlineSymbol], line_number: int
) -> Optional[OutlineSymbol]:
    """Return the deepest symbol whose range contains the given 1-based line.

    Returns ``None`` when the line falls outside every top-level symbol
    (e.g. on whitespace between two top-level functions).
    """
    for symbol in symbols:
        if symbol.line_number <= line_number <= symbol.end_line_number:
            inner = find_innermost_symbol(symbol.children, line_number)
            return inner if inner is not None else symbol
    return None


def flatten_symbols(symbols: Iterable[OutlineSymbol]) -> tuple[OutlineSymbol, ...]:
    """Depth-first flatten of a symbol tree, parents before children."""
    flat: list[OutlineSymbol] = []
    for symbol in symbols:
        flat.append(symbol)
        flat.extend(flatten_symbols(symbol.children))
    return tuple(flat)


# ---------------------------------------------------------------------------
# Tree-sitter implementation
# ---------------------------------------------------------------------------


def _build_outline_with_treesitter(source: str) -> Optional[tuple[OutlineSymbol, ...]]:
    """Parse via tree-sitter; return ``None`` if runtime is unavailable."""
    initialize_tree_sitter_runtime()
    if not runtime_status().is_available:
        return None
    registry = default_tree_sitter_language_registry()
    resolved = registry.resolve_for_key("python")
    if resolved is None:
        return None
    try:
        import tree_sitter  # type: ignore
    except ImportError:
        return None

    parser: Any = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(resolved.language)
    else:
        parser.language = resolved.language
    try:
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)
    except Exception:  # pragma: no cover - defensive against parser crashes
        _LOGGER.exception("tree-sitter outline parse failed")
        return None

    return _extract_module_symbols(tree.root_node, source_bytes, parent_qualifier="")


def _extract_module_symbols(
    module_node: Any, source_bytes: bytes, parent_qualifier: str
) -> tuple[OutlineSymbol, ...]:
    return _extract_block_symbols(
        module_node, source_bytes, parent_qualifier=parent_qualifier, in_class=False
    )


def _extract_block_symbols(
    block_node: Any, source_bytes: bytes, *, parent_qualifier: str, in_class: bool
) -> tuple[OutlineSymbol, ...]:
    """Walk the children of a `module` or `block` node, producing symbols.

    Adjacent property setter/deleter decorators are merged into the prior
    `@property` entry.
    """
    symbols: list[OutlineSymbol] = []
    for child in block_node.children:
        new_symbol = _symbol_for_node(
            child, source_bytes, parent_qualifier=parent_qualifier, in_class=in_class
        )
        if new_symbol is None:
            continue
        if (
            in_class
            and symbols
            and symbols[-1].kind == "property"
            and new_symbol.kind in ("method", "async_method")
            and new_symbol.name == symbols[-1].name
            and _node_is_property_setter_or_deleter(child, source_bytes)
        ):
            previous = symbols[-1]
            symbols[-1] = OutlineSymbol(
                name=previous.name,
                qualified_name=previous.qualified_name,
                kind="property",
                line_number=previous.line_number,
                end_line_number=max(previous.end_line_number, new_symbol.end_line_number),
                detail=previous.detail,
                children=previous.children,
            )
            continue
        symbols.append(new_symbol)
    return tuple(symbols)


def _symbol_for_node(
    node: Any, source_bytes: bytes, *, parent_qualifier: str, in_class: bool
) -> Optional[OutlineSymbol]:
    node_type = node.type
    if node_type == "class_definition":
        return _build_class_symbol(node, source_bytes, parent_qualifier=parent_qualifier)
    if node_type == "function_definition":
        return _build_function_symbol(
            node, source_bytes, parent_qualifier=parent_qualifier, in_class=in_class
        )
    if node_type == "decorated_definition":
        return _build_decorated_symbol(
            node, source_bytes, parent_qualifier=parent_qualifier, in_class=in_class
        )
    if node_type == "expression_statement":
        for grand in node.children:
            if grand.type == "assignment":
                return _build_assignment_symbol(
                    grand, source_bytes, parent_qualifier=parent_qualifier, in_class=in_class
                )
        return None
    if node_type == "assignment":
        return _build_assignment_symbol(
            node, source_bytes, parent_qualifier=parent_qualifier, in_class=in_class
        )
    return None


def _build_class_symbol(
    node: Any, source_bytes: bytes, *, parent_qualifier: str
) -> Optional[OutlineSymbol]:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node, source_bytes)
    if not name:
        return None
    qualified = f"{parent_qualifier}.{name}" if parent_qualifier else name
    detail = ""
    superclasses_node = node.child_by_field_name("superclasses")
    if superclasses_node is not None:
        bases = _extract_bases(superclasses_node, source_bytes)
        if bases:
            detail = "(" + ", ".join(bases) + ")"
    body_node = node.child_by_field_name("body")
    children: tuple[OutlineSymbol, ...] = ()
    if body_node is not None:
        children = _extract_block_symbols(
            body_node, source_bytes, parent_qualifier=qualified, in_class=True
        )
    return OutlineSymbol(
        name=name,
        qualified_name=qualified,
        kind="class",
        line_number=node.start_point[0] + 1,
        end_line_number=node.end_point[0] + 1,
        detail=detail,
        children=children,
    )


def _build_function_symbol(
    node: Any,
    source_bytes: bytes,
    *,
    parent_qualifier: str,
    in_class: bool,
    decorator_kind: Optional[str] = None,
    decorator_detail_prefix: str = "",
) -> Optional[OutlineSymbol]:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node, source_bytes)
    if not name:
        return None
    qualified = f"{parent_qualifier}.{name}" if parent_qualifier else name
    is_async = _function_is_async(node)
    if decorator_kind == "property":
        kind: OutlineKind = "property"
    elif in_class:
        kind = "async_method" if is_async else "method"
    else:
        kind = "async_function" if is_async else "function"
    detail = _build_function_detail(node, source_bytes, prefix=decorator_detail_prefix)
    body_node = node.child_by_field_name("body")
    children: tuple[OutlineSymbol, ...] = ()
    if body_node is not None and kind != "property":
        children = _extract_block_symbols(
            body_node, source_bytes, parent_qualifier=qualified, in_class=False
        )
    return OutlineSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        line_number=node.start_point[0] + 1,
        end_line_number=node.end_point[0] + 1,
        detail=detail,
        children=children,
    )


def _build_decorated_symbol(
    node: Any, source_bytes: bytes, *, parent_qualifier: str, in_class: bool
) -> Optional[OutlineSymbol]:
    decorator_names = [
        _node_text(child, source_bytes)
        for child in node.children
        if child.type == "decorator"
    ]
    inner = node.child_by_field_name("definition")
    if inner is None:
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                inner = child
                break
    if inner is None:
        return None

    decorator_kind: Optional[str] = None
    detail_prefix = ""
    for raw in decorator_names:
        normalized = raw.lstrip("@").strip()
        if normalized == "property" or normalized.endswith(".property"):
            decorator_kind = "property"
        elif normalized == "staticmethod":
            detail_prefix = "static "
        elif normalized == "classmethod":
            detail_prefix = "class "

    if inner.type == "function_definition":
        symbol = _build_function_symbol(
            inner,
            source_bytes,
            parent_qualifier=parent_qualifier,
            in_class=in_class,
            decorator_kind=decorator_kind,
            decorator_detail_prefix=detail_prefix,
        )
        if symbol is None:
            return None
        return OutlineSymbol(
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            line_number=node.start_point[0] + 1,
            end_line_number=symbol.end_line_number,
            detail=symbol.detail,
            children=symbol.children,
        )
    if inner.type == "class_definition":
        symbol = _build_class_symbol(
            inner, source_bytes, parent_qualifier=parent_qualifier
        )
        if symbol is None:
            return None
        return OutlineSymbol(
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            line_number=node.start_point[0] + 1,
            end_line_number=symbol.end_line_number,
            detail=symbol.detail,
            children=symbol.children,
        )
    return None


def _build_assignment_symbol(
    node: Any, source_bytes: bytes, *, parent_qualifier: str, in_class: bool
) -> Optional[OutlineSymbol]:
    left = node.child_by_field_name("left")
    if left is None or left.type != "identifier":
        return None
    name = _node_text(left, source_bytes)
    if not name:
        return None
    has_annotation = node.child_by_field_name("type") is not None
    if in_class:
        if not has_annotation:
            return None
        if name == "__slots__":
            return None
        kind: OutlineKind = "field"
    else:
        if not _CONSTANT_NAME_PATTERN.match(name):
            return None
        kind = "constant"
    qualified = f"{parent_qualifier}.{name}" if parent_qualifier else name
    return OutlineSymbol(
        name=name,
        qualified_name=qualified,
        kind=kind,
        line_number=node.start_point[0] + 1,
        end_line_number=node.end_point[0] + 1,
        detail="",
        children=(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node_text(node: Any, source_bytes: bytes) -> str:
    raw = source_bytes[node.start_byte : node.end_byte]
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _function_is_async(node: Any) -> bool:
    for child in node.children:
        if child.type == "async":
            return True
        if child.type == "def":
            return False
    return False


def _build_function_detail(node: Any, source_bytes: bytes, *, prefix: str = "") -> str:
    params_node = node.child_by_field_name("parameters")
    if params_node is None:
        params = "()"
    else:
        params = _node_text(params_node, source_bytes)
        params = " ".join(params.split())
    detail = f"{prefix}{params}".strip()
    if len(detail) > _DETAIL_MAX_CHARS:
        detail = detail[: _DETAIL_MAX_CHARS - 1] + "..."
    return detail


def _extract_bases(superclasses_node: Any, source_bytes: bytes) -> list[str]:
    bases: list[str] = []
    for child in superclasses_node.children:
        if child.type in ("(", ")", ",", "ERROR"):
            continue
        text = _node_text(child, source_bytes).strip()
        if text and text not in ("(", ")", ","):
            bases.append(text)
    return bases


def _node_is_property_setter_or_deleter(node: Any, source_bytes: bytes) -> bool:
    if node.type != "decorated_definition":
        return False
    for child in node.children:
        if child.type != "decorator":
            continue
        text = _node_text(child, source_bytes).lstrip("@").strip()
        if text.endswith(".setter") or text.endswith(".deleter"):
            return True
    return False


# ---------------------------------------------------------------------------
# AST fallback (used only when tree-sitter runtime is unavailable)
# ---------------------------------------------------------------------------


def _build_outline_with_ast(source: str) -> tuple[OutlineSymbol, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    symbols: list[OutlineSymbol] = []
    for node in tree.body:
        symbol = _ast_symbol_for_node(node, parent_qualifier="", in_class=False)
        if symbol is not None:
            symbols.append(symbol)
    return tuple(symbols)


def _ast_symbol_for_node(
    node: ast.stmt, *, parent_qualifier: str, in_class: bool
) -> Optional[OutlineSymbol]:
    if isinstance(node, ast.ClassDef):
        qualified = f"{parent_qualifier}.{node.name}" if parent_qualifier else node.name
        children: list[OutlineSymbol] = []
        for child in node.body:
            child_symbol = _ast_symbol_for_node(child, parent_qualifier=qualified, in_class=True)
            if child_symbol is not None:
                children.append(child_symbol)
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
        return OutlineSymbol(
            name=node.name,
            qualified_name=qualified,
            kind="class",
            line_number=int(node.lineno),
            end_line_number=int(end_line),
            children=tuple(children),
        )
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        qualified = f"{parent_qualifier}.{node.name}" if parent_qualifier else node.name
        is_async = isinstance(node, ast.AsyncFunctionDef)
        if in_class:
            kind: OutlineKind = "async_method" if is_async else "method"
        else:
            kind = "async_function" if is_async else "function"
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
        return OutlineSymbol(
            name=node.name,
            qualified_name=qualified,
            kind=kind,
            line_number=int(node.lineno),
            end_line_number=int(end_line),
            children=(),
        )
    if isinstance(node, ast.Assign) and not in_class:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if _CONSTANT_NAME_PATTERN.match(name):
                end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
                return OutlineSymbol(
                    name=name,
                    qualified_name=name if not parent_qualifier else f"{parent_qualifier}.{name}",
                    kind="constant",
                    line_number=int(node.lineno),
                    end_line_number=int(end_line),
                    children=(),
                )
    return None
