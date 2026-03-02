"""Unit tests for runtime module probe and cache."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.bootstrap import runtime_module_probe
from app.bootstrap.runtime_module_probe import (
    RuntimeModuleProbeResult,
    load_cached_runtime_modules,
    probe_and_cache_runtime_modules,
    probe_runtime_modules,
    resolve_probe_runtime_path,
    save_runtime_modules_cache,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# probe_runtime_modules
# ---------------------------------------------------------------------------


class TestProbeRuntimeModules:
    """Tests for the subprocess-based runtime probe."""

    def test_successful_probe_returns_modules(self, monkeypatch: pytest.MonkeyPatch) -> None:
        modules_json = json.dumps(["FreeCAD", "os", "sys"])
        call_count = 0

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(command, 0, stdout="3.9.2\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout=modules_json + "\n", stderr="")

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        result = probe_runtime_modules("/opt/freecad/AppRun")

        assert result.success is True
        assert result.modules == frozenset(["FreeCAD", "os", "sys"])
        assert result.runtime_path == "/opt/freecad/AppRun"
        assert result.python_version == "3.9.2"
        assert result.error_message == ""

    def test_probe_nonzero_exit_returns_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        call_count = 0

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(command, 0, stdout="3.9.2\n", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="ImportError: boom")

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        result = probe_runtime_modules("/opt/freecad/AppRun")

        assert result.success is False
        assert result.modules == frozenset()
        assert "exited with code 1" in result.error_message
        assert "ImportError: boom" in result.error_message

    def test_probe_timeout_returns_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        call_count = 0

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(command, 0, stdout="3.9.2\n", stderr="")
            raise subprocess.TimeoutExpired(command, 30)

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        result = probe_runtime_modules("/opt/freecad/AppRun")

        assert result.success is False
        assert "timed out" in result.error_message.lower()

    def test_probe_oserror_returns_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise OSError("No such file")

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        result = probe_runtime_modules("/nonexistent/AppRun")

        assert result.success is False
        assert "No such file" in result.error_message

    def test_probe_bad_json_returns_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        call_count = 0

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(command, 0, stdout="3.9.2\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="NOT JSON\n", stderr="")

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        result = probe_runtime_modules("/opt/freecad/AppRun")

        assert result.success is False
        assert "parse probe output" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------


class TestCacheRoundTrip:
    """Tests for save/load of cached runtime modules."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        result = RuntimeModuleProbeResult(
            modules=frozenset(["FreeCAD", "os", "json"]),
            runtime_path="/opt/freecad/AppRun",
            python_version="3.9.2",
            probed_at="2026-03-02T17:00:00+00:00",
            success=True,
        )
        save_runtime_modules_cache(result, state_root=tmp_path)

        loaded = load_cached_runtime_modules(state_root=tmp_path)
        assert loaded == frozenset(["FreeCAD", "os", "json"])

    def test_load_returns_none_when_no_cache(self, tmp_path: Path) -> None:
        loaded = load_cached_runtime_modules(state_root=tmp_path)
        assert loaded is None

    def test_load_returns_none_on_corrupt_cache(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "runtime_modules.json").write_text("NOT JSON", encoding="utf-8")

        loaded = load_cached_runtime_modules(state_root=tmp_path)
        assert loaded is None

    def test_cache_file_contains_metadata(self, tmp_path: Path) -> None:
        result = RuntimeModuleProbeResult(
            modules=frozenset(["FreeCAD"]),
            runtime_path="/opt/freecad/AppRun",
            python_version="3.9.2",
            probed_at="2026-03-02T17:00:00+00:00",
            success=True,
        )
        path = save_runtime_modules_cache(result, state_root=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["runtime_path"] == "/opt/freecad/AppRun"
        assert data["python_version"] == "3.9.2"
        assert "FreeCAD" in data["modules"]


# ---------------------------------------------------------------------------
# resolve_probe_runtime_path
# ---------------------------------------------------------------------------


class TestResolveProbeRuntimePath:
    """Tests for runtime path resolution fallback."""

    def test_returns_apprun_when_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        app_run = tmp_path / "AppRun"
        app_run.write_text("", encoding="utf-8")
        monkeypatch.setattr(runtime_module_probe.constants, "APP_RUN_PATH", str(app_run))

        assert resolve_probe_runtime_path() == str(app_run.resolve())

    def test_falls_back_to_sys_executable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runtime_module_probe.constants, "APP_RUN_PATH", "/nonexistent/AppRun")

        import sys
        assert resolve_probe_runtime_path() == sys.executable


# ---------------------------------------------------------------------------
# probe_and_cache_runtime_modules
# ---------------------------------------------------------------------------


class TestProbeAndCache:
    """Tests for the convenience probe-then-cache function."""

    def test_success_caches_and_returns_modules(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        modules_json = json.dumps(["FreeCAD", "os"])
        call_count = 0

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(command, 0, stdout="3.9.2\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout=modules_json, stderr="")

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        modules = probe_and_cache_runtime_modules(
            runtime_path="/opt/freecad/AppRun",
            state_root=tmp_path,
        )

        assert modules == frozenset(["FreeCAD", "os"])
        assert load_cached_runtime_modules(state_root=tmp_path) == frozenset(["FreeCAD", "os"])

    def test_failure_returns_cached_if_available(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        old_result = RuntimeModuleProbeResult(
            modules=frozenset(["FreeCAD"]),
            runtime_path="/opt/freecad/AppRun",
            python_version="3.9.2",
            probed_at="2026-03-01T00:00:00+00:00",
            success=True,
        )
        save_runtime_modules_cache(old_result, state_root=tmp_path)

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise OSError("gone")

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        modules = probe_and_cache_runtime_modules(
            runtime_path="/opt/freecad/AppRun",
            state_root=tmp_path,
        )

        assert modules == frozenset(["FreeCAD"])

    def test_failure_without_cache_returns_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise OSError("gone")

        monkeypatch.setattr(runtime_module_probe.subprocess, "run", fake_run)

        modules = probe_and_cache_runtime_modules(
            runtime_path="/opt/freecad/AppRun",
            state_root=tmp_path,
        )

        assert modules == frozenset()
