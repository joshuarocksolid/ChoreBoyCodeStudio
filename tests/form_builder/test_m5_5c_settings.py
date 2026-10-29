# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Settings > Form designer (UX-TMPL-006, R3 182)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration import settings_page, template_store
from app.persistence.settings_service import SettingsService
from app.qt.QtWidgets import QApplication, QDialog, QTabWidget
from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.shortcut_preferences import ShortcutCommand, clear_extra_shortcut_commands, register_shortcut_commands

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


def _service(tmp_path: Path) -> SettingsService:
    return SettingsService(state_root=str((tmp_path / "state").resolve()))


@pytest.mark.parity("R3-182")
def test_the_page_round_trips_its_six_choices_and_keeps_other_keys(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.update_global(
        lambda payload: {**payload, "theme_mode": "dark", "form_builder": {"workbench": {"left": 300}, "insert": {"recent": ["QLabel"]}}}
    )
    page = settings_page.FormDesignerSettingsPage(service=service)
    assert page.values() == {
        "preview_style": "",
        "preview_screen": "",
        "preview_prewarm": True,
        "insert_view": "",
        "qt_names": False,
        "template_scope": "user",
    }
    labels = [page.style_combo.itemText(0), page.screen_combo.itemText(0), page.insert_combo.itemText(0)]
    assert labels == ["Fusion · as on ChoreBoy", "ChoreBoy screen · 1366 × 768", "Icons"]
    assert [page.insert_combo.itemText(i) for i in range(3)] == ["Icons", "List", "Automatic"]
    assert [page.template_combo.itemText(i) for i in range(2)] == ["All my projects", "This project only"]
    page.screen_combo.setCurrentIndex(page.screen_combo.findData("full_hd"))
    page.insert_combo.setCurrentIndex(page.insert_combo.findData("list"))
    page.template_combo.setCurrentIndex(page.template_combo.findData("project"))
    page.prewarm.setChecked(False)
    page.qt_names.setChecked(True)
    page.apply()
    saved = service.load_global(force_refresh=True)
    assert saved["theme_mode"] == "dark"
    block = saved["form_builder"]
    assert block["workbench"] == {"left": 300} and block["insert"] == {"recent": ["QLabel"], "view": "list"}
    assert (block["preview_screen"], block["preview_prewarm"], block["qt_names"], block["template_scope"]) == (
        "full_hd",
        False,
        True,
        "project",
    )
    again = settings_page.FormDesignerSettingsPage(service=service)
    assert again.values() == page.values()
    again.insert_combo.setCurrentIndex(again.insert_combo.findData(""))
    again.apply()
    assert "view" not in service.load_global(force_refresh=True)["form_builder"]["insert"]


def test_save_as_template_starts_with_the_page_choice(tmp_path: Path) -> None:
    service = _service(tmp_path)
    template_store.use_state_root(str((tmp_path / "state").resolve()))
    try:
        assert template_store.default_scope() == "user"
        page = settings_page.FormDesignerSettingsPage(service=service)
        page.template_combo.setCurrentIndex(page.template_combo.findData("project"))
        page.apply()
        assert template_store.default_scope() == "project"
    finally:
        template_store.use_state_root(None)


def test_the_page_joins_the_settings_dialog_and_applies_after_ok(tmp_path: Path, qapp: QApplication) -> None:
    service = _service(tmp_path)
    dialog = SettingsDialog(EditorSettingsSnapshot())
    page = settings_page.attach_to_dialog(dialog, service=service)
    assert page is not None and settings_page.attach_to_dialog(dialog, service=service) is None
    tabs = dialog._tabs_widget
    assert isinstance(tabs, QTabWidget) and tabs.tabText(tabs.count() - 1) == "Form designer"
    page.qt_names.setChecked(True)
    dialog.accept()
    for _ in range(4):
        qapp.processEvents()
    assert service.load_global(force_refresh=True)["form_builder"]["qt_names"] is True


def test_the_keyboard_link_opens_the_keyboard_tab_filtered_to_form_designer(tmp_path: Path) -> None:
    register_shortcut_commands((ShortcutCommand("form.action.probe5_5c", "Insert widget\u2026", "", "Form designer"),))
    try:
        dialog = SettingsDialog(EditorSettingsSnapshot())
        _check_keyboard_link(dialog, tmp_path)
    finally:
        clear_extra_shortcut_commands()


def _check_keyboard_link(dialog: SettingsDialog, tmp_path: Path) -> None:
    page = settings_page.attach_to_dialog(dialog, service=_service(tmp_path))
    dialog._tabs_widget.setCurrentIndex(0)
    page.keyboard_link.click()
    assert dialog._tabs_widget.currentIndex() == dialog._keybindings_tab_index
    assert dialog._shortcut_search_input.text() == "Form designer"
    row = dialog._shortcut_rows["form.action.probe5_5c"]
    assert not dialog._shortcut_table.isRowHidden(row), "the filter leaves the Form designer rows showing"
    other = dialog._shortcut_rows["shell.action.file.save"]
    assert dialog._shortcut_table.isRowHidden(other)


def test_the_shells_dialog_gets_the_tab_when_it_shows(tmp_path: Path, qapp: QApplication) -> None:
    settings_page.install()
    dialog = SettingsDialog(EditorSettingsSnapshot())
    assert isinstance(dialog, QDialog) and dialog.objectName() == settings_page.DIALOG_NAME
    dialog.show()
    for _ in range(3):
        qapp.processEvents()
    tabs = dialog._tabs_widget
    assert [tabs.tabText(i) for i in range(tabs.count())][-1] == "Form designer"
    dialog.close()


@pytest.mark.xfail(
    strict=True,
    reason="Owner: shell (settings dialog). No settings-page registration exists; settings_page.install() watches for the dialog until one does.",
)
def test_the_shell_registers_settings_pages_itself() -> None:
    import importlib

    importlib.import_module("app.shell.settings_pages")
