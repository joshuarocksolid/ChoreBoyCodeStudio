"""Runtime member listing and per-row details, owned by the REPL runner process.

Listing is cheap and safe: ``dir()`` plus ``inspect.getattr_static`` for the
kind and a short type. No getter, ``__getattr__`` or docstring work runs, and
nothing is cut. Details (signatures, first doc paragraph, defining class) are
resolved only for the row the user highlights.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
import importlib
import inspect
import logging
import re
import threading
import types
from typing import Any, Callable, List, Optional, Tuple

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
_DOTTED_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_DOC_SIGNATURE_LINE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_.]*\s*\(.*\)\s*(->\s*.+)?$")

NamespaceLookup = Callable[[str], Any]


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
    """List members and resolve one member's details.

    Whitelisted dotted paths are imported. With ``namespace_lookup``, any other
    dotted name is read from the live console namespace (``btn`` or
    ``self.window``), the same objects the console's ``dir()`` listing uses.
    """

    def __init__(self, *, namespace_lookup: Optional[NamespaceLookup] = None) -> None:
        self._namespace_lookup = namespace_lookup

    def list_members(self, target_path: str) -> RuntimeListingResult:
        try:
            path, target = self._load_target(target_path)
        except _TargetUnavailable as exc:
            return RuntimeUnavailable(reason=exc.reason)
        return RuntimeMemberListing.from_members(path, static_members(target))

    def resolve_member(self, ref: RuntimeMemberRef) -> RuntimeDetailResult:
        try:
            _path, target = self._load_target(ref.target_path)
        except _TargetUnavailable as exc:
            return RuntimeUnavailable(reason=exc.reason)
        return resolve_member_detail(target, ref.name)

    def introspect(self, request: ReplIntrospectionRequest) -> CompletionEnvelope:
        """Return every matching member as a row whose docs resolve on demand."""

        listing = self.list_members(request.target_path)
        if isinstance(listing, RuntimeUnavailable):
            return CompletionEnvelope(items=[], degradation_reason=listing.reason)
        return CompletionEnvelope(
            items=listing.visible(request.member_prefix),
            source=RUNTIME_INTROSPECTION_PROVIDER,
            confidence="runtime_inspection",
        )

    def _load_target(self, target_path: str) -> tuple[str, Any]:
        path = str(target_path or "").strip()
        if path and is_whitelisted_target_path(path):
            try:
                return path, resolve_whitelisted_target(path)
            except Exception as exc:
                _logger.debug("REPL introspection import failed for %s: %s", path, exc)
                raise _TargetUnavailable(REPL_INTROSPECTION_DEGRADATION_IMPORT_FAILED) from exc
        if self._namespace_lookup is None or not _DOTTED_NAME.match(path):
            raise _TargetUnavailable(REPL_INTROSPECTION_DEGRADATION_NOT_WHITELISTED)
        try:
            return path, self._namespace_lookup(path)
        except REPL_RUNTIME_DEGRADATION_EXCEPTIONS as exc:
            raise _TargetUnavailable(REPL_INTROSPECTION_DEGRADATION_MEMBER_FAILED) from exc


def namespace_lookup_for(namespace: dict[str, Any], lock: Optional[threading.RLock] = None) -> NamespaceLookup:
    """Return a lookup that walks ``a.b.c`` through ``namespace`` with plain getattr."""

    guard = lock or threading.RLock()

    def lookup(path: str) -> Any:
        parts = path.split(".")
        with guard:
            if parts[0] not in namespace:
                raise NameError(parts[0])
            value = namespace[parts[0]]
            for part in parts[1:]:
                value = getattr(value, part)
        return value

    return lookup


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
    if _is_qt_signal(raw):
        return CompletionKind.SIGNAL
    if _is_enum_value(raw):
        return CompletionKind.ENUM
    for raw_types, kind in _STATIC_KIND_TABLE:
        if isinstance(raw, raw_types):
            return kind
    if isinstance(raw, _PLAIN_CALLABLE_TYPES):
        return CompletionKind.METHOD if owner_is_type else CompletionKind.FUNCTION
    if callable(raw):
        return CompletionKind.METHOD if owner_is_type else CompletionKind.FUNCTION
    return CompletionKind.ATTRIBUTE


def static_members(target: Any) -> tuple[RuntimeMember, ...]:
    """Every name ``dir(target)`` reports, with a kind and a short type. Never getattr."""

    try:
        names = dir(target)
    except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
        return ()
    owner_is_type = not isinstance(target, types.ModuleType)
    members: List[RuntimeMember] = []
    for name in sorted(name for name in names if isinstance(name, str)):
        try:
            raw = inspect.getattr_static(target, name)
        except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
            # Names that only __getattr__ or __dir__ provide have no static entry.
            members.append(RuntimeMember(name=name, kind=CompletionKind.ATTRIBUTE, short_type=""))
            continue
        kind = classify_static_member(raw, owner_is_type=owner_is_type)
        members.append(RuntimeMember(name=name, kind=kind, short_type=_short_type(raw, kind)))
    return tuple(members)


def resolve_member_detail(target: Any, name: str) -> RuntimeDetailResult:
    """Signature(s), first doc paragraph and defining class for one member."""

    try:
        raw = inspect.getattr_static(target, name)
    except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
        raw = None
    owner_is_type = not isinstance(target, types.ModuleType)
    kind = classify_static_member(raw, owner_is_type=owner_is_type) if raw is not None else CompletionKind.ATTRIBUTE
    if kind == CompletionKind.PROPERTY and not isinstance(target, type):
        # Reading a property on an instance runs its getter; describe it statically.
        value: Any = raw
    else:
        try:
            value = getattr(target, name)
        except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
            if raw is None:
                return RuntimeUnavailable(reason=REPL_INTROSPECTION_DEGRADATION_MEMBER_FAILED)
            value = raw
    signatures: List[str] = []
    if kind in (CompletionKind.METHOD, CompletionKind.FUNCTION, CompletionKind.CLASS):
        signatures = _signatures(name, value)
    elif kind == CompletionKind.SIGNAL:
        signatures = [name + _signal_arguments(value)]
    doc_lines = _safe_doc(value).strip().splitlines() if kind not in (CompletionKind.ATTRIBUTE, CompletionKind.ENUM) else []
    doc_signatures: List[str] = []
    while doc_lines and _DOC_SIGNATURE_LINE.match(doc_lines[0]):
        doc_signatures.append(doc_lines.pop(0).strip())
    if not signatures:
        signatures = doc_signatures
    owner = _owner_name(target, name)
    owner_line = "{} {}".format(owner, kind.value) if owner else kind.value
    return RuntimeMemberDetail(
        signature="\n".join(signatures),
        documentation=first_paragraph("\n".join(doc_lines)),
        owner=owner_line,
    )


def prewarm_signature_machinery() -> None:
    """Pay the one-time cost of the first ``inspect.signature`` call (14-28 ms on ChoreBoy)."""

    try:
        inspect.signature(prewarm_signature_machinery)
    except (TypeError, ValueError):
        pass
    try:
        from PySide2 import QtCore  # noqa: WPS433 - optional, runner side only

        _signatures("setObjectName", QtCore.QObject.setObjectName)
    except Exception:
        pass


def start_prewarm_thread() -> None:
    thread = threading.Thread(target=prewarm_signature_machinery, name="cbcs-repl-prewarm", daemon=True)
    thread.start()


def _signatures(name: str, value: Any) -> List[str]:
    try:
        return [name + str(inspect.signature(value))]
    except (TypeError, ValueError):
        pass
    except Exception:
        return []
    raw = getattr(value, "__signature__", None)
    if isinstance(raw, (list, tuple)):
        lines: List[str] = []
        for one in raw:
            text = name + str(one)
            if text not in lines:
                lines.append(text)
        return lines
    return []


def _signal_arguments(value: Any) -> str:
    text = str(value or "")
    found = re.search(r"\((.*)\)", text)
    return "({})".format(found.group(1)) if found else "()"


def _owner_name(target: Any, name: str) -> str:
    if isinstance(target, types.ModuleType):
        return ""
    klass = target if isinstance(target, type) else type(target)
    try:
        mro: Tuple[type, ...] = klass.__mro__
    except AttributeError:
        return ""
    for candidate in mro:
        try:
            if name in vars(candidate):
                return candidate.__name__
        except TypeError:
            continue
    return ""


def _short_type(raw: Any, kind: CompletionKind) -> str:
    if kind in (CompletionKind.ATTRIBUTE, CompletionKind.ENUM):
        return type(raw).__name__
    return kind.value


def _is_qt_signal(raw: Any) -> bool:
    raw_type = type(raw)
    return raw_type.__name__ == "Signal" and str(getattr(raw_type, "__module__", "")).startswith("PySide2")


def _is_enum_value(raw: Any) -> bool:
    if isinstance(raw, enum.Enum):
        return True
    raw_type = type(raw)
    module = str(getattr(raw_type, "__module__", ""))
    return module.startswith(("PySide2", "shiboken2")) and hasattr(raw_type, "values") and hasattr(raw, "name")


def _safe_doc(value: Any) -> str:
    try:
        return inspect.getdoc(value) or ""
    except REPL_RUNTIME_DEGRADATION_EXCEPTIONS:
        return ""


def console_member_items(
    *,
    expression: str,
    value: Any,
    prefix: str,
    replacement_start: int,
    replacement_end: int,
    trigger_kind: str,
    trigger_character: str,
) -> list[CompletionItem]:
    """Rows for ``expression.`` in the console: every member, details on demand."""

    listing = RuntimeMemberListing.from_members(expression, static_members(value))
    fingerprint = "live:{:x}".format(id(value))
    items: list[CompletionItem] = []
    for item in listing.visible(prefix):
        items.append(
            CompletionItem(
                label=item.label,
                insert_text=item.insert_text,
                kind=item.kind,
                detail=item.detail,
                engine=item.engine,
                source=item.source,
                confidence=item.confidence,
                semantic_kind=item.semantic_kind,
                replacement_start=replacement_start,
                replacement_end=replacement_end,
                trigger_kind=trigger_kind,
                trigger_character=trigger_character,
                item_id=item.item_id,
                context_fingerprint=fingerprint,
                resolve_provider=item.resolve_provider,
                resolvable_fields=item.resolvable_fields,
            )
        )
    return items
