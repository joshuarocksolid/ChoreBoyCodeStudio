"""Semantic token extraction helpers for editor overlays."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import re

TOKEN_FUNCTION = "function"
TOKEN_CLASS = "class"
TOKEN_PARAMETER = "parameter"
TOKEN_IMPORT = "import"

_NAME_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


@dataclass(frozen=True)
class SemanticTokenSpan:
    """One semantic token span in absolute document coordinates."""

    start: int
    end: int
    token_type: str


def build_python_semantic_spans(source_text: str) -> list[SemanticTokenSpan]:
    """Return semantic spans for Python declarations/import bindings."""
    syntax_tree = _parse_source_with_recovery(source_text)
    if syntax_tree is None:
        return []

    lines = source_text.splitlines()
    line_starts = _line_start_offsets(source_text)
    spans: list[SemanticTokenSpan] = []
    seen: set[tuple[int, int, str]] = set()

    def add_span(start: int | None, end: int | None, token_type: str) -> None:
        if start is None or end is None or end <= start:
            return
        key = (start, end, token_type)
        if key in seen:
            return
        seen.add(key)
        spans.append(SemanticTokenSpan(start=start, end=end, token_type=token_type))

    for node in ast.walk(syntax_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start, end = _named_node_span(node_name=node.name, node=node, lines=lines, line_starts=line_starts)
            add_span(start, end, TOKEN_FUNCTION)
            for arg in _all_arguments(node.args):
                arg_start = _absolute_offset(line_starts=line_starts, line_number=int(arg.lineno), column=int(arg.col_offset))
                add_span(arg_start, None if arg_start is None else arg_start + len(arg.arg), TOKEN_PARAMETER)
            continue

        if isinstance(node, ast.ClassDef):
            start, end = _named_node_span(node_name=node.name, node=node, lines=lines, line_starts=line_starts)
            add_span(start, end, TOKEN_CLASS)
            continue

        if isinstance(node, ast.Import):
            for alias in node.names:
                start, end = _import_alias_span(alias=alias, lines=lines, line_starts=line_starts)
                add_span(start, end, TOKEN_IMPORT)
            continue

        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                start, end = _import_alias_span(alias=alias, lines=lines, line_starts=line_starts)
                add_span(start, end, TOKEN_IMPORT)
            continue

    spans.sort(key=lambda span: (span.start, span.end, span.token_type))
    return spans


def _all_arguments(arguments: ast.arguments) -> list[ast.arg]:
    result: list[ast.arg] = list(arguments.args)
    result.extend(arguments.kwonlyargs)
    if arguments.vararg is not None:
        result.append(arguments.vararg)
    if arguments.kwarg is not None:
        result.append(arguments.kwarg)
    return result


def _named_node_span(
    *,
    node_name: str,
    node: ast.AST,
    lines: list[str],
    line_starts: list[int],
) -> tuple[int | None, int | None]:
    line_number = int(getattr(node, "lineno", 0))
    if line_number <= 0 or line_number > len(lines):
        return (None, None)
    line_text = lines[line_number - 1]
    search_start = int(getattr(node, "col_offset", 0))
    name_pattern = re.compile(rf"\b{re.escape(node_name)}\b")
    relative_match = name_pattern.search(line_text, search_start)
    if relative_match is None:
        relative_match = name_pattern.search(line_text)
    if relative_match is None:
        return (None, None)
    absolute_start = line_starts[line_number - 1] + relative_match.start()
    absolute_end = line_starts[line_number - 1] + relative_match.end()
    return (absolute_start, absolute_end)


def _import_alias_span(
    *,
    alias: ast.alias,
    lines: list[str],
    line_starts: list[int],
) -> tuple[int | None, int | None]:
    line_number = int(getattr(alias, "lineno", 0))
    if line_number <= 0 or line_number > len(lines):
        return (None, None)
    line_text = lines[line_number - 1]
    search_column = int(getattr(alias, "col_offset", 0))
    target_name = (alias.asname or alias.name.split(".")[0]).strip()
    if not target_name:
        return (None, None)
    match = _NAME_PATTERN.search(line_text, search_column)
    while match is not None:
        candidate = match.group(0)
        if candidate == target_name:
            start = line_starts[line_number - 1] + match.start()
            end = line_starts[line_number - 1] + match.end()
            return (start, end)
        match = _NAME_PATTERN.search(line_text, match.end())
    fallback_start = _absolute_offset(line_starts=line_starts, line_number=line_number, column=search_column)
    if fallback_start is None:
        return (None, None)
    fallback_name = alias.name.split(".")[0]
    return (fallback_start, fallback_start + len(fallback_name))


def _absolute_offset(*, line_starts: list[int], line_number: int, column: int) -> int | None:
    if line_number <= 0 or line_number > len(line_starts):
        return None
    return line_starts[line_number - 1] + max(0, column)


def _line_start_offsets(source_text: str) -> list[int]:
    offsets: list[int] = []
    running = 0
    for line in source_text.splitlines(keepends=True):
        offsets.append(running)
        running += len(line)
    if not offsets:
        offsets.append(0)
    return offsets


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
