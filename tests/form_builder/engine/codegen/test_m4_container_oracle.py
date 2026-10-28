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


@pytest.mark.parity("R3-121")
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


@pytest.mark.parity("R3-121")
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


@pytest.mark.parity("R3-128")
def test_toolbox_insert_writes_a_label_and_no_title(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(TOOLBOX)
    doc = log.document
    log.execute(InsertPage(doc.root.id))
    text = write_ui(doc).text
    assert 'attribute name="label"' in text and "Page 2" in text
    assert 'attribute name="title"' not in text
    _oracle(_save(tmp_path, "toolbox", text))


@pytest.mark.parity("R3-127")
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


@pytest.mark.parity("R3-126")
def test_stacked_insert_writes_no_title_and_keeps_the_current_page(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(STACKED)
    doc = log.document
    log.execute(InsertPage(doc.root.id, index=0))
    text = write_ui(doc).text
    assert "<attribute" not in text and "<string>Page" not in text
    assert "page_3" in text
    assert 'name="currentIndex"' in text and "<number>2</number>" in text  # still on page_b
    _oracle(_save(tmp_path, "stacked", text))


STACKED = _HEAD + (
    ' <widget class="QStackedWidget" name="Form">\n'
    ' <property name="currentIndex"><number>1</number></property>\n'
    '  <widget class="QWidget" name="page_1"/>\n'
    '  <widget class="QWidget" name="page_2"/>\n'
    " </widget>\n"
) + _TAIL


def _qui_load(path: Path):  # type: ignore[no-untyped-def]
    from PySide6.QtCore import QFile
    from PySide6.QtUiTools import QUiLoader

    file = QFile(str(path))
    assert file.open(QFile.OpenModeFlag.ReadOnly)
    try:
        return QUiLoader().load(file)
    finally:
        file.close()


@pytest.mark.parity("R3-127")
@pytest.mark.parity("R3-128")
def test_quiloader_reads_the_titles_order_and_start_page_the_builder_wrote(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    """Titles, order and the start page as Qt's own .ui loader reads them (UX-CONT-001)."""
    del uic_env
    from PySide6.QtWidgets import QMdiArea, QTabWidget, QToolBox, QWizard

    log = open_log(TABS)
    doc = log.document
    log.execute(InsertPage(doc.root.id, index=0))
    log.execute(SetProperty(doc.root.id, "currentIndex", NumberValue(1)))
    tabs = _qui_load(_save(tmp_path, "q_tabs", write_ui(doc).text))
    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Tab 1", "Settings"]
    assert tabs.currentIndex() == 1 and tabs.currentWidget().objectName() == "tab_1"

    log = open_log(TOOLBOX)
    doc = log.document
    log.execute(InsertPage(doc.root.id))
    toolbox = _qui_load(_save(tmp_path, "q_toolbox", write_ui(doc).text))
    assert isinstance(toolbox, QToolBox)
    assert [toolbox.itemText(i) for i in range(toolbox.count())] == ["Settings", "Page 2"]

    log = open_log(WIZARD)
    doc = log.document
    log.execute(InsertPage(doc.root.id))
    wizard = _qui_load(_save(tmp_path, "q_wizard", write_ui(doc).text))
    assert isinstance(wizard, QWizard)
    titles = [wizard.page(page_id).title() for page_id in wizard.pageIds()]
    assert titles == ["Step 1", "Step 2"]

    log = open_log(MDI)
    doc = log.document
    log.execute(InsertPage(doc.by_name("mdiArea")[0]))
    mdi = _qui_load(_save(tmp_path, "q_mdi", write_ui(doc).text))
    area = mdi.findChild(QMdiArea, "mdiArea")
    assert area is not None
    assert sorted(sub.windowTitle() for sub in area.subWindowList()) == ["Notes", "Window 2"]


@pytest.mark.parametrize(
    "text",
    [TABS, TOOLBOX, WIZARD, NESTED_WIZARD, MDI, DOCK, STACKED],
    ids=["tabs", "toolbox", "wizard", "nested_wizard", "mdi", "dock", "stacked"],
)
def test_saving_a_container_form_twice_gives_the_same_bytes(text: str) -> None:
    """Every container kind: read, write, read, write is byte-identical (UX-CONT-001 storage)."""
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.ui4.reader import read_ui

    once = write_ui(read_ui(text, allocator=IdAllocator()).document).text
    twice = write_ui(read_ui(once, allocator=IdAllocator()).document).text
    assert twice == once


# A layout on a plain child QWidget gets 0 for the sides it does not write; a
# page, scroll content, MDI window, dock content or central widget keeps the
# style margins. Partial margins fill the other sides with 0 (observed uic).
_HOLDERS = {
    "free_and_nested": '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n <widget class="QWidget" name="Form">\n  <widget class="QWidget" name="freeHolder">\n   <layout class="QVBoxLayout" name="l1"/>\n  </widget>\n  <widget class="QGroupBox" name="box">\n   <layout class="QVBoxLayout" name="l2"/>\n  </widget>\n  <widget class="QFrame" name="frame">\n   <layout class="QVBoxLayout" name="l3"/>\n  </widget>\n  <widget class="QTabWidget" name="tabs">\n   <widget class="QWidget" name="tab">\n    <attribute name="title"><string>A</string></attribute>\n    <layout class="QVBoxLayout" name="l4"/>\n   </widget>\n  </widget>\n  <widget class="QWidget" name="outer">\n   <layout class="QVBoxLayout" name="l5">\n    <item>\n     <widget class="QFrame" name="nestedFrame">\n      <layout class="QVBoxLayout" name="l6"/>\n     </widget>\n    </item>\n    <item>\n     <widget class="QWidget" name="nestedWidget">\n      <layout class="QVBoxLayout" name="l7"/>\n     </widget>\n    </item>\n   </layout>\n  </widget>\n </widget>\n <resources/>\n <connections/>\n</ui>\n',
    "page_hosts": '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n <widget class="QMainWindow" name="Form">\n  <widget class="QWidget" name="centralwidget">\n   <layout class="QVBoxLayout" name="c0">\n    <item><widget class="QStackedWidget" name="st"><widget class="QWidget" name="sp"><layout class="QVBoxLayout" name="c1"/></widget></widget></item>\n    <item><widget class="QToolBox" name="tb"><widget class="QWidget" name="tp"><attribute name="label"><string>A</string></attribute><layout class="QVBoxLayout" name="c2"/></widget></widget></item>\n    <item><widget class="QScrollArea" name="sa"><property name="widgetResizable"><bool>true</bool></property><widget class="QWidget" name="scrollAreaWidgetContents"><layout class="QVBoxLayout" name="c3"/></widget></widget></item>\n    <item><widget class="QMdiArea" name="mdi"><widget class="QWidget" name="subwindow"><property name="windowTitle"><string>W</string></property><layout class="QVBoxLayout" name="c4"/></widget></widget></item>\n    <item><widget class="QSplitter" name="spl"><widget class="QWidget" name="sw"><layout class="QVBoxLayout" name="c6"/></widget></widget></item>\n    <item><widget class="QWizard" name="wz"><widget class="QWizardPage" name="wp"><layout class="QVBoxLayout" name="c7"/></widget></widget></item>\n   </layout>\n  </widget>\n  <widget class="QDockWidget" name="dock"><attribute name="dockWidgetArea"><number>1</number></attribute><widget class="QWidget" name="dockWidgetContents"><layout class="QVBoxLayout" name="c5"/></widget></widget>\n </widget>\n <resources/>\n <connections/>\n</ui>\n',
    "inside_frames": '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n <widget class="QWidget" name="Form">\n  <widget class="QGroupBox" name="g"><widget class="QWidget" name="gw"><layout class="QVBoxLayout" name="a1"/></widget></widget>\n  <widget class="QFrame" name="f"><widget class="QWidget" name="fw"><layout class="QVBoxLayout" name="a2"/></widget></widget>\n  <widget class="QWidget" name="layoutWidget"><layout class="QVBoxLayout" name="a3"/></widget>\n  <widget class="Custom" name="cu"><layout class="QVBoxLayout" name="a4"/></widget>\n </widget>\n <customwidgets><customwidget><class>Custom</class><extends>QWidget</extends><header>custom.h</header></customwidget></customwidgets>\n <resources/>\n <connections/>\n</ui>\n',
    "native_true": '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n <widget class="QWidget" name="Form">\n  <widget class="QWidget" name="freeHolder" native="true">\n   <layout class="QVBoxLayout" name="l1"/>\n  </widget>\n  <widget class="QGroupBox" name="box">\n   <layout class="QVBoxLayout" name="l2"/>\n  </widget>\n  <widget class="QFrame" name="frame">\n   <layout class="QVBoxLayout" name="l3"/>\n  </widget>\n  <widget class="QTabWidget" name="tabs">\n   <widget class="QWidget" name="tab">\n    <attribute name="title"><string>A</string></attribute>\n    <layout class="QVBoxLayout" name="l4"/>\n   </widget>\n  </widget>\n  <widget class="QWidget" name="outer">\n   <layout class="QVBoxLayout" name="l5">\n    <item>\n     <widget class="QFrame" name="nestedFrame">\n      <layout class="QVBoxLayout" name="l6"/>\n     </widget>\n    </item>\n    <item>\n     <widget class="QWidget" name="nestedWidget">\n      <layout class="QVBoxLayout" name="l7"/>\n     </widget>\n    </item>\n   </layout>\n  </widget>\n </widget>\n <resources/>\n <connections/>\n</ui>\n',
    "native_false": '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n <widget class="QWidget" name="Form">\n  <widget class="QWidget" name="freeHolder" native="false">\n   <layout class="QVBoxLayout" name="l1"/>\n  </widget>\n  <widget class="QGroupBox" name="box">\n   <layout class="QVBoxLayout" name="l2"/>\n  </widget>\n  <widget class="QFrame" name="frame">\n   <layout class="QVBoxLayout" name="l3"/>\n  </widget>\n  <widget class="QTabWidget" name="tabs">\n   <widget class="QWidget" name="tab">\n    <attribute name="title"><string>A</string></attribute>\n    <layout class="QVBoxLayout" name="l4"/>\n   </widget>\n  </widget>\n  <widget class="QWidget" name="outer">\n   <layout class="QVBoxLayout" name="l5">\n    <item>\n     <widget class="QFrame" name="nestedFrame">\n      <layout class="QVBoxLayout" name="l6"/>\n     </widget>\n    </item>\n    <item>\n     <widget class="QWidget" name="nestedWidget">\n      <layout class="QVBoxLayout" name="l7"/>\n     </widget>\n    </item>\n   </layout>\n  </widget>\n </widget>\n <resources/>\n <connections/>\n</ui>\n',
    "partial_margin": '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Form</class>\n <widget class="QWidget" name="Form">\n  <widget class="QGroupBox" name="g"><widget class="QWidget" name="gw"><layout class="QVBoxLayout" name="a1"><property name="leftMargin"><number>3</number></property></layout></widget></widget>\n  <widget class="QFrame" name="f"><widget class="QWidget" name="fw"><layout class="QVBoxLayout" name="a2"/></widget></widget>\n  <widget class="QWidget" name="layoutWidget"><layout class="QVBoxLayout" name="a3"/></widget>\n  <widget class="Custom" name="cu"><layout class="QVBoxLayout" name="a4"/></widget>\n </widget>\n <customwidgets><customwidget><class>Custom</class><extends>QWidget</extends><header>custom.h</header></customwidget></customwidgets>\n <resources/>\n <connections/>\n</ui>\n',
}


@pytest.mark.parametrize("name", sorted(_HOLDERS))
def test_layout_margins_on_plain_and_page_widgets_match_uic(name: str, tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    _oracle(_save(tmp_path, name, _HOLDERS[name]))
