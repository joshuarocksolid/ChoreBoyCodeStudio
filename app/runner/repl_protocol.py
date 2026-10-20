"""JSON-line protocol helpers for Python Console metadata requests."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.intelligence.runtime_members import (
    RuntimeListingResult,
    RuntimeMember,
    RuntimeMemberDetail,
    RuntimeMemberListing,
    RuntimeUnavailable,
)

REPL_CONTROL_PROTOCOL = "cbcs_repl_control_v1"

REPL_METHOD_COMPLETE = "complete"
REPL_METHOD_LIST_MEMBERS = "list_members"
REPL_METHOD_RESOLVE_MEMBER = "resolve_member"
REPL_METHOD_PING = "ping"

SUPPORTED_REPL_METHODS = frozenset(
    {
        REPL_METHOD_COMPLETE,
        REPL_METHOD_LIST_MEMBERS,
        REPL_METHOD_RESOLVE_MEMBER,
        REPL_METHOD_PING,
    }
)

REPL_DEGRADATION_INVALID_RESPONSE = "repl_invalid_response"

REPL_ERROR_INCOMPATIBLE_PROTOCOL = "Incompatible REPL control protocol."
REPL_ERROR_INVALID_SESSION_TOKEN = "Invalid REPL control session token."
REPL_ERROR_UNSUPPORTED_METHOD = "Unsupported REPL control method: %s"


class ReplControlProtocolError(ValueError):
    """Invalid REPL control wire message."""


def completion_item_to_dict(item: CompletionItem) -> dict[str, Any]:
    """Serialize a completion item for the REPL control channel."""

    payload = asdict(item)
    payload["kind"] = item.kind.value
    return payload


def completion_item_from_dict(payload: dict[str, Any]) -> CompletionItem:
    """Parse a completion item from the REPL control channel."""

    try:
        kind = CompletionKind(str(payload.get("kind", CompletionKind.SYMBOL.value)))
    except ValueError:
        kind = CompletionKind.SYMBOL
    return CompletionItem(
        label=str(payload.get("label") or ""),
        insert_text=str(payload.get("insert_text") or payload.get("label") or ""),
        kind=kind,
        detail=str(payload.get("detail") or ""),
        documentation=str(payload.get("documentation") or ""),
        signature=str(payload.get("signature") or ""),
        return_type=str(payload.get("return_type") or ""),
        source_file_path=payload.get("source_file_path") if isinstance(payload.get("source_file_path"), str) else None,
        engine=str(payload.get("engine") or ""),
        source=str(payload.get("source") or ""),
        confidence=str(payload.get("confidence") or ""),
        semantic_kind=str(payload.get("semantic_kind") or ""),
        replacement_start=_optional_int(payload.get("replacement_start")),
        replacement_end=_optional_int(payload.get("replacement_end")),
        trigger_kind=str(payload.get("trigger_kind") or ""),
        trigger_character=str(payload.get("trigger_character") or ""),
        side_effect_risk=str(payload.get("side_effect_risk") or ""),
    )


def envelope_to_dict(envelope: CompletionEnvelope) -> dict[str, Any]:
    """Serialize a completion envelope for JSON transport."""

    return {
        "items": [completion_item_to_dict(item) for item in envelope.items],
        "degradation_reason": envelope.degradation_reason,
        "source": envelope.source,
        "confidence": envelope.confidence,
    }


def envelope_from_dict(payload: dict[str, Any]) -> CompletionEnvelope:
    """Parse a completion envelope from JSON transport."""

    raw_items = payload.get("items", [])
    items = [
        completion_item_from_dict(item)
        for item in raw_items
        if isinstance(item, dict)
    ] if isinstance(raw_items, list) else []
    return CompletionEnvelope(
        items=items,
        degradation_reason=str(payload.get("degradation_reason") or ""),
        source=str(payload.get("source") or ""),
        confidence=str(payload.get("confidence") or ""),
    )


def build_repl_request(
    *,
    protocol: str,
    session_token: str,
    method: str,
    **fields: Any,
) -> dict[str, Any]:
    """Build one editor->runner REPL control request envelope."""

    if method not in SUPPORTED_REPL_METHODS:
        raise ReplControlProtocolError(REPL_ERROR_UNSUPPORTED_METHOD % (method,))
    if not str(protocol).strip():
        raise ReplControlProtocolError("REPL control protocol must be non-empty.")
    if not str(session_token).strip():
        raise ReplControlProtocolError("REPL control session token must be non-empty.")
    payload: dict[str, Any] = {
        "protocol": str(protocol),
        "session_token": str(session_token),
        "method": method,
    }
    payload.update(fields)
    return payload


def build_complete_request(
    *,
    protocol: str,
    session_token: str,
    line_buffer: str,
    cursor_offset: int,
    trigger_kind: str = "invoked",
    trigger_character: str = "",
    max_results: int = 100,
) -> dict[str, Any]:
    """Build a completion request envelope."""

    return build_repl_request(
        protocol=protocol,
        session_token=session_token,
        method=REPL_METHOD_COMPLETE,
        line_buffer=line_buffer,
        cursor_offset=cursor_offset,
        trigger_kind=trigger_kind,
        trigger_character=trigger_character,
        max_results=max_results,
    )


def build_list_members_request(*, protocol: str, session_token: str, target_path: str) -> dict[str, Any]:
    return build_repl_request(
        protocol=protocol,
        session_token=session_token,
        method=REPL_METHOD_LIST_MEMBERS,
        target_path=target_path,
    )


def build_resolve_member_request(
    *,
    protocol: str,
    session_token: str,
    target_path: str,
    member_name: str,
) -> dict[str, Any]:
    return build_repl_request(
        protocol=protocol,
        session_token=session_token,
        method=REPL_METHOD_RESOLVE_MEMBER,
        target_path=target_path,
        member_name=member_name,
    )


def listing_to_wire(listing: RuntimeMemberListing) -> dict[str, Any]:
    return {
        "target_path": listing.target_path,
        "members": [[member.name, member.kind.value] for member in (*listing.public, *listing.private)],
    }


def listing_from_wire(payload: dict[str, Any]) -> RuntimeListingResult:
    target_path = payload.get("target_path")
    raw_members = payload.get("members")
    if not isinstance(target_path, str) or not isinstance(raw_members, list):
        return RuntimeUnavailable(reason=REPL_DEGRADATION_INVALID_RESPONSE)
    members: list[RuntimeMember] = []
    for entry in raw_members:
        if not isinstance(entry, list) or not entry or not isinstance(entry[0], str):
            continue
        members.append(RuntimeMember(name=entry[0], kind=_kind_from_wire(entry[1] if len(entry) > 1 else None)))
    return RuntimeMemberListing.from_members(target_path, members)


def detail_to_wire(detail: RuntimeMemberDetail) -> dict[str, Any]:
    return {"signature": detail.signature, "documentation": detail.documentation}


def detail_from_wire(payload: dict[str, Any]) -> RuntimeMemberDetail:
    signature = payload.get("signature")
    documentation = payload.get("documentation")
    return RuntimeMemberDetail(
        signature=signature if isinstance(signature, str) else "",
        documentation=documentation if isinstance(documentation, str) else "",
    )


def build_ping_request(*, protocol: str, session_token: str) -> dict[str, Any]:
    """Build a health-check request envelope."""

    return build_repl_request(
        protocol=protocol,
        session_token=session_token,
        method=REPL_METHOD_PING,
    )


def validate_repl_request(
    payload: dict[str, Any],
    *,
    expected_protocol: str,
    expected_session_token: str,
) -> str:
    """Validate an inbound REPL control request and return its method name."""

    if payload.get("protocol") != expected_protocol:
        raise ReplControlProtocolError(REPL_ERROR_INCOMPATIBLE_PROTOCOL)
    if payload.get("session_token") != expected_session_token:
        raise ReplControlProtocolError(REPL_ERROR_INVALID_SESSION_TOKEN)
    method = payload.get("method")
    if not isinstance(method, str) or method not in SUPPORTED_REPL_METHODS:
        raise ReplControlProtocolError(REPL_ERROR_UNSUPPORTED_METHOD % (method,))
    return method


def build_repl_success_response(result: dict[str, Any]) -> dict[str, Any]:
    """Build one runner->editor success envelope."""

    return {"ok": True, "result": result}


def build_repl_error_response(error: str) -> dict[str, Any]:
    """Build one runner->editor error envelope."""

    return {"ok": False, "error": str(error)}


def dumps_message(payload: dict[str, Any]) -> bytes:
    """Return one UTF-8 JSON-line protocol message."""

    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def loads_message(raw_line: bytes) -> dict[str, Any]:
    """Parse one UTF-8 JSON-line protocol message."""

    payload = json.loads(raw_line.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("REPL control message must be a JSON object.")
    return payload


def _kind_from_wire(value: object) -> CompletionKind:
    try:
        return CompletionKind(str(value))
    except ValueError:
        return CompletionKind.ATTRIBUTE


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None
