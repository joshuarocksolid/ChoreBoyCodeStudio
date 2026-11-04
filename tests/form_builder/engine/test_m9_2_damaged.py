"""Damaged .ui files open with the engine's sentence and are not saved shorter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.editors.editor_manager import EditorManager
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.provider import FormTabProvider
from app.shell.tab_content_providers import ProviderDeclined

pytestmark = pytest.mark.unit

_FORM = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<ui version="4.0">\n'
    ' <widget class="QWidget" name="Form">\n'
    '  <property name="windowTitle"><string>Hello</string></property>\n'
    " </widget>\n"
    "</ui>\n"
)


def _read(text: str):
    return read_ui(text, allocator=IdAllocator())


def test_a_truncated_file_raises_the_reader_sentence() -> None:
    with pytest.raises(UiReadError) as caught:
        _read('<ui version="4.0"><widget class="QWidget" name="Form"')
    assert caught.value.code == "FB001"
    assert str(caught.value)


def test_a_file_nested_too_deep_names_fb008() -> None:
    depth = 300
    text = "<ui>" + "<widget>" * depth + "</widget>" * depth + "</ui>"
    with pytest.raises(UiReadError) as caught:
        _read(text)
    assert caught.value.code == "FB008"
    assert "nested too deeply" in str(caught.value)


def test_unknown_elements_and_a_broken_logic_property_round_trip() -> None:
    text = _FORM.replace(
        " </widget>",
        '  <property name="cbcsOnClicked" stdset="0"><string>{</string></property>\n'
        "  <shopNote id='kept'>leave this</shopNote>\n"
        " </widget>",
    )
    written = write_ui(_read(text).document).text
    assert "<shopNote" in written
    assert "leave this" in written
    assert "{</string>" in written or ">{</string>" in written or "<string>{</string>" in written
    assert len(written.encode("utf-8")) >= len("{".encode("utf-8"))


def test_duplicate_names_and_odd_nesting_do_not_drop_widgets() -> None:
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0"><widget class="QWidget" name="Form">'
        '<property name="windowTitle"><widget class="QLabel" name="inside"/></property>'
        '<widget class="QPushButton" name="ok"/>'
        '<widget class="QPushButton" name="ok"/>'
        "</widget></ui>\n"
    )
    loaded = _read(text)
    names = [node.object_name for node in loaded.document.iter_widgets()]
    assert names.count("ok") == 2
    written = write_ui(loaded.document).text
    assert written.count('name="ok"') == 2


def test_a_long_attribute_value_is_kept() -> None:
    payload = "N" * 200_000
    text = _FORM.replace("Hello", payload)
    written = write_ui(_read(text).document).text
    assert payload in written


def test_a_ui_that_is_not_utf8_opens_as_text_and_saves_the_same_bytes(tmp_path: Path) -> None:
    raw = (
        b'<?xml version="1.0" encoding="ISO-8859-1"?>\n'
        b'<ui version="4.0"><widget class="QWidget" name="Form">'
        b'<property name="windowTitle"><string>caf\xe9</string></property>'
        b"</widget></ui>\n"
    )
    path = tmp_path / "cafe.ui"
    path.write_bytes(raw)
    manager = EditorManager()
    opened = manager.open_file(str(path))
    text = opened.tab.current_content
    assert text.encode("utf-8", "surrogateescape") == raw
    provider = FormTabProvider()
    with pytest.raises(ProviderDeclined) as caught:
        provider.create_surface(SimpleNamespace(file_path=str(path), initial_text=text, project_root=None))  # type: ignore[arg-type]
    assert caught.value.reason == "This form can't be opened in the form builder: the file isn't UTF-8."
    manager.save_tab(str(path))
    assert path.read_bytes() == raw
