"""Live Python Console completion service owned by the runner process."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
import inspect
import keyword
import logging
import re
import threading
import time
from typing import Any

from app.intelligence.api_index import provide_api_index_member_items
from app.intelligence.completion_context import CompletionContext, CompletionSyntacticContext, build_completion_context
from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.intelligence.completion_providers import extract_completion_prefix
from app.intelligence.runtime_introspection import attach_replacement_metadata, resolve_runtime_introspection_query
from app.runner.repl_introspection import (
    REPL_RUNTIME_DEGRADATION_EXCEPTIONS,
    ReplIntrospectionRequest,
    ReplIntrospectionService,
    is_whitelisted_target_path,
    resolve_whitelisted_target,
)

_logger = logging.getLogger(__name__)

REPL_COMPLETION_DEGRADATION_JEDI_UNAVAILABLE = "repl_jedi_unavailable"
REPL_COMPLETION_DEGRADATION_NO_COMPLETIONS = "repl_no_completions"
REPL_COMPLETION_DEGRADATION_RUNTIME_INSPECTION = "repl_runtime_inspection"

_PYTHON_CONSOLE_FILE_PATH = "<python_console>"

_DOTTED_EXPR_PATTERN = re.compile(
    r"(?P<expr>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\.(?P<prefix>[A-Za-z_][A-Za-z0-9_]*)?$"
)


@dataclass(frozen=True)
class ReplCompletionRequest:
    """Completion request from the editor-side Python Console widget."""

    line_buffer: str
    cursor_offset: int
    trigger_kind: str = "invoked"
    trigger_character: str = ""
    max_results: int = 100


class ReplCompletionService:
    """Resolve completions against the live InteractiveConsole namespace."""

    def __init__(
        self,
        namespace: dict[str, Any],
        *,
        namespace_lock: threading.RLock | None = None,
        introspection_service: ReplIntrospectionService | None = None,
    ) -> None:
        self._namespace = namespace
        self._namespace_lock = namespace_lock or threading.RLock()
        self._introspection_service = introspection_service or ReplIntrospectionService()

    def complete(self, request: ReplCompletionRequest) -> CompletionEnvelope:
        """Return completion candidates for a live REPL line buffer."""

        started_at = time.perf_counter()

        static_items = self._complete_with_static_index(request)
        if static_items:
            return self._envelope_for_items(
                items=static_items,
                source="static_api_index",
                confidence="static",
                started_at=started_at,
            )

        live_items = self._complete_with_fallback(request)
        if live_items:
            return self._envelope_for_items(
                items=live_items,
                source="runtime",
                confidence="runtime_inspection",
                degradation_reason=REPL_COMPLETION_DEGRADATION_RUNTIME_INSPECTION,
                started_at=started_at,
            )

        jedi_unavailable = False
        try:
            jedi_items = self._complete_with_jedi(request)
        except Exception as exc:
            _logger.debug("REPL Jedi completion failed: %s", exc)
            jedi_items = []
            jedi_unavailable = True
        if jedi_items:
            return CompletionEnvelope(items=jedi_items, source="runtime", confidence="semantic")

        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms > 200.0:
            _logger.warning("Slow REPL completion: elapsed_ms=%.2f count=0", elapsed_ms)
        degradation_reason = REPL_COMPLETION_DEGRADATION_JEDI_UNAVAILABLE if jedi_unavailable else ""
        if request.line_buffer.strip() and not degradation_reason:
            degradation_reason = REPL_COMPLETION_DEGRADATION_NO_COMPLETIONS
        return CompletionEnvelope(
            items=[],
            source="runtime",
            confidence="",
            degradation_reason=degradation_reason,
        )

    def _envelope_for_items(
        self,
        *,
        items: list[CompletionItem],
        source: str,
        confidence: str,
        degradation_reason: str = "",
        started_at: float,
    ) -> CompletionEnvelope:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms > 200.0:
            _logger.warning(
                "Slow REPL completion: elapsed_ms=%.2f count=%s",
                elapsed_ms,
                len(items),
            )
        return CompletionEnvelope(
            items=items,
            source=source,
            confidence=confidence,
            degradation_reason=degradation_reason,
        )

    def _complete_with_static_index(self, request: ReplCompletionRequest) -> list[CompletionItem]:
        cursor = _clamp_cursor(request.line_buffer, request.cursor_offset)
        limit = max(1, int(request.max_results))
        context = build_completion_context(
            source_text=request.line_buffer,
            cursor_position=cursor,
            current_file_path=_PYTHON_CONSOLE_FILE_PATH,
            project_root=None,
            trigger_is_manual=request.trigger_kind in {"manual", "trigger_character"},
            min_prefix_chars=1,
            max_results=limit,
            trigger_kind=request.trigger_kind,
            trigger_character=request.trigger_character,
        )

        if context.syntactic_context in {
            CompletionSyntacticContext.IMPORT_FROM_MEMBER,
            CompletionSyntacticContext.IMPORT_MODULE,
        }:
            indexed_items = provide_api_index_member_items(
                module_name=context.module_name,
                member_prefix=context.prefix,
                limit=limit,
            )
            if indexed_items:
                return attach_replacement_metadata(indexed_items[:limit], context=context)
            target_path = context.trusted_runtime_module or context.module_name
            if is_whitelisted_target_path(target_path):
                return self._introspect_for_context(context, target_path=target_path, limit=limit)

        if context.syntactic_context == CompletionSyntacticContext.DOTTED_MEMBER:
            module_candidates = [
                context.base_expression,
                context.module_name,
                context.base_expression.split(".")[0] if context.base_expression else "",
            ]
            for module_name in module_candidates:
                if not module_name:
                    continue
                indexed_items = provide_api_index_member_items(
                    module_name=module_name,
                    member_prefix=context.prefix,
                    limit=limit,
                )
                if indexed_items:
                    return attach_replacement_metadata(indexed_items[:limit], context=context)
            query = resolve_runtime_introspection_query(context)
            if query is not None:
                return self._introspect_for_context(
                    context,
                    target_path=query.target_path,
                    limit=limit,
                    member_prefix=query.member_prefix,
                )

        return []

    def _complete_with_jedi(self, request: ReplCompletionRequest) -> list[CompletionItem]:
        from app.intelligence.jedi_runtime import initialize_jedi_runtime

        jedi_status = initialize_jedi_runtime()
        if not jedi_status.is_available:
            raise RuntimeError(jedi_status.message)

        import jedi

        cursor = _clamp_cursor(request.line_buffer, request.cursor_offset)
        line, column = _line_column(request.line_buffer, cursor)
        with self._namespace_lock:
            script = jedi.Interpreter(request.line_buffer, [self._namespace])
            completions = list(script.complete(line, column))
        prefix = extract_completion_prefix(request.line_buffer, cursor)
        replacement_start = cursor - len(prefix)
        items: list[CompletionItem] = []
        for completion in completions[: max(1, int(request.max_results))]:
            name = str(getattr(completion, "name", "") or "")
            if not name:
                continue
            completion_type = str(getattr(completion, "type", "symbol"))
            items.append(
                CompletionItem(
                    label=name,
                    insert_text=name,
                    kind=_kind_from_jedi_type(completion_type),
                    detail=f"{completion_type} • live runtime",
                    documentation=_safe_completion_doc(completion),
                    signature=_safe_completion_signature(completion),
                    engine="jedi_interpreter",
                    source="runtime",
                    confidence="semantic",
                    semantic_kind=completion_type,
                    replacement_start=replacement_start,
                    replacement_end=cursor,
                    trigger_kind=request.trigger_kind,
                    trigger_character=request.trigger_character,
                    side_effect_risk="low",
                )
            )
        return items

    def _complete_with_trusted_runtime(self, request: ReplCompletionRequest) -> list[CompletionItem]:
        """Compatibility alias for tests that patch trusted-runtime completion."""

        return self._complete_with_static_index(request)

    def _introspect_for_context(
        self,
        context: CompletionContext,
        *,
        target_path: str,
        limit: int,
        member_prefix: str | None = None,
    ) -> list[CompletionItem]:
        envelope = self._introspection_service.introspect(
            ReplIntrospectionRequest(
                target_path=target_path,
                member_prefix=context.prefix if member_prefix is None else member_prefix,
                max_results=limit,
            )
        )
        items = list(envelope.items or [])
        if not items:
            return []
        return attach_replacement_metadata(items[:limit], context=context)

    def _complete_with_fallback(self, request: ReplCompletionRequest) -> list[CompletionItem]:
        cursor = _clamp_cursor(request.line_buffer, request.cursor_offset)
        snippet = request.line_buffer[:cursor]
        dotted_match = _DOTTED_EXPR_PATTERN.search(snippet)
        if dotted_match is not None:
            prefix = dotted_match.group("prefix") or ""
            expression = dotted_match.group("expr")
            replacement_start = cursor - len(prefix)
            return self._complete_dotted_expression(
                expression=expression,
                prefix=prefix,
                replacement_start=replacement_start,
                replacement_end=cursor,
                request=request,
            )

        prefix = extract_completion_prefix(request.line_buffer, cursor)
        replacement_start = cursor - len(prefix)
        names = sorted({
            *self._namespace.keys(),
            *dir(builtins),
            *keyword.kwlist,
        })
        items: list[CompletionItem] = []
        for name in names:
            if name.startswith("__") or (prefix and not name.lower().startswith(prefix.lower())):
                continue
            value = self._namespace.get(name, getattr(builtins, name, None))
            items.append(
                _item_from_value(
                    name=name,
                    value=value,
                    replacement_start=replacement_start,
                    replacement_end=cursor,
                    request=request,
                    source="runtime",
                    side_effect_risk="none",
                )
            )
            if len(items) >= max(1, int(request.max_results)):
                break
        return items

    def _complete_dotted_expression(
        self,
        *,
        expression: str,
        prefix: str,
        replacement_start: int,
        replacement_end: int,
        request: ReplCompletionRequest,
    ) -> list[CompletionItem]:
        value: Any | None = None
        if is_whitelisted_target_path(expression):
            try:
                value = resolve_whitelisted_target(expression)
            except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
                value = None
        if value is None:
            try:
                with self._namespace_lock:
                    value = eval(expression, {"__builtins__": builtins}, self._namespace)
            except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
                return []
        names: list[str]
        try:
            names = sorted(name for name in dir(value) if not name.startswith("__"))
        except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
            return []
        items: list[CompletionItem] = []
        for name in names:
            if prefix and not name.lower().startswith(prefix.lower()):
                continue
            try:
                member_value = getattr(value, name)
            except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
                member_value = None
            items.append(
                _item_from_value(
                    name=name,
                    value=member_value,
                    replacement_start=replacement_start,
                    replacement_end=replacement_end,
                    request=request,
                    source="runtime_inspection",
                    side_effect_risk="possible_descriptor_or_getattr",
                )
            )
            if len(items) >= max(1, int(request.max_results)):
                break
        return items


def _item_from_value(
    *,
    name: str,
    value: Any,
    replacement_start: int,
    replacement_end: int,
    request: ReplCompletionRequest,
    source: str,
    side_effect_risk: str,
) -> CompletionItem:
    signature = _safe_signature(value)
    return CompletionItem(
        label=name,
        insert_text=name,
        kind=_kind_from_value(value),
        detail="live runtime",
        documentation=_safe_doc(value),
        signature=signature,
        engine="runtime_dir",
        source=source,
        confidence="runtime_inspection",
        replacement_start=replacement_start,
        replacement_end=replacement_end,
        trigger_kind=request.trigger_kind,
        trigger_character=request.trigger_character,
        side_effect_risk=side_effect_risk,
    )


def _kind_from_jedi_type(completion_type: str) -> CompletionKind:
    mapping = {
        "keyword": CompletionKind.KEYWORD,
        "module": CompletionKind.MODULE,
        "function": CompletionKind.FUNCTION,
        "class": CompletionKind.CLASS,
        "property": CompletionKind.PROPERTY,
        "instance": CompletionKind.ATTRIBUTE,
    }
    return mapping.get(completion_type, CompletionKind.SYMBOL)


def _kind_from_value(value: Any) -> CompletionKind:
    if inspect.ismodule(value):
        return CompletionKind.MODULE
    if inspect.isclass(value):
        return CompletionKind.CLASS
    if inspect.ismethod(value):
        return CompletionKind.METHOD
    if inspect.isfunction(value) or inspect.isbuiltin(value):
        return CompletionKind.FUNCTION
    if callable(value):
        return CompletionKind.METHOD
    return CompletionKind.ATTRIBUTE


def _safe_completion_doc(completion: Any) -> str:
    docstring = getattr(completion, "docstring", None)
    if not callable(docstring):
        return ""
    try:
        return str(docstring(raw=False) or "")
    except TypeError:
        try:
            return str(docstring() or "")
        except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
            return ""
    except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
        return ""


def _safe_completion_signature(completion: Any) -> str:
    name_with_symbols = getattr(completion, "name_with_symbols", "")
    if name_with_symbols:
        return str(name_with_symbols)
    description = getattr(completion, "description", "")
    return str(description or "")


def _safe_doc(value: Any) -> str:
    try:
        return inspect.getdoc(value) or ""
    except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
        return ""


def _safe_signature(value: Any) -> str:
    if value is None or not callable(value):
        return ""
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return ""


def _clamp_cursor(text: str, cursor: int) -> int:
    return max(0, min(int(cursor), len(text)))


def _line_column(text: str, cursor: int) -> tuple[int, int]:
    prefix = text[:cursor]
    line = prefix.count("\n") + 1
    last_newline = prefix.rfind("\n")
    column = len(prefix) if last_newline < 0 else len(prefix) - last_newline - 1
    return line, column
