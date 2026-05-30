"""Unit tests for REPL control request handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.runner.repl_control import _handle_request
from app.runner.repl_protocol import REPL_CONTROL_PROTOCOL

pytestmark = pytest.mark.unit


def _request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "protocol": REPL_CONTROL_PROTOCOL,
        "session_token": "expected-token",
        "method": "ping",
    }
    payload.update(overrides)
    return payload


def test_handle_request_rejects_incompatible_protocol() -> None:
    completion_service = MagicMock()
    introspection_service = MagicMock()

    response = _handle_request(
        _request(protocol="wrong-protocol"),
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="expected-token",
        completion_service=completion_service,
        introspection_service=introspection_service,
    )

    assert response == {"ok": False, "error": "Incompatible REPL control protocol."}
    completion_service.complete.assert_not_called()


def test_handle_request_rejects_invalid_session_token() -> None:
    completion_service = MagicMock()
    introspection_service = MagicMock()

    response = _handle_request(
        _request(session_token="wrong-token"),
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="expected-token",
        completion_service=completion_service,
        introspection_service=introspection_service,
    )

    assert response == {"ok": False, "error": "Invalid REPL control session token."}
    completion_service.complete.assert_not_called()


def test_handle_request_introspect_returns_envelope() -> None:
    from app.runner.repl_introspection import ReplIntrospectionService

    completion_service = MagicMock()
    introspection_service = ReplIntrospectionService()

    response = _handle_request(
        _request(
            method="introspect",
            target_path="PySide2.QtCore",
            member_prefix="",
            include_private=False,
            max_results=10,
        ),
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="expected-token",
        completion_service=completion_service,
        introspection_service=introspection_service,
    )

    assert response.get("ok") is True
    result = response.get("result")
    assert isinstance(result, dict)
    assert result.get("items")
    completion_service.complete.assert_not_called()
