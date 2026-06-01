"""Whitelisted trusted-runtime introspection owned by the REPL runner process."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import inspect
import logging
from typing import Any

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.intelligence.trusted_runtime_whitelist import is_whitelisted_target_path

_logger = logging.getLogger(__name__)

REPL_INTROSPECTION_DEGRADATION_IMPORT_FAILED = "repl_introspection_import_failed"


@dataclass(frozen=True)
class ReplIntrospectionRequest:
    """Request to list members of a whitelisted runtime target."""

    target_path: str
    member_prefix: str = ""
    include_private: bool = True
    max_results: int = 100


class ReplIntrospectionService:
    """Import whitelisted modules/classes and expose members for editor completion."""

    def introspect(self, request: ReplIntrospectionRequest) -> CompletionEnvelope:
        target_path = str(request.target_path or "").strip()
        if not target_path or not is_whitelisted_target_path(target_path):
            return CompletionEnvelope(
                items=[],
                degradation_reason="repl_introspection_not_whitelisted",
            )
        try:
            target = resolve_whitelisted_target(target_path)
        except Exception as exc:
            _logger.debug("REPL introspection import failed for %s: %s", target_path, exc)
            return CompletionEnvelope(
                items=[],
                degradation_reason=REPL_INTROSPECTION_DEGRADATION_IMPORT_FAILED,
            )

        names = _member_names(target, include_private=request.include_private)
        prefix = request.member_prefix or ""
        items: list[CompletionItem] = []
        for name in names:
            if prefix and not name.lower().startswith(prefix.lower()):
                continue
            member_value = _safe_getattr(target, name)
            items.append(_item_from_member(name=name, value=member_value, target_path=target_path))
            if len(items) >= max(1, int(request.max_results)):
                break
        return CompletionEnvelope(
            items=items,
            source="runtime_introspection",
            confidence="runtime_inspection",
        )


def resolve_whitelisted_target(target_path: str) -> Any:
    """Import or navigate to a whitelisted runtime target."""

    if not is_whitelisted_target_path(target_path):
        raise ValueError(f"Target is not whitelisted: {target_path}")

    parts = target_path.split(".")
    try:
        return importlib.import_module(target_path)
    except ImportError:
        pass

    root_name = parts[0]
    root = importlib.import_module(root_name)
    if len(parts) == 1:
        return root

    current: Any = root
    for part in parts[1:]:
        current = getattr(current, part)
    return current


def _member_names(target: Any, *, include_private: bool) -> list[str]:
    try:
        names = dir(target)
    except Exception:
        return []
    filtered: list[str] = []
    for name in names:
        if name.startswith("__"):
            continue
        if not include_private and name.startswith("_"):
            continue
        filtered.append(name)
    return sorted(filtered)


def _safe_getattr(target: Any, name: str) -> Any:
    try:
        return getattr(target, name)
    except Exception:
        return None


def _item_from_member(*, name: str, value: Any, target_path: str) -> CompletionItem:
    signature = _safe_signature(value)
    documentation = _safe_doc(value)
    return CompletionItem(
        label=name,
        insert_text=name,
        kind=_kind_from_value(value),
        detail=f"{target_path} member",
        documentation=documentation,
        signature=signature,
        engine="runtime_introspection",
        source="runtime_introspection",
        confidence="runtime_inspection",
        side_effect_risk="possible_descriptor_or_getattr",
        resolve_provider="runtime_introspection",
    )


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
