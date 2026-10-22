# pyright: reportAttributeAccessIssue=false
"""Typed ui4 catalog for form, action, resource, custom-widget, and connection elements.

Designer 6.8.3 drops some of these on save. We keep them. The one intentional
byte difference against a Designer resave is recorded in ``_ORDER_ONLY``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.schema import (
    ConnectionHint,
    HeaderDecl,
    LayoutDefault,
    LayoutFunction,
    SlotsDecl,
)
from app.features.form_builder.engine.ui4.values import SizeValue
from app.features.form_builder.engine.ui4.writer import write_ui

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"
_SINK = _CORPUS / "synthetic" / "schema" / "kitchen_sink.ui"
_RESAVED = _CORPUS / "designer_resaved"
_RCC = Path("/Applications/FreeCAD.app/Contents/Resources/lib/qt6/rcc")

# schema.write_order emits properties before nested actions. Designer left the
# action first on innerGroup in this one resave. Line content is the same.
_ORDER_ONLY = {
    "actiongroup": "synthetic/schema/kitchen_sink.ui",
}

_DESIGNER_TAGS = (
    "author",
    "comment",
    "exportmacro",
    "layoutdefault",
    "layoutfunction",
    "pixmapfunction",
    "customwidgets",
    "customwidget",
    "class",
    "extends",
    "header",
    "container",
    "tabstops",
    "tabstop",
    "includes",
    "include",
    "resources",
    "connections",
    "connection",
    "hints",
    "hint",
    "designerdata",
    "slots",
    "signal",
    "slot",
    "buttongroups",
    "buttongroup",
    "action",
    "actiongroup",
    "addaction",
    "pixmap",
)


def _load(text: str):
    return read_ui(text, allocator=IdAllocator())


def _saved(text: str) -> str:
    return write_ui(_load(text).document).text


def _stable(text: str) -> str:
    first = _saved(text)
    assert write_ui(_load(first).document).text == first
    return first


def _extract(text: str, tag: str) -> List[str]:
    """Raw slices of ``tag``, including nested elements of the same name."""
    out: List[str] = []
    token_open = "<" + tag
    token_close = "</" + tag + ">"
    index = 0
    length = len(text)
    while index < length:
        start = text.find(token_open, index)
        if start < 0:
            break
        after = start + len(token_open)
        if after < length and (text[after].isalnum() or text[after] == "_"):
            index = after
            continue
        end = text.find(">", start)
        if end < 0:
            break
        if text[end - 1] == "/":
            out.append(text[start : end + 1])
            index = end + 1
            continue
        depth = 1
        cursor = end + 1
        while depth and cursor < length:
            nxt_open = text.find(token_open, cursor)
            nxt_close = text.find(token_close, cursor)
            if nxt_close < 0:
                break
            if nxt_open != -1 and nxt_open < nxt_close:
                boundary = nxt_open + len(token_open)
                if boundary < length and (text[boundary].isalnum() or text[boundary] == "_"):
                    cursor = boundary
                    continue
                depth += 1
                cursor = text.find(">", nxt_open) + 1
            else:
                depth -= 1
                cursor = nxt_close + len(token_close)
        out.append(text[start:cursor])
        index = cursor
    return out


def _lines(chunk: str) -> List[str]:
    return sorted(line.strip() for line in chunk.splitlines() if line.strip())


_SCAN: Dict[str, List[Tuple[str, str, str]]] = {}
_SCAN_READY = False


def _designer_mismatches() -> Dict[str, List[Tuple[str, str, str]]]:
    global _SCAN_READY
    if _SCAN_READY:
        return _SCAN
    for path in sorted(_RESAVED.rglob("*.ui")):
        designer = path.read_text(encoding="utf-8")
        written = _saved(designer)
        rel = path.relative_to(_RESAVED).as_posix()
        for tag in _DESIGNER_TAGS:
            left = _extract(designer, tag)
            right = _extract(written, tag)
            if left != right:
                _SCAN.setdefault(tag, []).append((rel, "\n".join(left), "\n".join(right)))
    _SCAN_READY = True
    return _SCAN


def _assert_designer(tags: Sequence[str]) -> None:
    found = _designer_mismatches()
    unexpected = []
    for tag in tags:
        rows = found.get(tag, [])
        allowed = _ORDER_ONLY.get(tag)
        if not rows:
            continue
        if allowed is None:
            unexpected.append((tag, [rel for rel, _left, _right in rows]))
            continue
        rels = [rel for rel, _left, _right in rows]
        if rels != [allowed]:
            unexpected.append((tag, rels))
            continue
        _rel, left, right = rows[0]
        if _lines(left) != _lines(right):
            unexpected.append((tag, ["content differs, not only order"]))
    assert unexpected == []


@pytest.mark.parity("R3-224")
@pytest.mark.parity("R3-225")
@pytest.mark.parity("R3-226")
@pytest.mark.parity("R3-229")
@pytest.mark.parity("R3-230")
@pytest.mark.parity("R3-231")
@pytest.mark.parity("R3-233")
@pytest.mark.parity("R3-234")
@pytest.mark.parity("R3-236")
@pytest.mark.parity("R3-237")
@pytest.mark.parity("R3-238")
@pytest.mark.parity("R3-239")
@pytest.mark.parity("R3-276")
@pytest.mark.parity("R3-280")
@pytest.mark.parity("R3-281")
def test_form_level_elements_are_typed_and_match_designer() -> None:
    text = _SINK.read_text(encoding="utf-8")
    saved = _stable(text)
    document = _load(saved).document
    ui = document.ui
    assert ui.field("author") == "ChoreBoy Code Studio corpus"
    assert ui.field("comment") == "Synthetic form that exercises the ui4 element set."
    assert ui.field("exportmacro") == "CBCS_EXPORT"
    assert ui.field("layoutdefault") == LayoutDefault(spacing=6, margin=11)
    assert ui.field("layoutfunction") == LayoutFunction(spacing="cbcsSpacing", margin="cbcsMargin")
    assert ui.field("pixmapfunction") == "cbcsPixmap"
    assert document.tabstops() == ("nameEdit", "whenEdit", "shortcutEdit")
    images = ui.field("images")
    assert isinstance(images, OpaqueElement) and images.tag == "images"
    assert "<images/>" in saved
    data = ui.field("designerdata")
    assert isinstance(data, OpaqueElement) and data.tag == "designerdata"
    assert ui.field("form_slots") == SlotsDecl(
        signals=("customSignal(int)",),
        slots=("on_nameEdit_textChanged(QString)",),
    )
    wrappers = ui.field("present_wrappers")
    assert isinstance(wrappers, frozenset)
    assert "resources" in wrappers
    assert "connections" in wrappers
    bare = _stable(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <widget class=\"QWidget\" name=\"Form\"/>\n"
        " <author></author>\n"
        " <comment/>\n"
        " <exportmacro></exportmacro>\n"
        "</ui>\n"
    )
    assert "<author" not in bare
    assert "<comment" not in bare
    assert "<exportmacro" not in bare
    assert "<resources/>" in bare
    assert "<connections/>" in bare
    named = _stable(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <widget class=\"QWidget\" name=\"Form\"/>\n"
        ' <resources name="cbcsResources">\n'
        '  <include location="icons.qrc"/>\n'
        " </resources>\n"
        "</ui>\n"
    )
    assert 'name="cbcsResources"' not in named
    loaded = _load(named)
    assert [node.field("location") for node in loaded.document.ui.children("resources")] == ["icons.qrc"]
    assert not any("resources" in item.message for item in loaded.diagnostics)
    kept = _stable(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <widget class=\"QWidget\" name=\"Form\"/>\n"
        ' <resources name="cbcsResources" zz="1">\n'
        '  <include location="icons.qrc"/>\n'
        " </resources>\n"
        "</ui>\n"
    )
    assert kept.count("<resources") == 1
    assert 'zz="1"' in kept
    assert 'name="cbcsResources"' not in kept
    _assert_designer(
        (
            "author",
            "comment",
            "exportmacro",
            "layoutdefault",
            "layoutfunction",
            "pixmapfunction",
            "tabstops",
            "tabstop",
            "resources",
            "connections",
            "designerdata",
            "slots",
            "signal",
            "slot",
        )
    )


@pytest.mark.parity("R3-232")
@pytest.mark.parity("R3-235")
@pytest.mark.parity("R3-240")
@pytest.mark.parity("R3-241")
@pytest.mark.parity("R3-242")
@pytest.mark.parity("R3-243")
@pytest.mark.parity("R3-244")
@pytest.mark.parity("R3-245")
@pytest.mark.parity("R3-246")
@pytest.mark.parity("R3-247")
@pytest.mark.parity("R3-248")
@pytest.mark.parity("R3-249")
@pytest.mark.parity("R3-250")
@pytest.mark.parity("R3-251")
@pytest.mark.parity("R3-252")
@pytest.mark.parity("R3-253")
@pytest.mark.parity("R3-254")
@pytest.mark.parity("R3-255")
@pytest.mark.parity("R3-256")
@pytest.mark.parity("R3-275")
def test_includes_resources_custom_widgets_and_button_groups() -> None:
    source = _SINK.read_text(encoding="utf-8")
    saved = _stable(source)
    assert _extract(source, "customwidget") == _extract(saved, "customwidget")
    document = _load(source).document
    ui = document.ui
    includes = ui.children("includes")
    assert [(node.kind, node.field("location"), node.field("impldecl"), node.field("text")) for node in includes] == [
        ("include", "local", "in implementation", "shop.widgets.invoice_header"),
        ("include", "global", "in declaration", "PySide6.QtCore"),
    ]
    resources = ui.children("resources")
    assert [node.kind for node in resources] == ["resource", "resource"]
    assert [node.field("location") for node in resources] == ["icons.qrc", "extra.qrc"]
    custom = document.custom_widget("InvoiceHeader")
    assert custom is not None and custom.kind == "customwidget"
    assert custom.field("class_name") == "InvoiceHeader"
    assert custom.field("extends") == "QWidget"
    assert custom.field("header") == HeaderDecl(text="shop.widgets.invoice_header", location="global")
    assert custom.field("sizehint") == SizeValue(width=120, height=48)
    assert custom.field("addpagemethod") == "addPage"
    assert custom.field("container") == 1
    assert custom.field("pixmap") == ":/cbcs/icons/dot.png"
    assert custom.field("slots") == SlotsDecl(signals=("changed()",), slots=("reset()",))
    specs = custom.field("propertyspecifications")
    assert isinstance(specs, OpaqueElement) and specs.tag == "propertyspecifications"
    tooltip = next(child for child in specs.children if isinstance(child, OpaqueElement) and child.tag == "tooltip")
    strings = next(
        child
        for child in specs.children
        if isinstance(child, OpaqueElement) and child.tag == "stringpropertyspecification"
    )
    assert tooltip.attrs == (("name", "title"),)
    assert tooltip.children == ("Title shown on the page",)
    assert strings.attrs == (("name", "title"), ("type", "singleline"), ("notr", "true"))
    assert [node.element.tag for node in custom.children("opaque")] == ["sizepolicy", "script", "properties"]
    groups = ui.children("buttongroups")
    assert len(groups) == 1 and groups[0].kind == "buttongroup"
    assert groups[0].field("name") == "choiceGroup"
    assert groups[0].prop("exclusive") is not None
    _assert_designer(
        (
            "customwidgets",
            "customwidget",
            "class",
            "extends",
            "header",
            "container",
            "includes",
            "include",
            "pixmap",
            "buttongroups",
            "buttongroup",
        )
    )


@pytest.mark.parity("R3-267")
@pytest.mark.parity("R3-268")
@pytest.mark.parity("R3-269")
@pytest.mark.parity("R3-277")
@pytest.mark.parity("R3-278")
@pytest.mark.parity("R3-279")
@pytest.mark.parity("R3-282")
def test_actions_and_connections_keep_their_fields(qapp: object) -> None:
    del qapp
    document = _load(_SINK.read_text(encoding="utf-8")).document
    root = document.root
    actions = {node.field("name"): node for node in root.children("actions")}
    assert actions["actionQuit"].field("menu") == "menuFile"
    assert actions["actionNew"].field("menu") is None
    outer = root.children("action_groups")
    assert len(outer) == 1 and outer[0].field("name") == "outerGroup"
    inner = outer[0].children("action_groups")
    assert len(inner) == 1 and inner[0].field("name") == "innerGroup"
    assert [node.field("name") for node in inner[0].children("actions")] == ["actionLeft"]
    menu = next(node for node in root.children("children") if node.field("object_name") == "menuBar")
    file_menu = next(node for node in menu.children("children") if node.field("object_name") == "menuFile")
    assert [node.field("name") for node in file_menu.children("add_actions")] == [
        "actionNew",
        "separator",
        "actionQuit",
    ]
    toolbar = next(node for node in root.children("children") if node.field("object_name") == "toolBar")
    assert [node.field("name") for node in toolbar.children("add_actions")] == ["actionNew"]
    saved = _stable(_SINK.read_text(encoding="utf-8"))
    assert 'menu="menuFile"' in saved
    connection = document.connections()[0]
    assert connection.field("sender") == "buttonBox"
    assert connection.field("signal") == "accepted()"
    assert connection.field("receiver") == "KitchenSink"
    assert connection.field("slot") == "close()"
    assert connection.field("hints") == (
        ConnectionHint(type="sourcelabel", x=10, y=20),
        ConnectionHint(type="destinationlabel", x=30, y=40),
    )
    _assert_designer(("action", "actiongroup", "addaction", "connection", "hints", "hint"))


def _loader_form(prefix: str) -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>MainWindow</class>
 <widget class="QMainWindow" name="MainWindow">
  <property name="geometry">
   <rect><x>0</x><y>0</y><width>420</width><height>280</height></rect>
  </property>
  <widget class="QWidget" name="central">
   <widget class="QLineEdit" name="third"><property name="text"><string>3</string></property></widget>
   <widget class="QLineEdit" name="first"><property name="text"><string>1</string></property></widget>
   <widget class="QLineEdit" name="second"><property name="text"><string>2</string></property></widget>
   <widget class="QPushButton" name="go"><property name="text"><string>Go</string></property></widget>
   <widget class="QRadioButton" name="radioA">
    <property name="text"><string>A</string></property>
    <attribute name="buttonGroup"><string notr="true">choice</string></attribute>
   </widget>
   <widget class="QRadioButton" name="radioB">
    <property name="text"><string>B</string></property>
    <attribute name="buttonGroup"><string notr="true">choice</string></attribute>
   </widget>
   <widget class="M11cHeader" name="banner"/>
   <widget class="QLabel" name="iconLabel">
    <property name="pixmap"><pixmap>:/m11c/dot.png</pixmap></property>
   </widget>
  </widget>
  <widget class="QMenuBar" name="menuBar">
   <widget class="QMenu" name="menuFile">
    <property name="title"><string>File</string></property>
    <addaction name="actionNew"/>
    <addaction name="separator"/>
    <addaction name="actionQuit"/>
   </widget>
   <addaction name="menuFile"/>
  </widget>
  <widget class="QToolBar" name="toolBar">
   <property name="windowTitle"><string>Main</string></property>
   <addaction name="actionNew"/>
  </widget>
  <action name="actionNew"><property name="text"><string>New</string></property></action>
  <action name="actionQuit" menu="menuFile"><property name="text"><string>Quit</string></property></action>
  <actiongroup name="outerGroup">
   <action name="actionLeft">
    <property name="text"><string>Left</string></property>
    <property name="checkable"><bool>true</bool></property>
   </action>
  </actiongroup>
 </widget>
 <customwidgets>
  <customwidget>
   <class>M11cHeader</class>
   <extends>QWidget</extends>
   <header>m11c_header.h</header>
  </customwidget>
 </customwidgets>
 <tabstops>
  <tabstop>third</tabstop>
  <tabstop>first</tabstop>
  <tabstop>second</tabstop>
 </tabstops>
 <resources>
  <include location="%s"/>
 </resources>
 <connections>
  <connection>
   <sender>go</sender>
   <signal>clicked()</signal>
   <receiver>first</receiver>
   <slot>clear()</slot>
   <hints>
    <hint type="sourcelabel"><x>1</x><y>2</y></hint>
    <hint type="destinationlabel"><x>3</x><y>4</y></hint>
   </hints>
  </connection>
 </connections>
 <buttongroups>
  <buttongroup name="choice">
   <property name="exclusive"><bool>true</bool></property>
  </buttongroup>
 </buttongroups>
</ui>
""" % prefix


def _compile_resource(directory: Path) -> str:
    from app.qt.QtGui import QColor, QImage

    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    assert image.save(str(directory / "dot.png"))
    qrc = directory / "m11c.qrc"
    qrc.write_text(
        '<RCC><qresource prefix="/m11c"><file>dot.png</file></qresource></RCC>\n',
        encoding="utf-8",
    )
    binary = directory / "m11c.rcc"
    subprocess.check_call([str(_RCC), "--binary", "-o", str(binary), str(qrc)], cwd=str(directory))
    return str(binary)


def _focus_names(window: object, names: Sequence[str]) -> Tuple[str, ...]:
    from app.qt.QtWidgets import QWidget

    start = window.findChild(QWidget, names[0])
    assert start is not None
    found = []
    current = start
    seen = set()
    for _step in range(40):
        name = current.objectName()
        if name in names and name not in seen:
            found.append(name)
            seen.add(name)
        nxt = current.nextInFocusChain()
        if nxt is None or nxt is start:
            break
        current = nxt
    return tuple(found)


def _loaded_behavior(text: str, qapp: object) -> dict:
    del qapp
    from app.qt.QtCore import QBuffer, QIODevice
    from app.qt.QtGui import QAction, QActionGroup
    from app.qt.QtUiTools import QUiLoader
    from app.qt.QtWidgets import (
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QPushButton,
        QRadioButton,
        QToolBar,
        QWidget,
    )

    class M11cHeader(QWidget):
        pass

    buffer = QBuffer()
    buffer.setData(text.encode("utf-8"))
    buffer.open(QIODevice.ReadOnly)
    loader = QUiLoader()
    loader.registerCustomWidget(M11cHeader)
    window = loader.load(buffer)
    assert isinstance(window, QMainWindow)
    window.show()
    menu = window.findChild(QMenu, "menuFile")
    toolbar = window.findChild(QToolBar, "toolBar")
    group = window.findChild(QActionGroup, "outerGroup")
    radio_a = window.findChild(QRadioButton, "radioA")
    radio_b = window.findChild(QRadioButton, "radioB")
    button = window.findChild(QPushButton, "go")
    first = window.findChild(QLineEdit, "first")
    label = window.findChild(QLabel, "iconLabel")
    banner = window.findChild(QWidget, "banner")
    quit_action = window.findChild(QAction, "actionQuit")
    assert menu is not None and toolbar is not None and group is not None
    assert radio_a is not None and radio_b is not None and button is not None and first is not None
    assert label is not None and banner is not None and quit_action is not None
    menu_names = tuple(action.objectName() for action in menu.actions())
    tool_names = tuple(action.objectName() for action in toolbar.actions())
    group_names = tuple(action.objectName() for action in group.actions())
    shared = radio_a.group()
    group_name = "" if shared is None else shared.objectName()
    same_group = shared is not None and shared is radio_b.group()
    quit_menu = quit_action.menu()
    quit_menu_name: Optional[str] = None if quit_menu is None else quit_menu.objectName()
    focus = _focus_names(window, ("third", "first", "second"))
    before = first.text()
    button.click()
    after = first.text()
    pixmap_null = label.pixmap().isNull()
    banner_type = type(banner).__name__
    window.hide()
    window.deleteLater()
    return {
        "menu": menu_names,
        "toolbar": tool_names,
        "group": group_names,
        "button_group": (group_name, same_group),
        "quit_menu": quit_menu_name,
        "focus": focus,
        "cleared": (before, after),
        "pixmap_null": pixmap_null,
        "banner": banner_type,
    }


@pytest.mark.parity("R3-236")
@pytest.mark.parity("R3-242")
@pytest.mark.parity("R3-243")
@pytest.mark.parity("R3-267")
@pytest.mark.parity("R3-268")
@pytest.mark.parity("R3-269")
@pytest.mark.parity("R3-275")
@pytest.mark.parity("R3-276")
@pytest.mark.parity("R3-277")
@pytest.mark.parity("R3-282")
def test_qt_loader_keeps_behavior_after_round_trip(qapp: object, tmp_path: Path) -> None:
    from app.qt.QtCore import QResource

    binary = _compile_resource(tmp_path)
    assert QResource.registerResource(binary)
    try:
        text = _loader_form("m11c.qrc")
        saved = _stable(text)
        before = _loaded_behavior(text, qapp)
        after = _loaded_behavior(saved, qapp)
    finally:
        QResource.unregisterResource(binary)
    assert before == after
    assert before["menu"] == ("actionNew", "", "actionQuit")
    assert before["toolbar"] == ("actionNew",)
    assert before["group"] == ("actionLeft",)
    assert before["button_group"] == ("choice", True)
    assert before["focus"] == ("third", "first", "second")
    assert before["cleared"] == ("1", "")
    assert before["pixmap_null"] is False
    assert before["banner"] == "M11cHeader"
    # QUiLoader 6.8.3 does not call setMenu for the action menu attribute.
    # uic does. The attribute still has to survive the save.
    assert before["quit_menu"] is None
    assert 'menu="menuFile"' in saved
