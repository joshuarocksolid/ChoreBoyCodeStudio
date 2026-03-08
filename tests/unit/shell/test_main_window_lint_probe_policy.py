"""Unit tests for lint runtime-probe policy in MainWindow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402

pytestmark = pytest.mark.unit


def _build_window_stub() -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._diagnostics_enabled = True
    window_any._diagnostics_realtime = True
    window_any._loaded_project = None
    window_any._editor_widgets_by_path = {}
    window_any._known_runtime_modules = None
    window_any._selected_linter = constants.LINTER_PROVIDER_DEFAULT
    window_any._lint_rule_overrides = {}
    window_any._stored_lint_diagnostics = {}
    window_any._intelligence_runtime_settings = SimpleNamespace(metrics_logging_enabled=False)
    window_any._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: None)
    window_any._push_diagnostics_to_editor = lambda *_args, **_kwargs: None
    window_any._update_tab_diagnostic_indicator = lambda *_args, **_kwargs: None
    window_any._render_merged_problems_panel = lambda: None
    window_any._update_status_bar_diagnostics = lambda *_args, **_kwargs: None
    return window


def test_render_lint_manual_trigger_allows_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()
    captured: list[bool] = []

    def _fake_analyze(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return []

    monkeypatch.setattr("app.shell.main_window.analyze_python_file", _fake_analyze)

    MainWindow._render_lint_diagnostics_for_file(window, "/tmp/main.py", trigger="manual")

    assert captured == [True]


def test_render_lint_save_trigger_disables_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()
    captured: list[bool] = []

    def _fake_analyze(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return []

    monkeypatch.setattr("app.shell.main_window.analyze_python_file", _fake_analyze)

    MainWindow._render_lint_diagnostics_for_file(window, "/tmp/main.py", trigger="save")

    assert captured == [False]


def test_lint_all_open_files_disables_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _build_window_stub()
    window_any = cast(Any, window)
    window_any._editor_widgets_by_path = {
        "/tmp/a.py": SimpleNamespace(toPlainText=lambda: "import x\n"),
        "/tmp/b.py": SimpleNamespace(toPlainText=lambda: "import y\n"),
    }
    captured: list[bool] = []

    def _fake_analyze(*_args, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return []

    monkeypatch.setattr("app.shell.main_window.analyze_python_file", _fake_analyze)

    MainWindow._lint_all_open_files(window)

    assert captured == [False, False]
