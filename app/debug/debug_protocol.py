"""Structured debug transport protocol helpers."""

from __future__ import annotations

from typing import Any, Mapping
import uuid

from app.plugins.rpc_protocol import decode_message, encode_message

DEBUG_PROTOCOL_NAME = "cbcs_debug_v1"


def encode_debug_message(payload: Mapping[str, Any]) -> str:
    """Encode one protocol payload for socket transport."""

    return encode_message(payload)


def decode_debug_message(line: str) -> dict[str, Any]:
    """Decode one protocol payload from socket transport."""

    payload = decode_message(line)
    kind = payload.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("Debug payload missing kind.")
    return payload


def build_hello_message(*, session_token: str, engine_name: str) -> dict[str, Any]:
    """Build initial runner->editor hello payload."""

    return {
        "kind": "hello",
        "protocol": DEBUG_PROTOCOL_NAME,
        "session_token": session_token,
        "engine_name": engine_name,
    }


def build_debug_event(event_name: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build one runner->editor event envelope."""

    return {
        "kind": "event",
        "event": str(event_name),
        "body": dict(body or {}),
    }


def build_debug_command(command_name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build one editor->runner command envelope."""

    return {
        "kind": "command",
        "command": str(command_name),
        "command_id": uuid.uuid4().hex,
        "arguments": dict(arguments or {}),
    }


def build_debug_response(
    *,
    command_name: str,
    command_id: str,
    success: bool,
    body: Mapping[str, Any] | None = None,
    error_message: str = "",
) -> dict[str, Any]:
    """Build one runner->editor response envelope."""

    payload: dict[str, Any] = {
        "kind": "response",
        "command": str(command_name),
        "command_id": str(command_id),
        "success": bool(success),
        "body": dict(body or {}),
    }
    if error_message:
        payload["error_message"] = str(error_message)
    return payload
