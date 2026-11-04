"""Damaged .ui files open with the engine's sentence and are not saved shorter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import NON_UTF8_UI_NOTICE, EditorManager
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
    assert caught.value.reason == NON_UTF8_UI_NOTICE
    with pytest.raises(ValueError, match="read-only"):
        manager.save_tab(str(path))
    assert path.read_bytes() == raw


def test_a_latin1_ui_stays_unchanged_when_the_text_editor_saves(tmp_path: Path, qapp: object) -> None:
    """The text widget replaces a bad byte. Save still leaves the file alone."""

    del qapp
    from types import SimpleNamespace

    from app.qt.QtGui import QPalette
    from app.qt.QtWidgets import QApplication, QWidget
    from app.shell.editor_tab_factory import EditorTabFactory
    from app.shell.save_workflow import SaveWorkflow
    from app.shell.theme_tokens import tokens_from_palette

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
    window = SimpleNamespace(
        _editor_tab_width=4,
        _editor_font_family="monospace",
        _editor_indent_style="spaces",
        _editor_indent_size=4,
        _editor_hover_tooltip_enabled=False,
        _editor_auto_reindent_flat_python_paste=False,
        _completion_min_chars=1,
        _shell_preferences_runtime=SimpleNamespace(completion_mode=lambda: "off"),
        _editor_tab_workflow=SimpleNamespace(
            effective_font_size=lambda: 12,
            apply_runtime_intelligence_preferences_to_editor=lambda _widget: None,
            attach_editor_bindings=lambda *_args: None,
        ),
        _shell_theme_workflow=SimpleNamespace(
            resolve_theme_tokens=lambda: tokens_from_palette(QApplication.instance().palette() or QPalette())
        ),
        _workspace_controller=SimpleNamespace(register_editor=lambda *_args: None),
    )
    parent = QWidget()
    editor = EditorTabFactory(window)._build_bound_source_editor(  # type: ignore[arg-type]
        opened,
        parent=parent,
        theme_tokens=None,
    )
    assert isinstance(editor, CodeEditorWidget)
    assert editor.isReadOnly()
    shown = editor.toPlainText()
    assert shown.encode("utf-8", "surrogateescape") != raw
    editor.insertPlainText("Z")
    manager.update_tab_content(str(path), shown)
    assert manager.get_tab(str(path)).current_content.encode("utf-8", "surrogateescape") == raw
    told: list[str] = []

    def _warn(*args: object, **_kwargs: object) -> int:
        told.append(str(args[-1]))
        return 0

    workflow = SaveWorkflow.__new__(SaveWorkflow)
    workflow._host = SimpleNamespace(dialog_parent=lambda: None)  # type: ignore[attr-defined]
    workflow._editor_manager = lambda: manager  # type: ignore[method-assign]
    import app.shell.save_workflow as save_workflow

    previous = save_workflow.QMessageBox.warning
    save_workflow.QMessageBox.warning = _warn  # type: ignore[method-assign]
    try:
        assert workflow.save_tab(str(path), check_stale_disk=False) is False
        assert workflow.save_tab(str(path), checkpoint_source="auto_save_to_file", check_stale_disk=False) is False
    finally:
        save_workflow.QMessageBox.warning = previous  # type: ignore[method-assign]
    assert told and "read-only" in told[0]
    assert path.read_bytes() == raw
