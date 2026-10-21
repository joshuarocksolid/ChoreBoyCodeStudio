"""Startup keeps a window when history or the plugin host cannot start."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication  # noqa: E402

from app.persistence.local_history_store import LocalHistoryStore  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from testing.main_window_test_helpers import prepare_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _startup_text(window: MainWindow) -> str:
    from app.qt.QtWidgets import QLabel

    startup = window.findChild(QLabel, "shell.startupStatusLabel")
    assert startup is not None
    return startup.text()


def test_main_window_builds_when_local_history_database_is_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _qapp: QApplication,
) -> None:
    def refuse(self: LocalHistoryStore, state_root: object = None, retention_policy: object = None) -> None:
        del self, state_root, retention_policy
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(LocalHistoryStore, "__init__", refuse)
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=_qapp)
    try:
        text = _startup_text(window)
        assert "Local history is off:" in text
        assert "database is locked" in text
    finally:
        shutdown_main_window_for_test(window, _qapp)


def test_main_window_builds_when_plugin_host_popen_is_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _qapp: QApplication,
) -> None:
    presented: list[str] = []

    def deny_start(self: object, *, env: object = None) -> int:
        del self, env
        raise PermissionError(13, "Permission denied", "/opt/freecad/AppRun")

    monkeypatch.setattr("app.plugins.runtime_manager.background_runtime_disabled", lambda: False)
    monkeypatch.setattr("app.plugins.host_supervisor.PluginHostSupervisor.start", deny_start)
    monkeypatch.setattr(
        "app.shell.main_window_composition_phases.present_plugin_host_unavailable",
        lambda _parent, detail: presented.append(detail),
    )

    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    prepare_main_window_for_test(window, app=_qapp)
    try:
        assert presented
        assert "Permission denied" in presented[0]
        assert "/opt/freecad/AppRun" in presented[0]
        text = _startup_text(window)
        assert "Permission denied" in text
    finally:
        shutdown_main_window_for_test(window, _qapp)
