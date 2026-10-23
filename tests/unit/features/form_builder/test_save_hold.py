"""A form save that would overwrite a hand edit stops until the user chooses Replace."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.features.form_builder.integration.content_source import form_scope, open_document_log  # noqa: E402
from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.features.form_builder.integration.save_pipeline import finish_save  # noqa: E402
from app.features.form_builder.integration.surface import FormSurface  # noqa: E402
from app.qt.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget  # noqa: E402
from app.shell.save_workflow import SaveWorkflow  # noqa: E402
from app.shell.tab_content_providers import TabContentProviderRegistry, TabSurfaceRequest  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.support.shell_host_stubs import save_workflow_stub  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_SHOP_NOTE = "\n# shop note\n"


class _OpenForm:
    def __init__(self, tmp_path: Path, parent: QWidget) -> None:
        forms = tmp_path / "forms"
        forms.mkdir()
        self.ui_path = forms / "invoice.ui"
        self.ui_path.write_text(_FORM, encoding="utf-8")
        self.module = forms / "ui_invoice.py"
        scope = form_scope(str(self.ui_path), str(tmp_path))
        finish_save(scope, open_document_log(_FORM).document, _FORM)
        self.module.write_text(self.module.read_text(encoding="utf-8") + _SHOP_NOTE, encoding="utf-8")
        self.hand_edited = self.module.read_text(encoding="utf-8")

        self.manager = EditorManager()
        opened = self.manager.open_file(str(self.ui_path))
        registry = TabContentProviderRegistry()
        self.workflow: SaveWorkflow = save_workflow_stub(self.manager, registry=registry)
        app = QApplication.instance()
        assert app is not None
        surface = FormTabProvider().create_surface(
            TabSurfaceRequest(
                file_path=str(self.ui_path),
                initial_text=_FORM,
                parent=parent,
                theme=tokens_from_palette(app.palette(), force_mode="light"),
                create_source_editor=lambda: None,  # type: ignore[arg-type,return-value]
                open_linked_file=lambda _linked: None,
                project_root=str(tmp_path),
                publish_problems=lambda _path, _rows: None,
                show_problems=lambda: None,
                save_file=self.workflow.save_tab,
                unsaved_text=lambda _path: None,
            )
        )
        assert isinstance(surface, FormSurface)
        self.surface = surface
        opened.tab.content_source = surface.content_source()
        registry.bind(str(self.ui_path), surface, "form-builder")
        surface.restore_text(_FORM.replace(">OK<", ">Save<"), "history")

    def notice(self) -> Tuple[bool, str]:
        bar = self.surface.findChild(QFrame, "formBuilder.notice")
        label = self.surface.findChild(QLabel, "formBuilder.noticeText")
        assert bar is not None and label is not None
        return not bar.isHidden(), label.text()

    def click(self, label: str) -> None:
        buttons = [
            button
            for button in self.surface.findChildren(QPushButton, "formBuilder.noticeButton")
            if button.text() == label
        ]
        assert len(buttons) == 1
        buttons[0].click()


def test_cancel_on_a_held_save_writes_nothing(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    parent = QWidget()
    form = _OpenForm(tmp_path, parent)
    ui_before = form.ui_path.read_bytes()

    assert form.workflow.save_tab(str(form.ui_path)) is False
    shown, text = form.notice()
    assert shown and text.startswith("ui_invoice.py has edits made by hand.")
    form.click("Cancel save")

    assert form.notice()[0] is False
    assert form.ui_path.read_bytes() == ui_before
    assert form.module.read_text(encoding="utf-8") == form.hand_edited
    tab = form.manager.get_tab(str(form.ui_path))
    assert tab is not None and tab.is_dirty
    form.surface.release()


def test_replace_saves_over_the_hand_edit_after_copying_it_aside(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    del qapp
    parent = QWidget()
    form = _OpenForm(tmp_path, parent)
    assert form.workflow.save_tab(str(form.ui_path)) is False

    form.click("Replace")

    assert b">Save<" in form.ui_path.read_bytes()
    assert _SHOP_NOTE not in form.module.read_text(encoding="utf-8")
    copies = list((tmp_path / "cbcs" / "form_builder" / "hand_edits").glob("ui_invoice.*.py.txt"))
    assert [copy.read_text(encoding="utf-8") for copy in copies] == [form.hand_edited]
    tab = form.manager.get_tab(str(form.ui_path))
    assert tab is not None and not tab.is_dirty
    form.surface.release()
