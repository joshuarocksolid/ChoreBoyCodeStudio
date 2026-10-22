"""Unit tests for REPL control protocol serialization helpers."""

from __future__ import annotations

import json

import pytest

from app.intelligence.completion_models import CompletionEnvelope, CompletionItem, CompletionKind
from app.intelligence.runtime_members import RuntimeMember, RuntimeMemberListing
from app.runner.repl_protocol import (
    REPL_CONTROL_PROTOCOL,
    REPL_ERROR_INCOMPATIBLE_PROTOCOL,
    REPL_ERROR_INVALID_SESSION_TOKEN,
    REPL_ERROR_UNSUPPORTED_METHOD,
    REPL_METHOD_COMPLETE,
    REPL_METHOD_LIST_MEMBERS,
    REPL_METHOD_PING,
    REPL_METHOD_RESOLVE_MEMBER,
    ReplControlProtocolError,
    build_complete_request,
    build_repl_error_response,
    build_repl_request,
    build_repl_success_response,
    completion_item_from_dict,
    completion_item_to_dict,
    envelope_from_dict,
    envelope_to_dict,
    listing_from_wire,
    listing_to_wire,
    validate_repl_request,
)

pytestmark = pytest.mark.unit


def test_completion_item_round_trip_preserves_replacement_range() -> None:
    item = CompletionItem(
        label="sample_value",
        insert_text="sample_value",
        kind=CompletionKind.ATTRIBUTE,
        detail="live runtime",
        documentation="doc",
        signature="()",
        engine="runtime_dir",
        source="runtime",
        confidence="runtime_inspection",
        replacement_start=4,
        replacement_end=7,
        trigger_kind="invoked",
        trigger_character="",
        side_effect_risk="none",
    )

    restored = completion_item_from_dict(completion_item_to_dict(item))

    assert restored.label == item.label
    assert restored.kind == item.kind
    assert restored.replacement_start == item.replacement_start
    assert restored.replacement_end == item.replacement_end
    assert restored.side_effect_risk == item.side_effect_risk


def test_envelope_round_trip_preserves_degradation_metadata() -> None:
    envelope = CompletionEnvelope(
        items=[
            CompletionItem(
                label="obj",
                insert_text="obj",
                kind=CompletionKind.SYMBOL,
                source="runtime",
                confidence="runtime_inspection",
            )
        ],
        degradation_reason="repl_no_completions",
        source="runtime",
        confidence="runtime_inspection",
    )

    restored = envelope_from_dict(envelope_to_dict(envelope))

    assert restored.degradation_reason == envelope.degradation_reason
    assert restored.source == envelope.source
    assert restored.confidence == envelope.confidence
    assert len(restored.items) == 1
    assert restored.items[0].label == "obj"


def test_repl_control_protocol_constant_is_non_empty() -> None:
    assert REPL_CONTROL_PROTOCOL


def test_build_complete_request_includes_protocol_and_method() -> None:
    payload = build_complete_request(
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="token",
        line_buffer="sample_",
        cursor_offset=7,
        trigger_kind="typing",
        max_results=20,
    )

    assert payload["protocol"] == REPL_CONTROL_PROTOCOL
    assert payload["session_token"] == "token"
    assert payload["method"] == REPL_METHOD_COMPLETE
    assert payload["line_buffer"] == "sample_"
    assert payload["cursor_offset"] == 7


def test_member_listing_survives_the_json_wire() -> None:
    listing = RuntimeMemberListing.from_members(
        "PySide2.QtCore.QObject",
        [
            RuntimeMember(name="_hidden", kind=CompletionKind.ATTRIBUTE),
            RuntimeMember(name="objectName", kind=CompletionKind.METHOD),
            RuntimeMember(name="staticMetaObject", kind=CompletionKind.PROPERTY),
        ],
    )

    restored = listing_from_wire(json.loads(json.dumps(listing_to_wire(listing))))

    assert restored == listing


def test_member_listing_wire_keeps_names_with_unknown_kinds() -> None:
    restored = listing_from_wire(
        {
            "target_path": "PySide2.QtCore",
            "members": [["Signal", "signal_kind_from_the_future"], [7, "method"], ["Qt"]],
        }
    )

    assert restored == RuntimeMemberListing.from_members(
        "PySide2.QtCore",
        [
            RuntimeMember(name="Signal", kind=CompletionKind.ATTRIBUTE),
            RuntimeMember(name="Qt", kind=CompletionKind.ATTRIBUTE),
        ],
    )


def test_build_repl_request_rejects_unknown_method() -> None:
    with pytest.raises(ReplControlProtocolError, match="Unsupported REPL control method"):
        build_repl_request(
            protocol=REPL_CONTROL_PROTOCOL,
            session_token="token",
            method="resolve",
        )


def test_validate_repl_request_rejects_invalid_boundary() -> None:
    cases = [
        (
            {"protocol": "wrong", "session_token": "token", "method": REPL_METHOD_PING},
            REPL_ERROR_INCOMPATIBLE_PROTOCOL,
        ),
        (
            {"protocol": REPL_CONTROL_PROTOCOL, "session_token": "wrong", "method": REPL_METHOD_PING},
            REPL_ERROR_INVALID_SESSION_TOKEN,
        ),
        (
            {"protocol": REPL_CONTROL_PROTOCOL, "session_token": "token", "method": "unknown"},
            REPL_ERROR_UNSUPPORTED_METHOD % ("unknown",),
        ),
    ]
    for payload, expected_error in cases:
        with pytest.raises(ReplControlProtocolError) as exc_info:
            validate_repl_request(
                payload,
                expected_protocol=REPL_CONTROL_PROTOCOL,
                expected_session_token="token",
            )
        assert str(exc_info.value) == expected_error


def test_validate_repl_request_accepts_supported_methods() -> None:
    for method in (REPL_METHOD_COMPLETE, REPL_METHOD_LIST_MEMBERS, REPL_METHOD_RESOLVE_MEMBER, REPL_METHOD_PING):
        validated = validate_repl_request(
            {
                "protocol": REPL_CONTROL_PROTOCOL,
                "session_token": "token",
                "method": method,
            },
            expected_protocol=REPL_CONTROL_PROTOCOL,
            expected_session_token="token",
        )
        assert validated == method


def test_repl_response_envelopes() -> None:
    assert build_repl_success_response({"status": "ready"}) == {
        "ok": True,
        "result": {"status": "ready"},
    }
    assert build_repl_error_response("boom") == {"ok": False, "error": "boom"}
