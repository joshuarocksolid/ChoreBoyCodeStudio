"""Live Python Console completion service owned by the runner process."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
import inspect
import keyword
import logging
import re
import time
from typing import Any

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.intelligence.completion_providers import extract_completion_prefix

_logger = logging.getLogger(__name__)

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

    def __init__(self, namespace: dict[str, Any]) -> None:
        self._namespace = namespace

    def complete(self, request: ReplCompletionRequest) -> CompletionEnvelope:
        """Return completion candidates for a live REPL line buffer."""

        started_at = time.perf_counter()
        try:
            jedi_items = self._complete_with_jedi(request)
        except Exception as exc:
            _logger.debug("REPL Jedi completion failed: %s", exc)
            jedi_items = []
        if jedi_items:
            return CompletionEnvelope(items=jedi_items, source="runtime", confidence="semantic")

        fallback_items = self._complete_with_fallback(request)
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        if elapsed_ms > 200.0:
            _logger.warning("Slow REPL completion: elapsed_ms=%.2f count=%s", elapsed_ms, len(fallback_items))
        return CompletionEnvelope(
            items=fallback_items,
            source="runtime",
            confidence="runtime_inspection" if fallback_items else "",
        )

    def _complete_with_jedi(self, request: ReplCompletionRequest) -> list[CompletionItem]:
        import jedi

        cursor = _clamp_cursor(request.line_buffer, request.cursor_offset)
        line, column = _line_column(request.line_buffer, cursor)
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
        try:
            value = eval(expression, {"__builtins__": builtins}, self._namespace)
        except Exception:
            return []
        names: list[str]
        try:
            names = sorted(name for name in dir(value) if not name.startswith("_"))
        except Exception:
            return []
        items: list[CompletionItem] = []
        for name in names:
            if prefix and not name.lower().startswith(prefix.lower()):
                continue
            try:
                member_value = getattr(value, name)
            except Exception:
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
        except Exception:
            return ""
    except Exception:
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
    except Exception:
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
