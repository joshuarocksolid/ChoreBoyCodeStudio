"""Unit tests for Jedi runtime bootstrap contract checks."""
from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest

import app.intelligence.jedi_runtime as jedi_runtime

pytestmark = pytest.mark.unit


def _reset_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jedi_runtime, "_RUNTIME_INITIALIZED", False)
    monkeypatch.setattr(
        jedi_runtime,
        "_RUNTIME_STATUS",
        jedi_runtime.JediRuntimeStatus(False, "not_initialized"),
    )


def test_initialize_jedi_runtime_requires_script_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _reset_runtime_state(monkeypatch)
    fake_jedi = ModuleType("jedi")
    fake_jedi.settings = SimpleNamespace(cache_directory="")
    fake_jedi.__version__ = "0.0-test"
    fake_parso = ModuleType("parso")
    fake_parso.__version__ = "0.0-test"
    monkeypatch.setitem(__import__("sys").modules, "jedi", fake_jedi)
    monkeypatch.setitem(__import__("sys").modules, "parso", fake_parso)
    monkeypatch.setattr(jedi_runtime, "ensure_vendor_path_on_sys_path", lambda: None)

    status = jedi_runtime.initialize_jedi_runtime(state_root=str(tmp_path))

    assert status.is_available is False
    assert "Script" in status.message


def test_initialize_jedi_runtime_does_not_require_settings_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    _reset_runtime_state(monkeypatch)
    fake_jedi = ModuleType("jedi")
    fake_jedi.Script = object  # type: ignore[attr-defined]
    fake_jedi.__version__ = "0.0-test"
    fake_parso = ModuleType("parso")
    fake_parso.__version__ = "0.0-test"
    monkeypatch.setitem(__import__("sys").modules, "jedi", fake_jedi)
    monkeypatch.setitem(__import__("sys").modules, "parso", fake_parso)
    monkeypatch.setattr(jedi_runtime, "ensure_vendor_path_on_sys_path", lambda: None)

    status = jedi_runtime.initialize_jedi_runtime(state_root=str(tmp_path))

    assert status.is_available is True
    assert status.message == "ready"
