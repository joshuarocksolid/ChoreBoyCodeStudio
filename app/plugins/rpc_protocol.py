from __future__ import annotations

import json
from typing import Any, Mapping


def encode_message(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True) + "\n"


def decode_message(line: str) -> dict[str, Any]:
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("RPC payload must be a JSON object.")
    return payload


def build_command_request(*, request_id: str, command_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "command",
        "request_id": request_id,
        "command_id": command_id,
        "payload": dict(payload or {}),
    }


def build_provider_query_request(
    *,
    request_id: str,
    provider_key: str,
    request: Mapping[str, Any] | None = None,
    activation_event: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "provider_query",
        "request_id": request_id,
        "provider_key": provider_key,
        "request": dict(request or {}),
    }
    if activation_event:
        payload["activation_event"] = activation_event
    return payload


def build_provider_job_start_request(
    *,
    request_id: str,
    job_id: str,
    provider_key: str,
    request: Mapping[str, Any] | None = None,
    activation_event: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "provider_job_start",
        "request_id": request_id,
        "job_id": job_id,
        "provider_key": provider_key,
        "request": dict(request or {}),
    }
    if activation_event:
        payload["activation_event"] = activation_event
    return payload


def build_provider_job_cancel_request(*, request_id: str, job_id: str) -> dict[str, Any]:
    return {
        "type": "provider_job_cancel",
        "request_id": request_id,
        "job_id": job_id,
    }


def build_response(
    *,
    request_id: str,
    ok: bool,
    result: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "type": "response",
        "request_id": request_id,
        "ok": ok,
    }
    if ok:
        response["result"] = result
    else:
        response["error"] = error or "unknown error"
    return response


def build_job_event(
    *,
    job_id: str,
    provider_key: str,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "job_event",
        "job_id": job_id,
        "provider_key": provider_key,
        "event_type": event_type,
        "payload": dict(payload or {}),
    }


def build_job_terminal_message(
    *,
    job_id: str,
    provider_key: str,
    message_type: str,
    result: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": message_type,
        "job_id": job_id,
        "provider_key": provider_key,
    }
    if message_type == "job_result":
        payload["result"] = result
    else:
        payload["error"] = error or "unknown error"
    return payload
