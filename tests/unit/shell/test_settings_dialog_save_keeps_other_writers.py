"""Settings OK must not drop keys another writer saved while the dialog was open."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.persistence.settings_service import SettingsService
from app.qt.QtWidgets import QDialog, QWidget
from app.shell import file_project_commands_workflow as workflow_module
from app.shell import settings_pages
from app.shell.python_tooling_status_copy import UNKNOWN_SETTINGS_COPY

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


class _Host:
    def __init__(self, service: SettingsService) -> None:
        self._service = service
        self.applied: list[Any] = []

    def settings_service(self) -> SettingsService:
        return self._service

    def current_project_root(self) -> None:
        return None

    def settings_dialog_python_tooling_copy(self) -> Any:
        return UNKNOWN_SETTINGS_COPY

    def dialog_parent(self) -> None:
        return None

    def shell_theme_workflow(self) -> Any:
        return SimpleNamespace(resolve_theme_tokens=lambda: None)

    def settings_apply_workflow(self) -> Any:
        return SimpleNamespace(apply_after_settings_saved=lambda **kwargs: self.applied.append(kwargs))


def test_ok_keeps_keys_saved_while_open_and_saves_registered_pages_with_the_dialog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "state"
    service = SettingsService(state_root=root)
    service.save_global({"form_builder": {"workbench": {"left": 300}}})

    def build(parent: QWidget, payload: Any) -> QWidget:
        page = QWidget(parent)
        page.setProperty("seen", payload.get("form_builder", {}).get("workbench", {}).get("left"))
        return page

    def apply(page: QWidget, payload: dict) -> dict:
        block = dict(payload.get("form_builder", {}))
        block["qt_names"] = True
        block["seen"] = page.property("seen")
        return {**payload, "form_builder": block}

    settings_pages.register_settings_page(settings_pages.SettingsPage("probe", "Probe", build, apply))

    def exec_while_another_writer_saves(dialog: QDialog) -> int:
        SettingsService(state_root=root).update_global(lambda p: {**p, "run": {"recent_argv": ["-v"]}})
        return QDialog.Accepted

    monkeypatch.setattr(workflow_module, "exec_qt", exec_while_another_writer_saves)
    try:
        workflow_module.FileProjectCommandsWorkflow(_Host(service))._open_settings_dialog()  # pyright: ignore[reportPrivateUsage, reportArgumentType]
    finally:
        settings_pages.unregister_settings_page("probe")

    on_disk = SettingsService(state_root=root).load_global()
    assert on_disk["run"] == {"recent_argv": ["-v"]}
    assert on_disk["form_builder"]["workbench"] == {"left": 300}
    assert on_disk["form_builder"]["qt_names"] is True and on_disk["form_builder"]["seen"] == 300
