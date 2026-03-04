"""Integration tests for startup capability probe wiring."""

import pytest

import run_editor
from app.bootstrap.logging_setup import LoggingResult, TIER_PRIMARY
from app.core.models import CapabilityCheckResult, CapabilityProbeReport

pytestmark = pytest.mark.integration

_FAKE_LOGGING_RESULT = LoggingResult(log_path=None, tier=TIER_PRIMARY, warnings=[])


class _RecordingLogger:
    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.exception_messages: list[str] = []

    def info(self, message: str, *args: object) -> None:
        self.info_messages.append(message % args if args else message)

    def warning(self, message: str, *args: object) -> None:
        self.warning_messages.append(message % args if args else message)

    def exception(self, message: str, *args: object) -> None:
        self.exception_messages.append(message % args if args else message)


def test_main_runs_startup_probe_and_stores_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """Editor startup should invoke probe and keep structured results available."""
    logger = _RecordingLogger()
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_presence", True, "ok"),
            CapabilityCheckResult("pyside2_import", True, "ok"),
        ]
    )
    probe_calls = {"count": 0}

    def fake_probe() -> CapabilityProbeReport:
        probe_calls["count"] += 1
        return report

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "configure_app_logging", lambda: _FAKE_LOGGING_RESULT)
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(run_editor, "run_startup_capability_probe", fake_probe)
    monkeypatch.setattr(run_editor, "_start_editor", lambda: 0)

    assert run_editor.main() == 0
    assert probe_calls["count"] == 1
    assert run_editor.get_last_startup_capability_report() == report


def test_main_logs_failed_probe_checks_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed checks should emit clear warnings instead of failing silently."""
    logger = _RecordingLogger()
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_presence", True, "ok"),
            CapabilityCheckResult("freecad_import", False, "Failed to import FreeCAD: missing"),
        ]
    )

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "configure_app_logging", lambda: _FAKE_LOGGING_RESULT)
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(run_editor, "run_startup_capability_probe", lambda: report)
    monkeypatch.setattr(run_editor, "_start_editor", lambda: 0)

    assert run_editor.main() == 0
    assert any("Startup capability probe reported issues:" in message for message in logger.warning_messages)
    assert any("Capability check failed [freecad_import]" in message for message in logger.warning_messages)


def test_main_sets_startup_report_before_shell_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup report should be available before the shell launch boundary executes."""
    logger = _RecordingLogger()
    call_order: list[str] = []
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_presence", True, "ok"),
            CapabilityCheckResult("pyside2_import", True, "ok"),
        ]
    )

    def fake_probe() -> CapabilityProbeReport:
        call_order.append("probe")
        return report

    def fake_start_editor() -> int:
        call_order.append("shell")
        assert run_editor.get_last_startup_capability_report() == report
        return 0

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "configure_app_logging", lambda: _FAKE_LOGGING_RESULT)
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(run_editor, "run_startup_capability_probe", fake_probe)
    monkeypatch.setattr(run_editor, "_start_editor", fake_start_editor)

    assert run_editor.main() == 0
    assert call_order == ["probe", "shell"]


class _FakeQApplication:
    _instance: "_FakeQApplication | None" = None

    def __init__(self, argv: list[str]) -> None:
        self.argv = list(argv)
        self.exec_calls = 0
        type(self)._instance = self

    @classmethod
    def instance(cls) -> "_FakeQApplication | None":
        return cls._instance

    def exec_(self) -> int:
        self.exec_calls += 1
        return 11


class _FakeMainWindow:
    created: list["_FakeMainWindow"] = []

    def __init__(self, startup_report: CapabilityProbeReport | None = None) -> None:
        self.startup_report = startup_report
        self.show_calls = 0
        type(self).created.append(self)

    def show(self) -> None:
        self.show_calls += 1


def test_start_editor_launches_main_window_with_startup_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shell launch should pass startup capability report into MainWindow."""
    report = CapabilityProbeReport(
        checks=[CapabilityCheckResult("apprun_presence", True, "ok")]
    )

    _FakeQApplication._instance = None
    _FakeMainWindow.created.clear()

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", report)
    monkeypatch.setattr(run_editor, "_load_qt_runtime", lambda: (_FakeQApplication, _FakeMainWindow))
    monkeypatch.setattr(run_editor.sys, "argv", ["run_editor.py"])

    assert run_editor._start_editor() == 11
    assert len(_FakeMainWindow.created) == 1
    assert _FakeMainWindow.created[0].startup_report == report
    assert _FakeMainWindow.created[0].show_calls == 1
    assert _FakeQApplication.instance() is not None
    assert _FakeQApplication.instance().exec_calls == 1


def test_start_editor_does_not_require_project_to_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shell launch should still run when no project/report data is loaded."""
    _FakeQApplication._instance = None
    _FakeMainWindow.created.clear()

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "_load_qt_runtime", lambda: (_FakeQApplication, _FakeMainWindow))
    monkeypatch.setattr(run_editor.sys, "argv", ["run_editor.py"])

    assert run_editor._start_editor() == 11
    assert len(_FakeMainWindow.created) == 1
    assert _FakeMainWindow.created[0].startup_report is None
