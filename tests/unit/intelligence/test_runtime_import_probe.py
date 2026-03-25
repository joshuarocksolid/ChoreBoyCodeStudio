"""Unit tests for detailed runtime import probing."""
from __future__ import annotations

import subprocess

import pytest

from app.intelligence import runtime_import_probe as runtime_import_probe_module
from app.intelligence.runtime_import_probe import probe_runtime_module_importability

pytestmark = pytest.mark.unit


def test_probe_runtime_module_importability_reports_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime_import_probe_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(  # type: ignore[no-untyped-def]
            command,
            1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'FreeCADGui'",
        ),
    )
    monkeypatch.setattr(
        runtime_import_probe_module,
        "resolve_probe_runtime_path",
        lambda: "/opt/freecad/AppRun",
    )
    runtime_import_probe_module.clear_runtime_import_probe_cache()

    result = probe_runtime_module_importability("FreeCADGui")

    assert result.is_importable is False
    assert result.failure_reason == "import_error"
    assert "ModuleNotFoundError" in result.detail


def test_probe_runtime_module_importability_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(command, **kwargs):  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(command, 5)

    monkeypatch.setattr(runtime_import_probe_module.subprocess, "run", _raise_timeout)
    monkeypatch.setattr(
        runtime_import_probe_module,
        "resolve_probe_runtime_path",
        lambda: "/opt/freecad/AppRun",
    )
    runtime_import_probe_module.clear_runtime_import_probe_cache()

    result = probe_runtime_module_importability("FreeCADGui")

    assert result.is_importable is False
    assert result.failure_reason == "timeout"
    assert "timed out" in result.detail.lower()
