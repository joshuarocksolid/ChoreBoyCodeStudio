"""Unit tests for plugin host RPC protocol helpers."""

from __future__ import annotations

import pytest

from app.plugins.rpc_protocol import build_command_request, build_response, decode_message, encode_message

pytestmark = pytest.mark.unit


def test_encode_and_decode_message_round_trip() -> None:
    payload = {"type": "ping", "value": 1}

    encoded = encode_message(payload)
    decoded = decode_message(encoded)

    assert encoded.endswith("\n")
    assert decoded == payload


def test_decode_message_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError, match="RPC payload must be a JSON object"):
        decode_message('["not", "an", "object"]')


def test_build_command_request_includes_default_payload() -> None:
    request = build_command_request(request_id="abc", command_id="cmd.test")
    assert request == {
        "type": "command",
        "request_id": "abc",
        "command_id": "cmd.test",
        "payload": {},
    }


def test_build_response_sets_result_or_error_fields() -> None:
    ok_response = build_response(request_id="abc", ok=True, result={"value": 1})
    error_response = build_response(request_id="abc", ok=False)

    assert ok_response["result"] == {"value": 1}
    assert "error" not in ok_response
    assert error_response["error"] == "unknown error"
