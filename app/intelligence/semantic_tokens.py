"""Semantic token extraction helpers for editor overlays."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import gc
import re

TOKEN_FUNCTION = "function"
TOKEN_METHOD = "method"
TOKEN_CLASS = "class"
TOKEN_PARAMETER = "parameter"
TOKEN_IMPORT = "import"
TOKEN_VARIABLE = "variable"
TOKEN_PROPERTY = "property"
TOKEN_CONSTANT = "constant"

MODIFIER_DECLARATION = "declaration"
MODIFIER_REFERENCE = "reference"
MODIFIER_READONLY = "readonly"
MODIFIER_MODIFICATION = "modification"

PARSE_STATE_OK = "ok"
PARSE_STATE_RECOVERED = "recovered"
PARSE_STATE_FAILED = "failed"
PARSE_STATE_CANCELLED = "cancelled"

_NAME_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

_BINDING_PRIORITY: dict[str, int] = {
    TOKEN_CLASS: 100,
    TOKEN_METHOD: 95,
    TOKEN_FUNCTION: 90,
    TOKEN_IMPORT: 85,
    TOKEN_PARAMETER: 80,
    TOKEN_CONSTANT: 70,
    TOKEN_PROPERTY: 60,
    TOKEN_VARIABLE: 50,
}


@dataclass(frozen=True)
class SemanticTokenSpan:
    """One semantic token span in absolute document coordinates."""

    start: int
    end: int
    token_type: str
    token_modifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticTokenExtractionResult:
    """Semantic extraction payload with parse state metadata."""

    spans: list[SemanticTokenSpan]
    parse_state: str

    @property
    def is_parse_failed(self) -> bool:
        return self.parse_state == PARSE_STATE_FAILED

    @property
    def is_cancelled(self) -> bool:
        return self.parse_state == PARSE_STATE_CANCELLED


@dataclass(frozen=True)
class _SymbolBinding:
    token_type: str
    readonly: bool = False


@dataclass
class _Scope:
    kind: str
    node: ast.AST
    parent: _Scope | None = None
    symbols: dict[str, _SymbolBinding] = field(default_factory=dict)
    children: list[_Scope] = field(default_factory=list)


@dataclass(frozen=True)
class _ParseResult:
    tree: ast.AST | None
    parse_state: str


def build_python_semantic_result(
    source_text: str,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> SemanticTokenExtractionResult:
    """Return semantic spans plus parse-state metadata for Python source."""
    gc_was_enabled = gc.isenabled()
    if gc_was_enabled:
        gc.disable()
    try:
        if should_cancel is not None and should_cancel():
            return SemanticTokenExtractionResult(spans=[], parse_state=PARSE_STATE_CANCELLED)

        parse_result = _parse_source_with_recovery(source_text, should_cancel=should_cancel)
        if parse_result.tree is None:
            return SemanticTokenExtractionResult(spans=[], parse_state=parse_result.parse_state)

        lines = source_text.splitlines()
        line_starts = _line_start_offsets(source_text)

        root_scope = _Scope(kind="module", node=parse_result.tree)
        definition_collector = _DefinitionCollector(root_scope=root_scope, should_cancel=should_cancel)
        definition_collector.visit(parse_result.tree)
        if definition_collector.cancelled:
            return SemanticTokenExtractionResult(spans=[], parse_state=PARSE_STATE_CANCELLED)

        span_collector = _SemanticTokenCollector(
            lines=lines,
            line_starts=line_starts,
            should_cancel=should_cancel,
            root_scope=root_scope,
            scope_by_node_id=definition_collector.scope_by_node_id,
        )
        span_collector.visit(parse_result.tree)
        if span_collector.cancelled:
            return SemanticTokenExtractionResult(spans=[], parse_state=PARSE_STATE_CANCELLED)
        return SemanticTokenExtractionResult(spans=span_collector.sorted_spans(), parse_state=parse_result.parse_state)
    finally:
        if gc_was_enabled:
            gc.enable()


def build_python_semantic_spans(
    source_text: str,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> list[SemanticTokenSpan]:
    """Return semantic spans for Python declarations/import bindings and references."""
    return build_python_semantic_result(source_text, should_cancel=should_cancel).spans


def _all_arguments(arguments: ast.arguments) -> list[ast.arg]:
    result: list[ast.arg] = list(arguments.posonlyargs)
    result.extend(arguments.args)
    result.extend(arguments.kwonlyargs)
    if arguments.vararg is not None:
        result.append(arguments.vararg)
    if arguments.kwarg is not None:
        result.append(arguments.kwarg)
    return result


def _iter_function_signature_expressions(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterable[ast.AST]:
    for arg in _all_arguments(node.args):
        if arg.annotation is not None:
            yield arg.annotation
    for default in node.args.defaults:
        yield default
    for default in node.args.kw_defaults:
        if default is not None:
            yield default
    if node.returns is not None:
        yield node.returns


def _looks_like_constant(name: str) -> bool:
    return bool(name) and name.upper() == name and any(ch.isalpha() for ch in name)


def _annotation_contains_final(annotation: ast.AST | None) -> bool:
    if annotation is None:
        return False
    if isinstance(annotation, ast.Name):
        return annotation.id == "Final"
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "Final"
    if isinstance(annotation, ast.Subscript):
        return _annotation_contains_final(annotation.value)
    if isinstance(annotation, ast.Tuple):
        return any(_annotation_contains_final(elt) for elt in annotation.elts)
    return False


def _merge_bindings(existing: _SymbolBinding, incoming: _SymbolBinding) -> _SymbolBinding:
    existing_priority = _BINDING_PRIORITY.get(existing.token_type, 0)
    incoming_priority = _BINDING_PRIORITY.get(incoming.token_type, 0)
    selected = incoming if incoming_priority > existing_priority else existing
    readonly = existing.readonly or incoming.readonly
    return _SymbolBinding(token_type=selected.token_type, readonly=readonly)


def _bind_symbol(scope: _Scope, name: str, binding: _SymbolBinding) -> None:
    if not name:
        return
    existing = scope.symbols.get(name)
    if existing is None:
        scope.symbols[name] = binding
        return
    scope.symbols[name] = _merge_bindings(existing, binding)


class _DefinitionCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        root_scope: _Scope,
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        self._should_cancel = should_cancel
        self._visit_count = 0
        self.cancelled = False
        self.scope_by_node_id: dict[int, _Scope] = {id(root_scope.node): root_scope}
        self._scope_stack: list[_Scope] = [root_scope]

    def visit(self, node: ast.AST) -> None:  # type: ignore[override]
        if self.cancelled:
            return
        self._visit_count += 1
        if self._visit_count % 64 == 0 and self._should_cancel is not None and self._should_cancel():
            self.cancelled = True
            return
        super().visit(node)

    def _current_scope(self) -> _Scope:
        return self._scope_stack[-1]

    def _push_scope(self, node: ast.AST, *, kind: str) -> _Scope:
        parent = self._current_scope()
        child = _Scope(kind=kind, node=node, parent=parent)
        parent.children.append(child)
        self.scope_by_node_id[id(node)] = child
        self._scope_stack.append(child)
        return child

    def _pop_scope(self) -> None:
        if len(self._scope_stack) > 1:
            self._scope_stack.pop()

    def _infer_assignment_binding(self, *, name: str, readonly_hint: bool = False) -> _SymbolBinding:
        current_scope = self._current_scope()
        if current_scope.kind == "class":
            if readonly_hint or _looks_like_constant(name):
                return _SymbolBinding(token_type=TOKEN_CONSTANT, readonly=True)
            return _SymbolBinding(token_type=TOKEN_PROPERTY)
        if current_scope.kind == "module":
            if readonly_hint or _looks_like_constant(name):
                return _SymbolBinding(token_type=TOKEN_CONSTANT, readonly=True)
            return _SymbolBinding(token_type=TOKEN_VARIABLE)
        return _SymbolBinding(token_type=TOKEN_VARIABLE, readonly=readonly_hint)

    def _register_assignment_target(self, target: ast.AST, *, readonly_hint: bool = False) -> None:
        if isinstance(target, ast.Name):
            _bind_symbol(
                self._current_scope(),
                target.id,
                self._infer_assignment_binding(name=target.id, readonly_hint=readonly_hint),
            )
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._register_assignment_target(element, readonly_hint=readonly_hint)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        _bind_symbol(self._current_scope(), node.name, _SymbolBinding(token_type=TOKEN_CLASS, readonly=True))
        self._push_scope(node, kind="class")
        for statement in node.body:
            self.visit(statement)
        self._pop_scope()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_function_like(node)

    def _visit_function_like(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        parent_scope = self._current_scope()
        token_type = TOKEN_METHOD if parent_scope.kind == "class" else TOKEN_FUNCTION
        _bind_symbol(parent_scope, node.name, _SymbolBinding(token_type=token_type, readonly=True))

        self._push_scope(node, kind="function")
        for arg in _all_arguments(node.args):
            _bind_symbol(self._current_scope(), arg.arg, _SymbolBinding(token_type=TOKEN_PARAMETER))
        for statement in node.body:
            self.visit(statement)
        self._pop_scope()

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._push_scope(node, kind="lambda")
        for arg in _all_arguments(node.args):
            _bind_symbol(self._current_scope(), arg.arg, _SymbolBinding(token_type=TOKEN_PARAMETER))
        self._pop_scope()

    def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node, node.generators)

    def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node, node.generators)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node, node.generators)

    def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node, node.generators)

    def _visit_comprehension(self, owner: ast.AST, generators: list[ast.comprehension]) -> None:
        self._push_scope(owner, kind="comprehension")
        for generator in generators:
            self._register_assignment_target(generator.target)
        self._pop_scope()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast.NodeVisitor API
        for alias in node.names:
            bound_name = (alias.asname or alias.name.split(".")[0]).strip()
            if not bound_name:
                continue
            _bind_symbol(self._current_scope(), bound_name, _SymbolBinding(token_type=TOKEN_IMPORT, readonly=True))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast.NodeVisitor API
        for alias in node.names:
            if alias.name == "*":
                continue
            bound_name = (alias.asname or alias.name).strip()
            if not bound_name:
                continue
            _bind_symbol(self._current_scope(), bound_name, _SymbolBinding(token_type=TOKEN_IMPORT, readonly=True))

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast.NodeVisitor API
        for target in node.targets:
            self._register_assignment_target(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._register_assignment_target(node.target, readonly_hint=_annotation_contains_final(node.annotation))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._register_assignment_target(node.target)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._register_assignment_target(node.target)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._register_assignment_target(node.target)
        for statement in node.body:
            self.visit(statement)
        for statement in node.orelse:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802 - ast.NodeVisitor API
        self.visit_For(node)

    def visit_With(self, node: ast.With) -> None:  # noqa: N802 - ast.NodeVisitor API
        for item in node.items:
            if item.optional_vars is not None:
                self._register_assignment_target(item.optional_vars)
        for statement in node.body:
            self.visit(statement)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802 - ast.NodeVisitor API
        self.visit_With(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802 - ast.NodeVisitor API
        if isinstance(node.name, str) and node.name:
            _bind_symbol(self._current_scope(), node.name, _SymbolBinding(token_type=TOKEN_VARIABLE))
        for statement in node.body:
            self.visit(statement)


class _SemanticTokenCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        lines: list[str],
        line_starts: list[int],
        should_cancel: Callable[[], bool] | None,
        root_scope: _Scope,
        scope_by_node_id: dict[int, _Scope],
    ) -> None:
        self._lines = lines
        self._line_starts = line_starts
        self._should_cancel = should_cancel
        self._visit_count = 0
        self.cancelled = False
        self._scope_by_node_id = scope_by_node_id
        self._scope_stack: list[_Scope] = [root_scope]
        self._spans: list[SemanticTokenSpan] = []
        self._seen: set[tuple[int, int, str, tuple[str, ...]]] = set()

    def sorted_spans(self) -> list[SemanticTokenSpan]:
        return sorted(self._spans, key=lambda span: (span.start, span.end, span.token_type, span.token_modifiers))

    def visit(self, node: ast.AST) -> None:  # type: ignore[override]
        if self.cancelled:
            return
        self._visit_count += 1
        if self._visit_count % 64 == 0 and self._should_cancel is not None and self._should_cancel():
            self.cancelled = True
            return
        super().visit(node)

    def _current_scope(self) -> _Scope:
        return self._scope_stack[-1]

    def _push_scope_for_node(self, node: ast.AST) -> bool:
        mapped_scope = self._scope_by_node_id.get(id(node))
        if mapped_scope is None or mapped_scope is self._current_scope():
            return False
        self._scope_stack.append(mapped_scope)
        return True

    def _pop_scope_if_needed(self, pushed: bool) -> None:
        if pushed and len(self._scope_stack) > 1:
            self._scope_stack.pop()

    def _resolve_binding(self, name: str) -> _SymbolBinding | None:
        for scope in reversed(self._scope_stack):
            binding = scope.symbols.get(name)
            if binding is not None:
                return binding
        return None

    def _binding_for_assignment_target(self, name: str) -> _SymbolBinding:
        local_binding = self._current_scope().symbols.get(name)
        if local_binding is not None:
            return local_binding
        return _SymbolBinding(token_type=TOKEN_VARIABLE)

    def _add_span(
        self,
        start: int | None,
        end: int | None,
        token_type: str,
        modifiers: Iterable[str] = (),
    ) -> None:
        if start is None or end is None or end <= start:
            return
        normalized_modifiers = tuple(sorted({value for value in modifiers if value}))
        key = (start, end, token_type, normalized_modifiers)
        if key in self._seen:
            return
        self._seen.add(key)
        self._spans.append(
            SemanticTokenSpan(
                start=start,
                end=end,
                token_type=token_type,
                token_modifiers=normalized_modifiers,
            )
        )

    def _name_span(self, node: ast.Name) -> tuple[int | None, int | None]:
        start = _absolute_offset(
            line_starts=self._line_starts,
            line_number=int(node.lineno),
            column=int(node.col_offset),
        )
        end = None if start is None else start + len(node.id)
        return (start, end)

    def _emit_name_reference(self, node: ast.Name) -> None:
        binding = self._resolve_binding(node.id)
        if binding is None:
            return
        modifiers: list[str] = [MODIFIER_REFERENCE]
        if binding.readonly:
            modifiers.append(MODIFIER_READONLY)
        start, end = self._name_span(node)
        self._add_span(start, end, binding.token_type, modifiers)

    def _emit_assignment_target(
        self,
        target: ast.AST,
        *,
        declaration: bool,
        modification: bool = False,
    ) -> None:
        modifiers: list[str] = []
        if declaration:
            modifiers.append(MODIFIER_DECLARATION)
        if modification:
            modifiers.append(MODIFIER_MODIFICATION)

        if isinstance(target, ast.Name):
            binding = self._binding_for_assignment_target(target.id)
            name_start, name_end = self._name_span(target)
            if binding.readonly:
                modifiers.append(MODIFIER_READONLY)
            self._add_span(name_start, name_end, binding.token_type, modifiers)
            return

        if isinstance(target, ast.Attribute):
            token_type = TOKEN_CONSTANT if _looks_like_constant(target.attr) else TOKEN_PROPERTY
            local_modifiers = list(modifiers)
            if token_type == TOKEN_CONSTANT:
                local_modifiers.append(MODIFIER_READONLY)
            start, end = _attribute_name_span(node=target, lines=self._lines, line_starts=self._line_starts)
            self._add_span(start, end, token_type, local_modifiers)
            self.visit(target.value)
            return

        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._emit_assignment_target(element, declaration=declaration, modification=modification)

    def _emit_target_reference(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self._emit_name_reference(target)
            return
        if isinstance(target, ast.Attribute):
            token_type = TOKEN_CONSTANT if _looks_like_constant(target.attr) else TOKEN_PROPERTY
            modifiers = [MODIFIER_REFERENCE]
            if token_type == TOKEN_CONSTANT:
                modifiers.append(MODIFIER_READONLY)
            start, end = _attribute_name_span(node=target, lines=self._lines, line_starts=self._line_starts)
            self._add_span(start, end, token_type, modifiers)
            self.visit(target.value)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._emit_target_reference(element)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        start, end = _named_node_span(
            node_name=node.name,
            node=node,
            lines=self._lines,
            line_starts=self._line_starts,
        )
        self._add_span(start, end, TOKEN_CLASS, [MODIFIER_DECLARATION, MODIFIER_READONLY])

        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

        pushed = self._push_scope_for_node(node)
        for statement in node.body:
            self.visit(statement)
        self._pop_scope_if_needed(pushed)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_function_like(node)

    def _visit_function_like(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        token_type = TOKEN_METHOD if self._current_scope().kind == "class" else TOKEN_FUNCTION
        modifiers = [MODIFIER_DECLARATION, MODIFIER_READONLY]
        if isinstance(node, ast.AsyncFunctionDef):
            # Token modifiers keep declaration semantics explicit; async styling can be added by theme later.
            modifiers = [MODIFIER_DECLARATION, MODIFIER_READONLY]
        start, end = _named_node_span(
            node_name=node.name,
            node=node,
            lines=self._lines,
            line_starts=self._line_starts,
        )
        self._add_span(start, end, token_type, modifiers)

        for decorator in node.decorator_list:
            self.visit(decorator)
        for expression in _iter_function_signature_expressions(node):
            self.visit(expression)

        pushed = self._push_scope_for_node(node)
        for arg in _all_arguments(node.args):
            arg_start = _absolute_offset(
                line_starts=self._line_starts,
                line_number=int(arg.lineno),
                column=int(arg.col_offset),
            )
            if arg_start is not None:
                self._add_span(
                    arg_start,
                    arg_start + len(arg.arg),
                    TOKEN_PARAMETER,
                    [MODIFIER_DECLARATION],
                )
        for statement in node.body:
            self.visit(statement)
        self._pop_scope_if_needed(pushed)

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802 - ast.NodeVisitor API
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)
        pushed = self._push_scope_for_node(node)
        for arg in _all_arguments(node.args):
            arg_start = _absolute_offset(
                line_starts=self._line_starts,
                line_number=int(arg.lineno),
                column=int(arg.col_offset),
            )
            if arg_start is not None:
                self._add_span(
                    arg_start,
                    arg_start + len(arg.arg),
                    TOKEN_PARAMETER,
                    [MODIFIER_DECLARATION],
                )
        self.visit(node.body)
        self._pop_scope_if_needed(pushed)

    def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node.generators, trailing_nodes=[node.elt], owner=node)

    def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node.generators, trailing_nodes=[node.elt], owner=node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node.generators, trailing_nodes=[node.elt], owner=node)

    def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._visit_comprehension(node.generators, trailing_nodes=[node.key, node.value], owner=node)

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        *,
        trailing_nodes: list[ast.AST],
        owner: ast.AST,
    ) -> None:
        pushed = self._push_scope_for_node(owner)
        for generator in generators:
            self.visit(generator.iter)
            self._emit_assignment_target(generator.target, declaration=True)
            for if_clause in generator.ifs:
                self.visit(if_clause)
        for expression in trailing_nodes:
            self.visit(expression)
        self._pop_scope_if_needed(pushed)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast.NodeVisitor API
        for alias in node.names:
            start, end = _import_alias_span(alias=alias, lines=self._lines, line_starts=self._line_starts)
            self._add_span(start, end, TOKEN_IMPORT, [MODIFIER_DECLARATION, MODIFIER_READONLY])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast.NodeVisitor API
        for alias in node.names:
            if alias.name == "*":
                continue
            start, end = _import_alias_span(alias=alias, lines=self._lines, line_starts=self._line_starts)
            self._add_span(start, end, TOKEN_IMPORT, [MODIFIER_DECLARATION, MODIFIER_READONLY])

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast.NodeVisitor API
        for target in node.targets:
            self._emit_assignment_target(target, declaration=True)
        if not _is_literal_expression(node.value):
            self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._emit_assignment_target(node.target, declaration=True)
        if not _is_literal_expression(node.annotation):
            self.visit(node.annotation)
        if node.value is not None:
            if not _is_literal_expression(node.value):
                self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._emit_target_reference(node.target)
        self._emit_assignment_target(node.target, declaration=False, modification=True)
        if not _is_literal_expression(node.value):
            self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:  # noqa: N802 - ast.NodeVisitor API
        self._emit_assignment_target(node.target, declaration=True, modification=True)
        if not _is_literal_expression(node.value):
            self.visit(node.value)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802 - ast.NodeVisitor API
        self.visit(node.iter)
        self._emit_assignment_target(node.target, declaration=True, modification=True)
        for statement in node.body:
            self.visit(statement)
        for statement in node.orelse:
            self.visit(statement)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802 - ast.NodeVisitor API
        self.visit_For(node)

    def visit_With(self, node: ast.With) -> None:  # noqa: N802 - ast.NodeVisitor API
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._emit_assignment_target(item.optional_vars, declaration=True)
        for statement in node.body:
            self.visit(statement)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802 - ast.NodeVisitor API
        self.visit_With(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802 - ast.NodeVisitor API
        if node.type is not None:
            self.visit(node.type)
        if isinstance(node.name, str) and node.name:
            start, end = _except_handler_name_span(
                handler=node,
                name=node.name,
                lines=self._lines,
                line_starts=self._line_starts,
            )
            self._add_span(start, end, TOKEN_VARIABLE, [MODIFIER_DECLARATION])
        for statement in node.body:
            self.visit(statement)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast.NodeVisitor API
        if isinstance(node.func, ast.Attribute):
            token_type = TOKEN_CONSTANT if _looks_like_constant(node.func.attr) else TOKEN_METHOD
            modifiers = [MODIFIER_REFERENCE]
            if token_type == TOKEN_CONSTANT:
                modifiers.append(MODIFIER_READONLY)
            start, end = _attribute_name_span(
                node=node.func,
                lines=self._lines,
                line_starts=self._line_starts,
            )
            self._add_span(start, end, token_type, modifiers)
            self.visit(node.func.value)
        else:
            self.visit(node.func)
        for argument in node.args:
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802 - ast.NodeVisitor API
        if not isinstance(node.ctx, ast.Load):
            return
        self._emit_name_reference(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - ast.NodeVisitor API
        self.visit(node.value)
        if not isinstance(node.ctx, ast.Load):
            return
        token_type = TOKEN_CONSTANT if _looks_like_constant(node.attr) else TOKEN_PROPERTY
        modifiers = [MODIFIER_REFERENCE]
        if token_type == TOKEN_CONSTANT:
            modifiers.append(MODIFIER_READONLY)
        start, end = _attribute_name_span(node=node, lines=self._lines, line_starts=self._line_starts)
        self._add_span(start, end, token_type, modifiers)


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


def _except_handler_name_span(
    *,
    handler: ast.ExceptHandler,
    name: str,
    lines: list[str],
    line_starts: list[int],
) -> tuple[int | None, int | None]:
    line_number = int(getattr(handler, "lineno", 0))
    if line_number <= 0 or line_number > len(lines):
        return (None, None)
    line_text = lines[line_number - 1]
    search_start = int(getattr(handler, "col_offset", 0))
    name_pattern = re.compile(rf"\bas\s+{re.escape(name)}\b")
    match = name_pattern.search(line_text, search_start)
    if match is None:
        return (None, None)
    absolute_start = line_starts[line_number - 1] + match.end() - len(name)
    absolute_end = absolute_start + len(name)
    return (absolute_start, absolute_end)


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


def _is_literal_expression(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal_expression(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            key is None or _is_literal_expression(key) for key in node.keys
        ) and all(_is_literal_expression(value) for value in node.values)
    if isinstance(node, ast.UnaryOp):
        return _is_literal_expression(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_literal_expression(node.left) and _is_literal_expression(node.right)
    if isinstance(node, ast.BoolOp):
        return all(_is_literal_expression(value) for value in node.values)
    if isinstance(node, ast.Compare):
        return _is_literal_expression(node.left) and all(_is_literal_expression(comp) for comp in node.comparators)
    if isinstance(node, ast.IfExp):
        return (
            _is_literal_expression(node.test)
            and _is_literal_expression(node.body)
            and _is_literal_expression(node.orelse)
        )
    return False


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
) -> _ParseResult:
    if should_cancel is not None and should_cancel():
        return _ParseResult(tree=None, parse_state=PARSE_STATE_CANCELLED)
    try:
        return _ParseResult(tree=ast.parse(source_text), parse_state=PARSE_STATE_OK)
    except SyntaxError:
        pass

    lines = source_text.splitlines()
    while lines:
        if should_cancel is not None and should_cancel():
            return _ParseResult(tree=None, parse_state=PARSE_STATE_CANCELLED)
        lines.pop()
        candidate = "\n".join(lines).strip()
        if not candidate:
            return _ParseResult(tree=None, parse_state=PARSE_STATE_FAILED)
        try:
            return _ParseResult(tree=ast.parse(candidate + "\n"), parse_state=PARSE_STATE_RECOVERED)
        except SyntaxError:
            continue
    return _ParseResult(tree=None, parse_state=PARSE_STATE_FAILED)
