"""Unit tests for scoped settings behavior in MainWindow helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
try:  # noqa: SIM105
    from app.shell.main_window import MainWindow  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    if exc.name == "PySide2.QtSvg":
        pytest.skip("PySide2.QtSvg unavailable in current environment", allow_module_level=True)
    raise

pytestmark = pytest.mark.unit


class _FakeStatusController:
    def __init__(self) -> None:
        self.project_text: str | None = None

    def set_project_state_text(self, text: str) -> None:
        self.project_text = text


class _FakeSettingsService:
    def __init__(self, *, global_payload: dict[str, Any], project_payload: dict[str, Any]) -> None:
        self._global_payload = global_payload
        self._project_payload = project_payload

    def load_global(self) -> dict[str, Any]:
        return dict(self._global_payload)

    def load_project(self, _project_root: str) -> dict[str, Any]:
        return dict(self._project_payload)


def test_load_effective_exclude_patterns_combines_global_and_project_patterns() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._settings_service = _FakeSettingsService(
        global_payload={
            constants.UI_FILE_EXCLUDES_SETTINGS_KEY: {
                constants.UI_FILE_EXCLUDES_PATTERNS_KEY: ["__pycache__", ".git"],
            }
        },
        project_payload={
            constants.UI_FILE_EXCLUDES_SETTINGS_KEY: {
                constants.UI_FILE_EXCLUDES_PATTERNS_KEY: ["build", ".git"],
            }
        },
    )

    effective = MainWindow._load_effective_exclude_patterns(window, "/tmp/project")

    assert effective == ["__pycache__", ".git", "build"]


def test_set_project_placeholder_appends_override_indicator() -> None:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._project_placeholder_label = SimpleNamespace(setText=lambda _text: None)
    status_controller = _FakeStatusController()
    window_any._status_controller = status_controller
    window_any._loaded_project = SimpleNamespace(project_root="/tmp/project")
    window_any._settings_service = _FakeSettingsService(
        global_payload={},
        project_payload={
            constants.UI_OUTPUT_SETTINGS_KEY: {
                constants.UI_OUTPUT_AUTO_OPEN_CONSOLE_ON_RUN_OUTPUT_KEY: False,
            }
        },
    )
    window_any._logger = SimpleNamespace(warning=lambda *args, **kwargs: None)

    MainWindow.set_project_placeholder(window, "Demo")

    assert status_controller.project_text == "Project: Demo (project overrides)"
