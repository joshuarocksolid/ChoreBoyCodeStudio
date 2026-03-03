"""Semantic token extraction helpers for editor overlays."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from collections.abc import Callable, Iterable
import re

TOKEN_FUNCTION = "function"
TOKEN_METHOD = "method"
TOKEN_CLASS = "class"
TOKEN_PARAMETER = "parameter"
TOKEN_IMPORT = "import"
TOKEN_VARIABLE = "variable"
TOKEN_PROPERTY = "property"

_NAME_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


@dataclass(frozen=True)
class SemanticTokenSpan:
    """One semantic token span in absolute document coordinates."""

    start: int
    end: int
    token_type: str


def build_python_semantic_spans(
    source_text: str,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> list[SemanticTokenSpan]:
    """Return semantic spans for Python declarations/import bindings and key usages."""
    if should_cancel is not None and should_cancel():
        return []
    syntax_tree = _parse_source_with_recovery(source_text, should_cancel=should_cancel)
    if syntax_tree is None:
        return []

    lines = source_text.splitlines()
    line_starts = _line_start_offsets(source_text)
    collector = _SemanticTokenCollector(
        lines=lines,
        line_starts=line_starts,
        should_cancel=should_cancel,
    )
    collector.visit(syntax_tree)
    if collector.cancelled:
        return []
    return collector.sorted_spans()


def _all_arguments(arguments: ast.arguments) -> list[ast.arg]:
    result: list[ast.arg] = list(arguments.args)
    result.extend(arguments.kwonlyargs)
    if arguments.vararg is not None:
        result.append(arguments.vararg)
    if arguments.kwarg is not None:
        result.append(arguments.kwarg)
    return result


class _SemanticTokenCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        lines: list[str],
        line_starts: list[int],
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        self._lines = lines
        self._line_starts = line_starts
        self._should_cancel = should_cancel
        self._visit_count = 0
        self._class_depth = 0
        self.cancelled = False
        self._spans: list[SemanticTokenSpan] = []
        self._seen: set[tuple[int, int, str]] = set()

    def sorted_spans(self) -> list[SemanticTokenSpan]:
        return sorted(self._spans, key=lambda span: (span.start, span.end, span.token_type))

    def visit(self, node: ast.AST) -> None:  # type: ignore[override]
        if self.cancelled:
            return
        self._visit_count += 1
        if self._visit_count % 64 == 0 and self._should_cancel is not None and self._should_cancel():
            self.cancelled = True
            return
        super().visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        start, end = _named_node_span(
            node_name=node.name,
            node=node,
            lines=self._lines,
            line_starts=self._line_starts,
        )
        self._add_span(start, end, TOKEN_CLASS)
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth = max(0, self._class_depth - 1)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_function_like(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast.NodeVisitor API
        for alias in node.names:
            start, end = _import_alias_span(alias=alias, lines=self._lines, line_starts=self._line_starts)
            self._add_span(start, end, TOKEN_IMPORT)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast.NodeVisitor API
        for alias in node.names:
            if alias.name == "*":
                continue
            start, end = _import_alias_span(alias=alias, lines=self._lines, line_starts=self._line_starts)
            self._add_span(start, end, TOKEN_IMPORT)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_assignment_like(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_assignment_like(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_assignment_like(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_assignment_like(node)

    def _visit_function_like(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        start, end = _named_node_span(
            node_name=node.name,
            node=node,
            lines=self._lines,
            line_starts=self._line_starts,
        )
        token_type = TOKEN_METHOD if self._class_depth > 0 else TOKEN_FUNCTION
        self._add_span(start, end, token_type)
        for arg in _all_arguments(node.args):
            arg_start = _absolute_offset(
                line_starts=self._line_starts,
                line_number=int(arg.lineno),
                column=int(arg.col_offset),
            )
            self._add_span(arg_start, None if arg_start is None else arg_start + len(arg.arg), TOKEN_PARAMETER)
        self.generic_visit(node)

    def _visit_assignment_like(self, node: ast.AST) -> None:
        for target in _iter_assignment_targets(node):
            start, end, token_type = _target_span(
                target=target,
                lines=self._lines,
                line_starts=self._line_starts,
            )
            self._add_span(start, end, token_type)

    def _add_span(self, start: int | None, end: int | None, token_type: str) -> None:
        if start is None or end is None or end <= start:
            return
        key = (start, end, token_type)
        if key in self._seen:
            return
        self._seen.add(key)
        self._spans.append(SemanticTokenSpan(start=start, end=end, token_type=token_type))


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


def _iter_assignment_targets(node: ast.AST) -> Iterable[ast.AST]:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            yield from _expand_assignment_target(target)
    elif isinstance(node, ast.AnnAssign):
        yield from _expand_assignment_target(node.target)
    elif isinstance(node, ast.AugAssign):
        yield from _expand_assignment_target(node.target)
    elif isinstance(node, ast.NamedExpr):
        yield from _expand_assignment_target(node.target)


def _expand_assignment_target(target: ast.AST) -> Iterable[ast.AST]:
    if isinstance(target, (ast.Name, ast.Attribute)):
        yield target
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _expand_assignment_target(element)


def _target_span(
    *,
    target: ast.AST,
    lines: list[str],
    line_starts: list[int],
) -> tuple[int | None, int | None, str]:
    if isinstance(target, ast.Name):
        start = _absolute_offset(
            line_starts=line_starts,
            line_number=int(target.lineno),
            column=int(target.col_offset),
        )
        end = None if start is None else start + len(target.id)
        return (start, end, TOKEN_VARIABLE)
    if isinstance(target, ast.Attribute):
        start, end = _attribute_name_span(node=target, lines=lines, line_starts=line_starts)
        return (start, end, TOKEN_PROPERTY)
    return (None, None, TOKEN_VARIABLE)


def _attribute_name_span(
    *,
    node: ast.Attribute,
    lines: list[str],
    line_starts: list[int],
) -> tuple[int | None, int | None]:
    end_line = int(getattr(node, "end_lineno", 0))
    end_col = int(getattr(node, "end_col_offset", 0))
    if end_line > 0 and end_line <= len(lines) and end_col > 0:
        start_col = max(0, end_col - len(node.attr))
        start = _absolute_offset(line_starts=line_starts, line_number=end_line, column=start_col)
        end = _absolute_offset(line_starts=line_starts, line_number=end_line, column=end_col)
        if start is not None and end is not None and end > start:
            return (start, end)

    line_number = int(getattr(node, "lineno", 0))
    if line_number <= 0 or line_number > len(lines):
        return (None, None)
    line_text = lines[line_number - 1]
    search_start = int(getattr(node, "col_offset", 0))
    match = re.search(rf"\.{re.escape(node.attr)}\b", line_text[search_start:])
    if match is None:
        return (None, None)
    absolute_start = line_starts[line_number - 1] + search_start + match.start() + 1
    absolute_end = absolute_start + len(node.attr)
    return (absolute_start, absolute_end)


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


def _parse_source_with_recovery(
    source_text: str,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> ast.AST | None:
    if should_cancel is not None and should_cancel():
        return None
    try:
        return ast.parse(source_text)
    except SyntaxError:
        pass

    lines = source_text.splitlines()
    while lines:
        if should_cancel is not None and should_cancel():
            return None
        lines.pop()
        candidate = "\n".join(lines).strip()
        if not candidate:
            return None
        try:
            return ast.parse(candidate + "\n")
        except SyntaxError:
            continue
    return None
