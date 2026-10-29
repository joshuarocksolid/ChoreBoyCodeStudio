# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Save as template (UX-TMPL-001) and New form from a template inside a real window (UX-TMPL-003, UX-TMPL-004)."""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.project import user_templates as ut
from app.features.form_builder.integration import new_form, template_store
from app.features.form_builder.integration.form_menu_ext import templates as menu_item
from app.features.form_builder.qtside.dialogs.save_template import CAPTION, DESCRIPTION_PLACEHOLDER, SaveTemplatePopover
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session
from tests.form_builder.qtside.test_m5_5c_k22 import _SHOP, _form_action

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def _window(tmp_path: Path, qapp: QApplication, text: str = _SHOP):  # type: ignore[no-untyped-def]
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True, exist_ok=True)
    template_store.use_state_root(str((tmp_path / "state").resolve()))
    return _session(tmp_path, qapp, text)


def test_the_popover_offers_the_spec_fields_and_defaults(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _window(tmp_path, qapp)
    try:
        popover = menu_item.open_popover(kb.surface)
        assert popover.name.text() == "Shop window"
        assert popover.description.text() == "" and popover.description.placeholderText() == DESCRIPTION_PLACEHOLDER
        assert popover.all_projects.isChecked() and popover.this_project.isEnabled()
        assert popover.caption.text() == CAPTION
        assert (popover.save_button.text(), popover.cancel_button.text()) == ("Save template", "Cancel")
        popover.name.setText("   ")
        assert not popover.save_button.isEnabled()
        popover.close()
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)


def test_the_default_name_is_the_window_title_else_the_file_in_words(tmp_path: Path, qapp: QApplication) -> None:
    untitled = _SHOP.replace('  <property name="windowTitle"><string>Shop window</string></property>\n', "")
    window, kb, guard = _window(tmp_path, qapp, untitled)
    try:
        assert menu_item.default_name(kb.surface) == "Customer"
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)


def test_saving_toasts_where_the_template_went_and_a_name_in_use_asks(tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    window, kb, guard = _window(tmp_path, qapp)
    try:
        said: List[str] = []
        monkeypatch.setattr(kb.surface, "show_plain", said.append)
        first = menu_item.save_now(kb.surface, "Shop window", "Till", ut.SCOPE_USER)
        assert said == ["Saved the template “Shop window”. It's on the New form tab."]
        asked: List[str] = []
        monkeypatch.setattr(menu_item, "ask_replace", lambda parent, name: asked.append(name) or False)
        assert menu_item.save_now(kb.surface, "shop WINDOW", "Other", ut.SCOPE_USER) is None
        assert asked == ["Shop window"]
        assert ut.read_template(first.folder, ut.SCOPE_USER).description == "Till"
        monkeypatch.setattr(menu_item, "ask_replace", lambda parent, name: True)
        again = menu_item.save_now(kb.surface, "shop WINDOW", "Other", ut.SCOPE_USER)
        assert again.folder == first.folder and again.description == "Other"
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)


def test_a_declined_replace_brings_the_popover_back_with_the_typed_answers(
    tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, kb, guard = _window(tmp_path, qapp)
    try:
        menu_item.save_now(kb.surface, "Shop window", "", ut.SCOPE_USER)
        monkeypatch.setattr(menu_item, "ask_replace", lambda parent, name: False)
        popover = menu_item.open_popover(kb.surface, name="Shop window", description="Second try")
        popover.submit()
        back = [w for w in kb.surface.findChildren(SaveTemplatePopover) if w.isVisible()]
        assert back and back[0].description.text() == "Second try"
        back[0].close()
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)


def test_the_thumbnail_is_the_canvas_page_at_200_by_120_at_most(tmp_path: Path, qapp: QApplication) -> None:
    window, kb, guard = _window(tmp_path, qapp)
    try:
        from app.qt.QtGui import QImage

        image = QImage.fromData(menu_item.thumbnail_png(kb.surface))
        assert not image.isNull() and image.width() <= 200 and image.height() <= 120
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)


def test_new_form_from_a_template_toasts_a_missing_module_and_selects_the_root(
    tmp_path: Path, qapp: QApplication
) -> None:
    custom = _SHOP.replace(
        '<widget class="QLabel" name="logoLabel">',
        '<widget class="TillDisplay" name="logoLabel">',
    ).replace(
        " <resources>",
        ' <customwidgets><customwidget><class>TillDisplay</class><extends>QLabel</extends>'
        "<header>widgets.till_display</header></customwidget></customwidgets>\n <resources>",
    )
    window, kb, guard = _window(tmp_path, qapp, custom)
    try:
        info = menu_item.save_now(kb.surface, "Till window", "", ut.SCOPE_USER)
        root = tmp_path / "shop"
        said: List[str] = []
        original = type(kb.surface).show_plain
        type(kb.surface).show_plain = lambda self, sentence: said.append(sentence)  # type: ignore[method-assign]
        try:
            result = new_form.perform_create(
                window, template="widget", stem="back_office", directory=str(root / "forms"), saved_template=info
            )
        finally:
            type(kb.surface).show_plain = original  # type: ignore[method-assign]
        qapp.processEvents()
        assert result.refused is None
        assert said and said[-1] == "TillDisplay comes from widgets.till_display, which isn't in this project. The form shows a stand-in."
        assert not (root / "widgets").exists(), "an own class's code is not copied"
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)


def test_rename_and_description_from_the_card_menu_change_only_template_json(
    tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, kb, guard = _window(tmp_path, qapp)
    try:
        info = menu_item.save_now(kb.surface, "Shop window", "Till", ut.SCOPE_USER)
        window._open_new_form()
        qapp.processEvents()
        surface = window._tab_content_registry.surface_for_path(str(tmp_path / "shop" / "cbcs" / "new-form.cbcs-tab"))
        answers = iter(["Till window", "Counter and tills"])
        monkeypatch.setattr(new_form, "ask_text", lambda parent, title, label, value: next(answers))
        form_before = Path(info.form_path).read_bytes()
        surface._panel.template_action_requested.emit("rename", info.card_key)
        surface._panel.template_action_requested.emit("describe", info.card_key)
        qapp.processEvents()
        again = ut.read_template(info.folder, ut.SCOPE_USER)
        assert (again.name, again.description) == ("Till window", "Counter and tills")
        assert Path(info.form_path).read_bytes() == form_before
        assert surface._panel.card(info.card_key).title() == "Till window"
        label = surface._panel.findChild(QLabel, "formBuilder.newForm.status")
        assert label.text() == ""
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)


def test_a_declined_delete_keeps_the_folder(tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    window, kb, guard = _window(tmp_path, qapp)
    try:
        info = menu_item.save_now(kb.surface, "Shop window", "", ut.SCOPE_USER)
        window._open_new_form()
        qapp.processEvents()
        surface = window._tab_content_registry.surface_for_path(str(tmp_path / "shop" / "cbcs" / "new-form.cbcs-tab"))
        monkeypatch.setattr(new_form, "ask_delete_template", lambda parent, name: False)
        surface._panel.template_action_requested.emit("delete", info.card_key)
        assert Path(info.folder).is_dir()
        QTest.qWait(1)
    finally:
        template_store.use_state_root(None)
        _close(window, qapp, guard)
