"""Unit tests for Rope runtime bootstrap contract checks."""
from __future__ import annotations

import sys
from types import ModuleType

import pytest

import app.intelligence.refactor_runtime as refactor_runtime

pytestmark = pytest.mark.unit


def _reset_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refactor_runtime, "_RUNTIME_INITIALIZED", False)
    monkeypatch.setattr(
        refactor_runtime,
        "_RUNTIME_STATUS",
        refactor_runtime.RefactorRuntimeStatus(False, "not_initialized"),
    )


def test_initialize_refactor_runtime_requires_rope_project_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_runtime_state(monkeypatch)
    fake_rope = ModuleType("rope")
    fake_rope.VERSION = "0.0-test"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "rope", fake_rope)
    monkeypatch.delitem(sys.modules, "rope.base", raising=False)
    monkeypatch.delitem(sys.modules, "rope.base.project", raising=False)
    monkeypatch.delitem(sys.modules, "rope.refactor", raising=False)
    monkeypatch.delitem(sys.modules, "rope.refactor.rename", raising=False)
    monkeypatch.setattr(refactor_runtime, "ensure_vendor_path_on_sys_path", lambda: None)

    status = refactor_runtime.initialize_refactor_runtime()

    assert status.is_available is False
    assert "rope.base" in status.message or "rope.refactor" in status.message


def test_initialize_refactor_runtime_reports_ready_when_modules_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_runtime_state(monkeypatch)
    fake_rope = ModuleType("rope")
    fake_rope.__path__ = []  # type: ignore[attr-defined]
    fake_rope.VERSION = "0.0-test"  # type: ignore[attr-defined]
    fake_rope_base = ModuleType("rope.base")
    fake_rope_base.__path__ = []  # type: ignore[attr-defined]
    fake_rope_base_project = ModuleType("rope.base.project")
    fake_rope_refactor = ModuleType("rope.refactor")
    fake_rope_refactor.__path__ = []  # type: ignore[attr-defined]
    fake_rope_refactor_rename = ModuleType("rope.refactor.rename")

    monkeypatch.setitem(sys.modules, "rope", fake_rope)
    monkeypatch.setitem(sys.modules, "rope.base", fake_rope_base)
    monkeypatch.setitem(sys.modules, "rope.base.project", fake_rope_base_project)
    monkeypatch.setitem(sys.modules, "rope.refactor", fake_rope_refactor)
    monkeypatch.setitem(sys.modules, "rope.refactor.rename", fake_rope_refactor_rename)
    monkeypatch.setattr(refactor_runtime, "ensure_vendor_path_on_sys_path", lambda: None)

    status = refactor_runtime.initialize_refactor_runtime()

    assert status.is_available is True
    assert status.message == "ready"
