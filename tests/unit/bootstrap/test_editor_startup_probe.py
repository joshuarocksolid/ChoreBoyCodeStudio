"""Integration tests for startup capability probe wiring."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import run_editor
from app.bootstrap.logging_setup import LoggingResult, TIER_PRIMARY
from app.core.models import CapabilityCheckResult, CapabilityProbeReport

pytestmark = pytest.mark.unit

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


def test_main_runs_minimal_startup_probe_and_stores_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """Editor startup should invoke minimal probe and keep results available."""
    logger = _RecordingLogger()
    report = CapabilityProbeReport(
        checks=[
            CapabilityCheckResult("apprun_presence", True, "ok"),
            CapabilityCheckResult("qt_binding_import", True, "ok"),
        ]
    )
    probe_calls = {"count": 0}

    def fake_probe() -> CapabilityProbeReport:
        probe_calls["count"] += 1
        return report

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "migrate_legacy_global_state", lambda: object())
    monkeypatch.setattr(run_editor, "_log_migration_outcome", lambda logger, outcome: None)
    monkeypatch.setattr(run_editor, "configure_app_logging", lambda: _FAKE_LOGGING_RESULT)
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(run_editor, "run_minimal_startup_capability_probe", fake_probe)
    monkeypatch.setattr(
        run_editor,
        "initialize_tree_sitter_runtime",
        lambda: SimpleNamespace(is_available=True, message="ok"),
    )
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
    monkeypatch.setattr(run_editor, "migrate_legacy_global_state", lambda: object())
    monkeypatch.setattr(run_editor, "_log_migration_outcome", lambda logger, outcome: None)
    monkeypatch.setattr(run_editor, "configure_app_logging", lambda: _FAKE_LOGGING_RESULT)
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(run_editor, "run_minimal_startup_capability_probe", lambda: report)
    monkeypatch.setattr(
        run_editor,
        "initialize_tree_sitter_runtime",
        lambda: SimpleNamespace(is_available=True, message="ok"),
    )
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
            CapabilityCheckResult("qt_binding_import", True, "ok"),
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
    monkeypatch.setattr(run_editor, "migrate_legacy_global_state", lambda: object())
    monkeypatch.setattr(run_editor, "_log_migration_outcome", lambda logger, outcome: None)
    monkeypatch.setattr(run_editor, "configure_app_logging", lambda: _FAKE_LOGGING_RESULT)
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(run_editor, "run_minimal_startup_capability_probe", fake_probe)
    monkeypatch.setattr(
        run_editor,
        "initialize_tree_sitter_runtime",
        lambda: SimpleNamespace(is_available=True, message="ok"),
    )
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

    def processEvents(self) -> None:
        self.process_events_calls = getattr(self, "process_events_calls", 0) + 1


class _FakeMainWindow:
    created: list["_FakeMainWindow"] = []

    def __init__(self, startup_report: CapabilityProbeReport | None = None) -> None:
        self.startup_report = startup_report
        self.show_calls = 0
        type(self).created.append(self)

    def show(self) -> None:
        self.show_calls += 1

    def showMaximized(self) -> None:
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


def test_refresh_startup_capability_report_updates_global_and_notifies_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deferred refresh should update global report and notify callback."""
    report = CapabilityProbeReport(
        checks=[CapabilityCheckResult("freecad_import", True, "ok")]
    )
    seen: list[CapabilityProbeReport] = []

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "run_startup_capability_probe", lambda: report)
    run_editor.set_startup_report_refresh_callback(lambda payload: seen.append(payload))
    try:
        refreshed = run_editor.refresh_startup_capability_report()
    finally:
        run_editor.set_startup_report_refresh_callback(None)

    assert refreshed == report
    assert run_editor.get_last_startup_capability_report() == report
    assert seen == [report]


def test_main_shows_startup_failure_dialog_when_window_construction_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = _RecordingLogger()
    presented: list[tuple[str, str, str]] = []

    def fail_start() -> int:
        raise RuntimeError("window boom")

    def presenter(summary: str, log_path: str, details: str) -> bool:
        presented.append((summary, log_path, details))
        return True

    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "migrate_legacy_global_state", lambda: object())
    monkeypatch.setattr(run_editor, "_log_migration_outcome", lambda logger, outcome: None)
    monkeypatch.setattr(
        run_editor,
        "configure_app_logging",
        lambda: LoggingResult(log_path=Path("/tmp/cbcs-editor.log"), tier=TIER_PRIMARY, warnings=[]),
    )
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(
        run_editor,
        "run_minimal_startup_capability_probe",
        lambda: CapabilityProbeReport(checks=[]),
    )
    monkeypatch.setattr(
        run_editor,
        "initialize_tree_sitter_runtime",
        lambda: SimpleNamespace(is_available=True, message="ok"),
    )
    monkeypatch.setattr(run_editor, "_start_editor", fail_start)
    monkeypatch.setattr(run_editor, "present_startup_failure_dialog", presenter)

    assert run_editor.main() == 1
    assert presented
    summary, log_path, details = presented[0]
    assert "window boom" in summary
    assert log_path == "/tmp/cbcs-editor.log"
    assert "window boom" in details
    assert "Editor startup failed." in logger.exception_messages


def test_main_continues_when_tree_sitter_initialization_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = _RecordingLogger()
    monkeypatch.setattr(run_editor, "_LAST_STARTUP_CAPABILITY_REPORT", None)
    monkeypatch.setattr(run_editor, "migrate_legacy_global_state", lambda: object())
    monkeypatch.setattr(run_editor, "_log_migration_outcome", lambda logger, outcome: None)
    monkeypatch.setattr(run_editor, "configure_app_logging", lambda: _FAKE_LOGGING_RESULT)
    monkeypatch.setattr(run_editor, "get_subsystem_logger", lambda _: logger)
    monkeypatch.setattr(
        run_editor,
        "run_minimal_startup_capability_probe",
        lambda: CapabilityProbeReport(checks=[]),
    )

    def fail_treesitter() -> SimpleNamespace:
        raise RuntimeError("grammar missing")

    monkeypatch.setattr(run_editor, "initialize_tree_sitter_runtime", fail_treesitter)
    def fail_if_called(*_args: object) -> bool:
        raise AssertionError("optional init must not open the last-resort dialog")

    monkeypatch.setattr(run_editor, "_start_editor", lambda: 0)
    monkeypatch.setattr(run_editor, "present_startup_failure_dialog", fail_if_called)

    assert run_editor.main() == 0
    assert "Tree-sitter initialization failed." in logger.exception_messages
