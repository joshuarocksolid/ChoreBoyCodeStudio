"""Unit tests for plugin host RPC protocol helpers."""

from __future__ import annotations

import pytest

from app.plugins.rpc_protocol import (
    build_command_request,
    build_job_event,
    build_job_terminal_message,
    build_provider_job_cancel_request,
    build_provider_job_start_request,
    build_provider_query_request,
    build_response,
    decode_message,
    encode_message,
)

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


def test_build_provider_query_and_job_requests_include_expected_fields() -> None:
    query = build_provider_query_request(
        request_id="abc",
        provider_key="cbcs.python_tools:formatter",
        request={"value": 1},
        activation_event="on_provider:formatter",
    )
    job_start = build_provider_job_start_request(
        request_id="def",
        job_id="job-1",
        provider_key="cbcs.pytest:pytest",
        request={"project_root": "/tmp/project"},
    )
    job_cancel = build_provider_job_cancel_request(request_id="ghi", job_id="job-1")

    assert query["type"] == "provider_query"
    assert query["provider_key"] == "cbcs.python_tools:formatter"
    assert query["activation_event"] == "on_provider:formatter"
    assert job_start["type"] == "provider_job_start"
    assert job_start["job_id"] == "job-1"
    assert job_cancel == {"type": "provider_job_cancel", "request_id": "ghi", "job_id": "job-1"}


def test_build_job_event_and_terminal_messages_are_structured() -> None:
    event = build_job_event(
        job_id="job-1",
        provider_key="cbcs.pytest:pytest",
        event_type="job_progress",
        payload={"completed": 1},
    )
    result = build_job_terminal_message(
        job_id="job-1",
        provider_key="cbcs.pytest:pytest",
        message_type="job_result",
        result={"ok": True},
    )
    error = build_job_terminal_message(
        job_id="job-1",
        provider_key="cbcs.pytest:pytest",
        message_type="job_error",
        error="boom",
    )

    assert event["type"] == "job_event"
    assert event["payload"] == {"completed": 1}
    assert result["result"] == {"ok": True}
    assert error["error"] == "boom"
