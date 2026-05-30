"""Unit tests for whitelisted REPL runtime introspection."""

from __future__ import annotations

import pytest

from app.runner.repl_introspection import (
    ReplIntrospectionRequest,
    ReplIntrospectionService,
    is_whitelisted_target_path,
)

pytestmark = pytest.mark.unit


def test_is_whitelisted_target_path_accepts_trusted_modules() -> None:
    assert is_whitelisted_target_path("PySide2.QtCore")
    assert is_whitelisted_target_path("FreeCAD")
    assert not is_whitelisted_target_path("os.path")


def test_introspect_returns_pyside_members() -> None:
    service = ReplIntrospectionService()

    envelope = service.introspect(
        ReplIntrospectionRequest(
            target_path="PySide2.QtCore",
            include_private=False,
            max_results=50,
        )
    )

    assert envelope.items
    assert envelope.source == "runtime_introspection"


def test_introspect_rejects_non_whitelisted_target() -> None:
    service = ReplIntrospectionService()

    envelope = service.introspect(
        ReplIntrospectionRequest(target_path="os.path", max_results=10)
    )

    assert envelope.items == []
    assert envelope.degradation_reason == "repl_introspection_not_whitelisted"
