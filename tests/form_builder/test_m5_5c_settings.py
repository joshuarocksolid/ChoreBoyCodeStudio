# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Settings > Form designer (UX-TMPL-006, R3 182)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration import settings_page, template_store
from app.persistence.settings_service import SettingsService
from app.qt.QtWidgets import QTabWidget
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


def _dialog_with_page(payload: dict) -> "tuple[SettingsDialog, settings_page.FormDesignerSettingsPage]":
    settings_page.install()
    dialog = SettingsDialog(EditorSettingsSnapshot(), global_settings_payload=payload)
    tabs = dialog._tabs_widget
    assert isinstance(tabs, QTabWidget) and tabs.tabText(tabs.count() - 1) == "Form designer"
    page = tabs.widget(tabs.count() - 1)
    assert isinstance(page, settings_page.FormDesignerSettingsPage)
    return dialog, page


def test_the_shell_dialog_builds_the_page_from_its_payload_and_saves_it_with_its_own(tmp_path: Path) -> None:
    """The page's keys go into the one payload the shell saves after OK; the shell's own values and other builder keys stay."""
    dialog, page = _dialog_with_page({"form_builder": {"qt_names": True, "workbench": {"left": 300}}})
    assert page.qt_names.isChecked()
    page.template_combo.setCurrentIndex(page.template_combo.findData("project"))
    saved = dialog.apply_feature_pages({"theme_mode": "dark", "form_builder": {"qt_names": True, "workbench": {"left": 300}}})
    assert saved["theme_mode"] == "dark"
    assert saved["form_builder"]["workbench"] == {"left": 300}
    assert (saved["form_builder"]["qt_names"], saved["form_builder"]["template_scope"]) == (True, "project")
    dialog.close()


def test_the_dialog_leaves_feature_pages_out_without_a_payload() -> None:
    """Without the payload the page would show defaults and OK would save them over the user's choices."""
    settings_page.install()
    dialog = SettingsDialog(EditorSettingsSnapshot())
    tabs = dialog._tabs_widget
    assert "Form designer" not in [tabs.tabText(i) for i in range(tabs.count())]
    dialog.close()


def test_the_keyboard_link_opens_the_keyboard_tab_filtered_to_form_designer(tmp_path: Path) -> None:
    register_shortcut_commands((ShortcutCommand("form.action.probe5_5c", "Insert widget\u2026", "", "Form designer"),))
    try:
        dialog, page = _dialog_with_page({})
        dialog._tabs_widget.setCurrentIndex(0)
        page.keyboard_link.click()
        assert dialog._tabs_widget.currentIndex() == dialog._keybindings_tab_index
        assert dialog._shortcut_search_input.text() == "Form designer"
        row = dialog._shortcut_rows["form.action.probe5_5c"]
        assert not dialog._shortcut_table.isRowHidden(row), "the filter leaves the Form designer rows showing"
        other = dialog._shortcut_rows["shell.action.file.save"]
        assert dialog._shortcut_table.isRowHidden(other)
    finally:
        clear_extra_shortcut_commands()


def test_insert_shows_set_on_the_page_survives_the_insert_pane_saving_its_recent_list(tmp_path: Path) -> None:
    """The Insert pane's cached state must not put the old view back over the page's choice."""
    from app.features.form_builder.integration.insert_memory import InsertMemoryStore

    root = str((tmp_path / "state").resolve())
    store = InsertMemoryStore(root)
    store.set_view("icons")
    page = settings_page.FormDesignerSettingsPage(service=SettingsService(state_root=root))
    page.insert_combo.setCurrentIndex(page.insert_combo.findData("list"))
    page.apply()
    store.note_used("QLabel")
    saved = SettingsService(state_root=root).load_global()["form_builder"]["insert"]
    assert (saved["view"], saved["recent"]) == ("list", ["QLabel"])
