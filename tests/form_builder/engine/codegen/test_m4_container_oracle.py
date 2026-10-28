# pyright: reportAttributeAccessIssue=false
"""Container forms the builder writes match ``uic -g python`` (UX-CONT-013, R3-121, R3-128).

Each form starts from a small file, is edited with the page commands and saved,
then compared to the Designer tool: root and nested wizards with three steps
that were reordered and had a step deleted, a toolbox and a tab widget with an
inserted page, an MDI area with a window, and a dock widget in a main window.
Needs ``CBCS_FB_UIC`` (the FreeCAD ``uic``); skipped without it.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.features.form_builder.engine.commands.catalog import MovePage, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.pages import DeletePage, InsertPage
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import open_log

pytestmark = pytest.mark.unit

_HERE = Path(__file__).resolve().parent


def _load_helper(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_uic = _load_helper("cbcs_uic_compare_m42", _HERE / "uic_compare.py")

_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n'
_TAIL = " <resources/>\n <connections/>\n</ui>\n"

WIZARD = _HEAD + (
    ' <widget class="QWizard" name="Wizard">\n'
    '  <widget class="QWizardPage" name="wizardPage_1">\n'
    '   <property name="title"><string>Step 1</string></property>\n'
    "  </widget>\n"
    " </widget>\n"
) + _TAIL

NESTED_WIZARD = _HEAD + (
    ' <widget class="QWidget" name="Form">\n'
    '  <layout class="QVBoxLayout" name="verticalLayout">\n'
    "   <item>\n"
    '    <widget class="QWizard" name="nestedWizard">\n'
    '     <widget class="QWizardPage" name="wizardPage_1">\n'
    '      <property name="title"><string>Step 1</string></property>\n'
    "     </widget>\n"
    "    </widget>\n"
    "   </item>\n"
    "  </layout>\n"
    " </widget>\n"
) + _TAIL

TOOLBOX = _HEAD + (
    ' <widget class="QToolBox" name="Form">\n'
    '  <widget class="QWidget" name="page_1">\n'
    '   <attribute name="label"><string>Settings</string></attribute>\n'
    "  </widget>\n"
    " </widget>\n"
) + _TAIL

TABS = _HEAD + (
    ' <widget class="QTabWidget" name="Form">\n'
    '  <widget class="QWidget" name="tab_1">\n'
    '   <attribute name="title"><string>Settings</string></attribute>\n'
    "  </widget>\n"
    " </widget>\n"
) + _TAIL

MDI = _HEAD + (
    ' <widget class="QWidget" name="Form">\n'
    '  <layout class="QVBoxLayout" name="verticalLayout">\n'
    "   <item>\n"
    '    <widget class="QMdiArea" name="mdiArea">\n'
    '     <widget class="QWidget" name="subwindow_1">\n'
    '      <property name="windowTitle"><string>Notes</string></property>\n'
    "     </widget>\n"
    "    </widget>\n"
    "   </item>\n"
    "  </layout>\n"
    " </widget>\n"
) + _TAIL

DOCK = _HEAD + (
    ' <widget class="QMainWindow" name="Form">\n'
    '  <widget class="QWidget" name="centralwidget"/>\n'
    '  <widget class="QDockWidget" name="dockWidget">\n'
    '   <property name="windowTitle"><string>Tools</string></property>\n'
    '   <attribute name="dockWidgetArea"><number>1</number></attribute>\n'
    '   <widget class="QWidget" name="dockWidgetContents"/>\n'
    "  </widget>\n"
    " </widget>\n"
) + _TAIL


def _save(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / ("%s.ui" % name)
    path.write_text(text, encoding="utf-8")
    return path


def _oracle(path: Path) -> None:
    result = _uic.compare(path)
    assert result[0] == "ok", "%s: %s" % (path.name, result)
    print("ORACLE %s %s" % (path.name, result[0]))


@pytest.fixture
def uic_env(monkeypatch):  # type: ignore[no-untyped-def]
    uic = os.environ.get("CBCS_FB_UIC", "") or "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
    if not Path(uic).is_file():
        pytest.skip("CBCS_FB_UIC is not set")
    monkeypatch.setenv("CBCS_FB_UIC", uic)


def test_root_wizard_with_three_steps_reordered_and_one_deleted(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(WIZARD)
    doc = log.document
    wizard = doc.root.id
    log.execute(InsertPage(wizard))
    log.execute(InsertPage(wizard, index=0))
    log.execute(MovePage(wizard, 0, 2))
    log.execute(DeletePage(wizard, 1))
    path = _save(tmp_path, "root_wizard", write_ui(doc).text)
    _oracle(path)


def test_nested_wizard_with_three_steps_reordered_and_one_deleted(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(NESTED_WIZARD)
    doc = log.document
    wizard = doc.by_name("nestedWizard")[0]
    log.execute(InsertPage(wizard))
    log.execute(InsertPage(wizard))
    log.execute(MovePage(wizard, 0, 2))
    log.execute(DeletePage(wizard, 1))
    _oracle(_save(tmp_path, "nested_wizard", write_ui(doc).text))


def test_toolbox_insert_writes_a_label_and_no_title(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(TOOLBOX)
    doc = log.document
    log.execute(InsertPage(doc.root.id))
    text = write_ui(doc).text
    assert 'attribute name="label"' in text and "Page 2" in text
    assert 'attribute name="title"' not in text
    _oracle(_save(tmp_path, "toolbox", text))


def test_tab_insert_writes_a_title_and_no_label(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(TABS)
    doc = log.document
    log.execute(InsertPage(doc.root.id))
    log.execute(SetProperty(doc.root.id, "currentIndex", NumberValue(1)))
    text = write_ui(doc).text
    assert 'attribute name="title"' in text and "Tab 2" in text
    assert 'attribute name="label"' not in text
    _oracle(_save(tmp_path, "tabs", text))


def test_mdi_window_insert_and_delete(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(MDI)
    doc = log.document
    area = doc.by_name("mdiArea")[0]
    log.execute(InsertPage(area))
    log.execute(DeletePage(area, 0))
    text = write_ui(doc).text
    assert "Window 2" in text and "Notes" not in text
    _oracle(_save(tmp_path, "mdi", text))


def test_dock_side_is_written_as_the_dock_area_number(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(DOCK)
    doc = log.document
    dock = doc.by_name("dockWidget")[0]
    log.execute(SetProperty(dock, "dockWidgetArea", NumberValue(8), kind="attribute"))
    text = write_ui(doc).text
    assert '<attribute name="dockWidgetArea">' in text and "<number>8</number>" in text
    _oracle(_save(tmp_path, "dock", text))
