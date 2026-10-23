"""Command-log dirty state and View XML commits, without Qt."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pytest

from app.features.form_builder.integration.content_source import FormContentSource, form_scope, open_document_log

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
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


def _source(text: str = _FORM) -> FormContentSource:
    return FormContentSource(open_document_log(text), text)


def _no_unsaved_buffers(_path: str) -> Optional[str]:
    return None


def _generated_form(tmp_path: Path) -> Tuple[FormContentSource, Path]:
    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    ui_path.write_text(_FORM, encoding="utf-8")
    source = FormContentSource(open_document_log(_FORM), _FORM, scope=form_scope(str(ui_path), str(tmp_path)))
    source.after_save()
    return source, forms / "ui_invoice.py"


def _append(path: Path, line: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + line, encoding="utf-8")


def test_open_is_clean_and_does_not_serialize() -> None:
    source = _source()

    assert source.is_dirty() is False
    assert source.serialize_count == 0
    text = source.current_text()
    assert source.serialize_count == 0
    assert source.current_text() == text
    assert source.serialize_count == 0
    assert "okButton" in text


def test_unchanged_xml_leaves_nothing_to_undo() -> None:
    source = _source()
    shown = source.current_text()
    source.enter_xml_mode(shown)

    assert source.leave_xml_mode() is None
    assert source.mode == "visual"
    assert source.log.can_undo() is False


def test_xml_edit_is_one_undo_step() -> None:
    source = _source()
    shown = source.current_text()
    source.enter_xml_mode(shown)
    source.xml_text_changed(shown.replace(">OK<", ">Save<"))

    assert source.is_dirty() is True
    assert source.leave_xml_mode() is None
    assert source.mode == "visual"
    assert source.log.undo_label() == "Edit XML"
    assert ">Save<" in source.current_text()
    assert source.log.undo() is True
    assert ">OK<" in source.current_text()
    assert ">Save<" not in source.current_text()


def test_invalid_xml_stays_in_xml_mode() -> None:
    source = _source()
    shown = source.current_text()
    source.enter_xml_mode(shown)
    source.xml_text_changed("<ui>")

    error = source.leave_xml_mode()

    assert error is not None
    assert "line" in error
    assert source.mode == "xml"
    assert source.current_text() == "<ui>"
    assert source.log.can_undo() is False
    assert source.log.document.root.object_name == "Form"


def test_mark_saved_clears_dirty_after_an_xml_edit() -> None:
    source = _source()
    shown = source.current_text()
    source.enter_xml_mode(shown)
    edited = shown.replace(">OK<", ">Save<")
    source.xml_text_changed(edited)
    assert source.leave_xml_mode() is None
    saved = source.current_text()

    source.mark_saved(saved)

    assert source.is_dirty() is False
    assert saved.encode("utf-8") == source.current_text().encode("utf-8")


def test_saving_unchanged_xml_adds_no_undo_step() -> None:
    source = _source()
    shown = source.current_text()
    source.enter_xml_mode(shown)

    source.mark_saved(shown)

    assert source.log.can_undo() is False
    assert source.is_dirty() is False
    assert source.mode == "xml"


def test_saved_invalid_xml_still_blocks_design() -> None:
    source = _source()
    shown = source.current_text()
    source.enter_xml_mode(shown)
    source.xml_text_changed("<ui>")

    source.mark_saved("<ui>")
    error = source.leave_xml_mode()

    assert error is not None
    assert "line" in error
    assert source.mode == "xml"
    assert source.current_text() == "<ui>"
    assert source.log.can_undo() is False
    assert source.log.document.root.object_name == "Form"

    source.cancel_xml_mode()

    assert source.mode == "visual"
    assert source.is_dirty() is True
    assert source.current_text() == _FORM
    assert source.log.document.root.object_name == "Form"


def test_consent_covers_only_the_hand_edit_it_was_given(tmp_path: Path) -> None:
    source, module = _generated_form(tmp_path)
    _append(module, "# one\n")
    first = source.save_hold(_no_unsaved_buffers)
    source.replace_hand_edits(first)
    assert [edit.path for edit in first] == [str(module)]
    assert source.save_hold(_no_unsaved_buffers) == ()

    _append(module, "# two\n")

    assert [edit.path for edit in source.save_hold(_no_unsaved_buffers)] == [str(module)]


def test_a_save_that_overwrites_the_file_uses_up_its_consent(tmp_path: Path) -> None:
    source, module = _generated_form(tmp_path)
    _append(module, "# one\n")
    edited = module.read_text(encoding="utf-8")
    source.replace_hand_edits(source.save_hold(_no_unsaved_buffers))
    source.after_save()

    module.write_text(edited, encoding="utf-8")

    assert [edit.path for edit in source.save_hold(_no_unsaved_buffers)] == [str(module)]
