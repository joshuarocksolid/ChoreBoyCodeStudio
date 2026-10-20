"""Whitelisted trusted-runtime introspection owned by the REPL runner process."""

from __future__ import annotations

from dataclasses import dataclass, replace
import importlib
import inspect
import logging
import types
from typing import Any, Optional

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.intelligence.runtime_members import (
    RUNTIME_INTROSPECTION_PROVIDER,
    RuntimeDetailResult,
    RuntimeListingResult,
    RuntimeMember,
    RuntimeMemberDetail,
    RuntimeMemberListing,
    RuntimeMemberRef,
    RuntimeUnavailable,
    first_paragraph,
)
from app.intelligence.trusted_runtime_whitelist import is_whitelisted_target_path

_logger = logging.getLogger(__name__)

REPL_INTROSPECTION_DEGRADATION_NOT_WHITELISTED = "repl_introspection_not_whitelisted"
REPL_INTROSPECTION_DEGRADATION_IMPORT_FAILED = "repl_introspection_import_failed"
REPL_INTROSPECTION_DEGRADATION_MEMBER_FAILED = "repl_introspection_member_failed"

# CC-22: live REPL targets may raise during import, dir(), getattr, or doc lookup.
REPL_RUNTIME_DEGRADATION_EXCEPTIONS = (
    AttributeError,
    ImportError,
    KeyError,
    ModuleNotFoundError,
    NameError,
    OSError,
    RuntimeError,
    SyntaxError,
    TypeError,
    ValueError,
)

_STATIC_KIND_TABLE: tuple[tuple[tuple[type, ...], CompletionKind], ...] = (
    ((types.ModuleType,), CompletionKind.MODULE),
    ((type,), CompletionKind.CLASS),
    ((staticmethod,), CompletionKind.FUNCTION),
    ((property, types.GetSetDescriptorType, types.MemberDescriptorType), CompletionKind.PROPERTY),
    (
        (
            classmethod,
            types.MethodDescriptorType,
            types.WrapperDescriptorType,
            types.ClassMethodDescriptorType,
        ),
        CompletionKind.METHOD,
    ),
)
_PLAIN_CALLABLE_TYPES = (types.FunctionType, types.BuiltinFunctionType)


@dataclass(frozen=True)
class ReplIntrospectionRequest:
    """In-process console request. ``max_results=None`` means uncapped."""

    target_path: str
    member_prefix: str = ""
    max_results: Optional[int] = None


class _TargetUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ReplIntrospectionService:
    def list_members(self, target_path: str) -> RuntimeListingResult:
        try:
            path, target = _load_target(target_path)
        except _TargetUnavailable as exc:
            return RuntimeUnavailable(reason=exc.reason)
        return RuntimeMemberListing.from_members(path, _static_members(target))

    def resolve_member(self, ref: RuntimeMemberRef) -> RuntimeDetailResult:
        try:
            _path, target = _load_target(ref.target_path)
        except _TargetUnavailable as exc:
            return RuntimeUnavailable(reason=exc.reason)
        try:
            value = getattr(target, ref.name)
        except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
            return RuntimeUnavailable(reason=REPL_INTROSPECTION_DEGRADATION_MEMBER_FAILED)
        return RuntimeMemberDetail(
            signature=_safe_signature(value),
            documentation=first_paragraph(_safe_doc(value)),
        )

    def introspect(self, request: ReplIntrospectionRequest) -> CompletionEnvelope:
        listing = self.list_members(request.target_path)
        if isinstance(listing, RuntimeUnavailable):
            return CompletionEnvelope(items=[], degradation_reason=listing.reason)
        items = [
            self._resolved_console_item(listing.target_path, item)
            for item in listing.visible(request.member_prefix, limit=request.max_results)
        ]
        return CompletionEnvelope(
            items=items,
            source=RUNTIME_INTROSPECTION_PROVIDER,
            confidence="runtime_inspection",
        )

    def _resolved_console_item(self, target_path: str, item: CompletionItem) -> CompletionItem:
        detail = self.resolve_member(RuntimeMemberRef(target_path=target_path, name=item.label))
        if isinstance(detail, RuntimeMemberDetail):
            item = replace(item, signature=detail.signature, documentation=detail.documentation)
        return replace(item, side_effect_risk="possible_descriptor_or_getattr", resolvable_fields=())


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


def classify_static_member(raw: Any, *, owner_is_type: bool) -> CompletionKind:
    for raw_types, kind in _STATIC_KIND_TABLE:
        if isinstance(raw, raw_types):
            return kind
    if isinstance(raw, _PLAIN_CALLABLE_TYPES):
        return CompletionKind.METHOD if owner_is_type else CompletionKind.FUNCTION
    return CompletionKind.ATTRIBUTE


def _load_target(target_path: str) -> tuple[str, Any]:
    path = str(target_path or "").strip()
    if not path or not is_whitelisted_target_path(path):
        raise _TargetUnavailable(REPL_INTROSPECTION_DEGRADATION_NOT_WHITELISTED)
    try:
        return path, resolve_whitelisted_target(path)
    except Exception as exc:
        _logger.debug("REPL introspection import failed for %s: %s", path, exc)
        raise _TargetUnavailable(REPL_INTROSPECTION_DEGRADATION_IMPORT_FAILED) from exc


def _static_members(target: Any) -> tuple[RuntimeMember, ...]:
    try:
        names = dir(target)
    except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
        return ()
    owner_is_type = isinstance(target, type)
    return tuple(
        RuntimeMember(name=name, kind=_static_kind(target, name, owner_is_type=owner_is_type))
        for name in sorted(name for name in names if isinstance(name, str) and not name.startswith("__"))
    )


def _static_kind(target: Any, name: str, *, owner_is_type: bool) -> CompletionKind:
    # Names that only __getattr__ or __dir__ provide have no static entry; keep them.
    try:
        return classify_static_member(inspect.getattr_static(target, name), owner_is_type=owner_is_type)
    except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
        return CompletionKind.ATTRIBUTE


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
