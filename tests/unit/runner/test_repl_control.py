"""Unit tests for REPL control request handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.runner.repl_control import _handle_request
from app.runner.repl_introspection import ReplIntrospectionService
from app.runner.repl_protocol import (
    REPL_CONTROL_PROTOCOL,
    REPL_METHOD_LIST_MEMBERS,
    REPL_METHOD_RESOLVE_MEMBER,
    build_ping_request,
)

pytestmark = pytest.mark.unit


def _request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = build_ping_request(
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="expected-token",
    )
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


def test_handle_request_rejects_unsupported_method() -> None:
    completion_service = MagicMock()
    introspection_service = MagicMock()

    response = _handle_request(
        _request(method="unknown"),
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="expected-token",
        completion_service=completion_service,
        introspection_service=introspection_service,
    )

    assert response == {"ok": False, "error": "Unsupported REPL control method: unknown"}
    completion_service.complete.assert_not_called()
    introspection_service.list_members.assert_not_called()


def _handle_with_real_introspection(**overrides: object) -> dict[str, object]:
    return _handle_request(
        _request(**overrides),
        protocol=REPL_CONTROL_PROTOCOL,
        session_token="expected-token",
        completion_service=MagicMock(),
        introspection_service=ReplIntrospectionService(),
    )


def test_handle_request_list_members_returns_names_and_kinds() -> None:
    pytest.importorskip("PySide2.QtCore")

    response = _handle_with_real_introspection(method=REPL_METHOD_LIST_MEMBERS, target_path="PySide2.QtCore.QObject")

    result = response.get("result")
    assert isinstance(result, dict)
    assert ["objectName", "method"] in result["members"]


def test_handle_request_resolve_member_returns_signature_and_documentation() -> None:
    pytest.importorskip("PySide2.QtCore")

    response = _handle_with_real_introspection(
        method=REPL_METHOD_RESOLVE_MEMBER,
        target_path="PySide2.QtCore.QObject",
        member_name="setObjectName",
    )

    result = response.get("result")
    assert isinstance(result, dict)
    assert str(result["signature"]).startswith("(")
    assert "setObjectName" in str(result["documentation"])


def test_handle_request_list_members_reports_non_whitelisted_target_as_error() -> None:
    response = _handle_with_real_introspection(method=REPL_METHOD_LIST_MEMBERS, target_path="os.path")

    assert response.get("ok") is False
