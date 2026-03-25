"""Unit tests for startup runtime capability probes."""

from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from app.bootstrap import capability_probe
from app.core.models import CapabilityCheckResult, CapabilityProbeReport

pytestmark = pytest.mark.unit


def test_check_apprun_presence_reports_available_when_path_exists(tmp_path: Path) -> None:
    """AppRun check should succeed when executable path exists."""
    app_run = tmp_path / "AppRun"
    app_run.write_text("", encoding="utf-8")

    result = capability_probe.check_apprun_presence(app_run_path=app_run)

    assert result.check_id == "apprun_presence"
    assert result.is_available is True
    assert result.details["path"] == str(app_run)


def test_check_apprun_presence_reports_missing_path(tmp_path: Path) -> None:
    """AppRun check should fail clearly when path is missing."""
    missing_path = tmp_path / "missing" / "AppRun"

    result = capability_probe.check_apprun_presence(app_run_path=missing_path)

    assert result.check_id == "apprun_presence"
    assert result.is_available is False
    assert str(missing_path) in result.message


def test_check_pyside2_availability_reports_import_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """PySide2 check should succeed when import works."""

    def fake_import(module_name: str) -> object:
        assert module_name == "PySide2"
        return object()

    monkeypatch.setattr(capability_probe.importlib, "import_module", fake_import)

    result = capability_probe.check_pyside2_availability()
    assert result.check_id == "pyside2_import"
    assert result.is_available is True


def test_check_freecad_availability_reports_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """FreeCAD check should return a failed result when isolated probe errors."""
    command_calls: list[list[str]] = []
    call_kwargs: list[dict[str, object]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:  # type: ignore[no-untyped-def]
        command_calls.append(command)
        call_kwargs.append(kwargs)
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'FreeCAD'",
        )

    monkeypatch.setattr(capability_probe.subprocess, "run", fake_run)
    result = capability_probe.check_freecad_availability()

    assert command_calls
    assert command_calls[0][0] == capability_probe.sys.executable
    assert command_calls[0][1] == "-c"
    assert call_kwargs
    assert call_kwargs[0]["timeout"] == capability_probe.MODULE_IMPORT_PROBE_TIMEOUT_SECONDS
    assert result.check_id == "freecad_import"
    assert result.is_available is False
    assert "No module named 'FreeCAD'" in result.message


def test_check_freecad_availability_reports_probe_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """FreeCAD check should return a failed result when isolated probe hangs."""

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:  # type: ignore[no-untyped-def]
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=capability_probe.MODULE_IMPORT_PROBE_TIMEOUT_SECONDS,
        )

    monkeypatch.setattr(capability_probe.subprocess, "run", fake_run)
    result = capability_probe.check_freecad_availability()

    assert result.check_id == "freecad_import"
    assert result.is_available is False
    assert "timed out" in result.message
    assert str(capability_probe.MODULE_IMPORT_PROBE_TIMEOUT_SECONDS) in result.message
    assert result.details["probe"] == "subprocess"
    assert result.details["timeout_seconds"] == capability_probe.MODULE_IMPORT_PROBE_TIMEOUT_SECONDS


def test_check_freecad_availability_reports_import_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """FreeCAD check should succeed when isolated probe exits zero."""

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(capability_probe.subprocess, "run", fake_run)
    result = capability_probe.check_freecad_availability()

    assert result.check_id == "freecad_import"
    assert result.is_available is True
    assert "succeeded" in result.message


def test_check_freecad_availability_uses_apprun_fallback_after_probe_launch_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FreeCAD check should retry via AppRun when python executable probe can't launch."""
    app_run = tmp_path / "AppRun"
    app_run.write_text("#!/bin/sh\n", encoding="utf-8")
    app_run.chmod(0o755)
    monkeypatch.setattr(capability_probe.constants, "APP_RUN_PATH", str(app_run))

    command_calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:  # type: ignore[no-untyped-def]
        command_calls.append(command)
        if command[0] == capability_probe.sys.executable:
            raise OSError("Permission denied")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(capability_probe.subprocess, "run", fake_run)
    result = capability_probe.check_freecad_availability()

    assert len(command_calls) == 2
    assert command_calls[0][0] == capability_probe.sys.executable
    assert command_calls[1][0] == str(app_run.resolve())
    assert result.is_available is True
    assert "AppRun probe" in result.message


def test_check_writable_state_path_uses_resolved_state_root(tmp_path: Path) -> None:
    """State-root writability should succeed for writable locations."""
    result = capability_probe.check_writable_state_path(state_root=tmp_path / "state")

    assert result.check_id == "state_root_writable"
    assert result.is_available is True
    assert result.details["path"] == str((tmp_path / "state").resolve())


def test_check_writable_logs_path_returns_failure_on_permission_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Logs writability check should return a clear failed result on errors."""

    def fake_verify(directory: Path) -> None:
        raise PermissionError(f"Denied: {directory}")

    monkeypatch.setattr(capability_probe, "_verify_writable_directory", fake_verify)

    result = capability_probe.check_writable_logs_path(state_root=Path("/tmp/choreboy-state"))
    assert result.check_id == "global_logs_writable"
    assert result.is_available is False
    assert "Denied:" in result.message


def test_check_writable_temp_path_uses_namespaced_temp_root(tmp_path: Path) -> None:
    """Temp-root writability should use temp-root contract helpers."""
    result = capability_probe.check_writable_temp_path(temp_root=tmp_path / "temp")

    assert result.check_id == "temp_root_writable"
    assert result.is_available is True
    assert result.details["path"] == str((tmp_path / "temp").resolve())


def test_check_python_tooling_runtime_reports_versions_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        capability_probe,
        "initialize_python_tooling_runtime",
        lambda: SimpleNamespace(
            is_available=True,
            vendor_root=Path("/tmp/vendor"),
            black_available=True,
            isort_available=True,
            tomli_available=True,
            message="ready",
        ),
    )
    monkeypatch.setattr(
        capability_probe,
        "import_python_tooling_modules",
        lambda: (
            type("BlackModule", (), {"__version__": "25.11.0"})(),
            type("IsortModule", (), {"__version__": "6.1.0"})(),
            type("TomliModule", (), {"__version__": "2.3.0"})(),
        ),
    )

    result = capability_probe.check_python_tooling_runtime()
    assert result.check_id == capability_probe.PYTHON_TOOLING_RUNTIME_CHECK_ID
    assert result.is_available is True
    assert result.details["black_version"] == "25.11.0"
    assert result.details["isort_version"] == "6.1.0"
    assert result.details["tomli_version"] == "2.3.0"


def test_run_startup_capability_probe_returns_structured_failures_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe aggregation should catch check exceptions and return failed data."""

    def crash(state_root: Path | None = None) -> CapabilityCheckResult:
        _ = state_root
        raise RuntimeError("state path probe crashed")

    monkeypatch.setattr(capability_probe, "check_writable_state_path", crash)
    monkeypatch.setattr(
        capability_probe,
        "check_apprun_presence",
        lambda app_run_path=None: CapabilityCheckResult("apprun_presence", True, "ok"),
    )
    monkeypatch.setattr(
        capability_probe,
        "check_pyside2_availability",
        lambda: CapabilityCheckResult("pyside2_import", True, "ok"),
    )
    monkeypatch.setattr(
        capability_probe,
        "check_freecad_availability",
        lambda: CapabilityCheckResult("freecad_import", True, "ok"),
    )
    monkeypatch.setattr(
        capability_probe,
        "check_writable_logs_path",
        lambda state_root=None: CapabilityCheckResult("global_logs_writable", True, "ok"),
    )
    monkeypatch.setattr(
        capability_probe,
        "check_writable_temp_path",
        lambda temp_root=None: CapabilityCheckResult("temp_root_writable", True, "ok"),
    )
    monkeypatch.setattr(
        capability_probe,
        "check_python_tooling_runtime",
        lambda: CapabilityCheckResult("python_tooling_runtime", True, "ok"),
    )

    report = capability_probe.run_startup_capability_probe()
    assert isinstance(report, CapabilityProbeReport)
    assert report.all_available is False
    assert "state_root_writable" in report.failed_check_ids

    payload = report.to_dict()
    failing_item = next(item for item in payload["checks"] if item["check_id"] == "state_root_writable")
    assert failing_item["is_available"] is False
    assert "state path probe crashed" in failing_item["message"]
