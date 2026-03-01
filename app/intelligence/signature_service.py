"""Signature-help parsing and resolution helpers."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
import inspect


@dataclass(frozen=True)
class CallContext:
    """Callable context for cursor position inside a function call."""

    callable_name: str
    argument_index: int


@dataclass(frozen=True)
class SignatureHelp:
    """Resolved signature metadata for one callable context."""

    callable_name: str
    signature_text: str
    argument_index: int
    doc_summary: str = ""
    source: str = "project"


def parse_call_context(source_text: str, cursor_position: int) -> CallContext | None:
    """Parse innermost active call context at cursor position."""
    safe_cursor = max(0, min(cursor_position, len(source_text)))
    if safe_cursor == 0:
        return None

    opening_parenthesis = _find_active_call_open_paren(source_text, safe_cursor)
    if opening_parenthesis is None:
        return None

    callable_name = _extract_callable_name(source_text, opening_parenthesis)
    if not callable_name:
        return None

    argument_index = _count_top_level_arguments(source_text, opening_parenthesis + 1, safe_cursor)
    return CallContext(callable_name=callable_name, argument_index=argument_index)


def resolve_signature_help(source_text: str, cursor_position: int) -> SignatureHelp | None:
    """Resolve signature-help data for cursor context."""
    context = parse_call_context(source_text, cursor_position)
    if context is None:
        return None

    symbol_name = context.callable_name.split(".")[-1]
    project_signatures = _extract_signatures_from_source(source_text)
    signature = project_signatures.get(symbol_name)
    if signature is not None:
        return SignatureHelp(
            callable_name=context.callable_name,
            signature_text=signature,
            argument_index=context.argument_index,
            doc_summary=_extract_doc_summary_from_source(source_text, symbol_name),
            source="project",
        )

    builtin_signature = _resolve_builtin_signature(symbol_name)
    if builtin_signature is not None:
        return SignatureHelp(
            callable_name=context.callable_name,
            signature_text=builtin_signature,
            argument_index=context.argument_index,
            doc_summary=_resolve_builtin_doc_summary(symbol_name),
            source="builtin",
        )
    return None


def _find_active_call_open_paren(source_text: str, cursor_position: int) -> int | None:
    depth = 0
    for index in range(cursor_position - 1, -1, -1):
        character = source_text[index]
        if character == ")":
            depth += 1
            continue
        if character == "(":
            if depth == 0:
                return index
            depth -= 1
    return None


def _extract_callable_name(source_text: str, open_paren_index: int) -> str:
    index = open_paren_index - 1
    while index >= 0 and source_text[index].isspace():
        index -= 1
    end = index + 1
    while index >= 0 and (source_text[index].isalnum() or source_text[index] in {"_", "."}):
        index -= 1
    return source_text[index + 1 : end].strip()


def _count_top_level_arguments(source_text: str, start: int, end: int) -> int:
    depth = 0
    count = 0
    for index in range(start, end):
        character = source_text[index]
        if character == "(":
            depth += 1
            continue
        if character == ")":
            if depth > 0:
                depth -= 1
            continue
        if character == "," and depth == 0:
            count += 1
    return count


def _extract_signatures_from_source(source_text: str) -> dict[str, str]:
    syntax_tree = _parse_source_with_recovery(source_text)
    if syntax_tree is None:
        return {}

    signatures: dict[str, str] = {}
    for node in ast.walk(syntax_tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        signatures[node.name] = f"{node.name}({_format_arguments(node.args)})"
    return signatures


def _extract_doc_summary_from_source(source_text: str, function_name: str) -> str:
    syntax_tree = _parse_source_with_recovery(source_text)
    if syntax_tree is None:
        return ""
    for node in ast.walk(syntax_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            doc = ast.get_docstring(node) or ""
            if not doc:
                return ""
            return doc.strip().splitlines()[0]
    return ""


def _format_arguments(arguments: ast.arguments) -> str:
    rendered: list[str] = []
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)

    for argument, default in zip(positional, defaults):
        rendered.append(_render_argument(argument.arg, default))

    if arguments.vararg is not None:
        rendered.append(f"*{arguments.vararg.arg}")
    elif arguments.kwonlyargs:
        rendered.append("*")

    kw_defaults = list(arguments.kw_defaults)
    for argument, default in zip(arguments.kwonlyargs, kw_defaults):
        rendered.append(_render_argument(argument.arg, default))

    if arguments.kwarg is not None:
        rendered.append(f"**{arguments.kwarg.arg}")

    return ", ".join(rendered)


def _render_argument(name: str, default: ast.AST | None) -> str:
    if default is None:
        return name
    rendered_default = _safe_unparse(default)
    return f"{name}={rendered_default}"


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive fallback
        return "..."


def _resolve_builtin_signature(symbol_name: str) -> str | None:
    candidate = getattr(builtins, symbol_name, None)
    if candidate is None or not callable(candidate):
        return None
    try:
        signature = inspect.signature(candidate)
    except (TypeError, ValueError):
        return f"{symbol_name}(...)"
    return f"{symbol_name}{signature}"


def _resolve_builtin_doc_summary(symbol_name: str) -> str:
    candidate = getattr(builtins, symbol_name, None)
    if candidate is None:
        return ""
    doc = inspect.getdoc(candidate) or ""
    if not doc:
        return ""
    return doc.strip().splitlines()[0]


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
