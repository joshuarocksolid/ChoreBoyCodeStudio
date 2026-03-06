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
