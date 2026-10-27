# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, List, Tuple

import pytest

from app.qt.QtCore import QPoint, Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QWidget
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import Stroke
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")


class _Host:
    def __init__(self) -> None:
        self.sentences: List[str] = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        self.sentences.append(sentence)

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None

    def open_context_menu(self, node: object, at: object) -> None:
        return None


@contextmanager
def _shown(text: str) -> Iterator[Tuple[FormSession, FormCanvas, _Host]]:
    with opened(text) as (session, realizer):
        parent = QWidget()
        parent.resize(720, 520)
        host = _Host()
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(720, 520)
        parent.show()
        _flush()
        canvas.setFocus()
        _flush()
        try:
            yield session, canvas, host
        finally:
            canvas.dispose()
            parent.deleteLater()


@pytest.mark.parity("R3-21")
def test_a_box_drag_inserts_between_the_neighbours() -> None:
    """Dragging a laid-out widget reorders it. The insertion sentence is the cursor."""
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="shop"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="receipts"><property name="text"><string>Receipts</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, host):
        shop = _widget(canvas, "shop")
        _drag_widget_to(canvas, "receipts", shop.mapTo(canvas.page_widget(), QPoint(shop.width() // 2, 4)))
        assert _slot_names(session.document, "verticalLayout") == ["receipts", "shop"]
        assert session.log.undo_label() == "Move"
        assert len(session.log.entries()) == 1
        assert any("Insert" in sentence or "before" in sentence for sentence in host.sentences)
        assert session.log.undo()
        _flush()
        assert _slot_names(session.document, "verticalLayout") == ["shop", "receipts"]


def test_a_box_drag_beside_a_widget_wraps_a_row() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="shop"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="below"><property name="text"><string>Below</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        shop = _widget(canvas, "shop")
        edge = shop.mapTo(canvas.page_widget(), QPoint(max(shop.width() - 2, 0), shop.height() // 2))
        _drag_widget_to(canvas, "below", edge)
        outer = _layout(session.document, "verticalLayout")
        assert len(outer.items) == 1
        wrapped = outer.items[0].content
        assert isinstance(wrapped, LayoutNode)
        assert wrapped.class_name == "QHBoxLayout"
        assert _content_names(wrapped) == ["shop", "below"]
        assert len(session.log.entries()) == 1


def test_a_grid_drop_on_an_empty_cell_moves_only_that_item() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0"><widget class="QPushButton" name="origin"><property name="text"><string>Origin</string></property></widget></item>
   <item row="0" column="1"><widget class="QPushButton" name="east"><property name="text"><string>East</string></property></widget></item>
   <item row="1" column="0"><widget class="QPushButton" name="south"><property name="text"><string>South</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        south = _widget(canvas, "south")
        target = south.mapTo(canvas.page_widget(), QPoint(south.width() + south.width() // 2, south.height() // 2))
        _drag_widget_to(canvas, "origin", target)
        cells = _cells(session.document, "grid")
        assert cells["origin"][:2] == (1, 1)
        assert cells["east"][:2] == (0, 1)
        assert cells["south"][:2] == (1, 0)
        assert session.log.undo()
        _flush()
        assert _cells(session.document, "grid")["origin"][:2] == (0, 0)


def test_a_grid_edge_inserts_a_column_and_shifts_the_rest() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0"><widget class="QPushButton" name="left"><property name="text"><string>Left</string></property></widget></item>
   <item row="0" column="1"><widget class="QPushButton" name="right"><property name="text"><string>Right</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, host):
        left = _widget(canvas, "left")
        edge = left.mapTo(canvas.page_widget(), QPoint(2, left.height() // 2))
        before = session.log.entries()
        _press_move(canvas, "right", edge)
        assert any("column" in sentence.lower() for sentence in host.sentences)
        strokes = [item for item in canvas.overlay().items if isinstance(item, Stroke)]
        assert strokes
        _release(canvas, edge)
        cells = _cells(session.document, "grid")
        assert cells["right"][1] == 0
        assert cells["left"][1] == 1
        assert len(session.log.entries()) == len(before) + 1


def test_a_grid_ghost_row_adds_a_row_under_the_grid() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0"><widget class="QPushButton" name="only"><property name="text"><string>Only</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, host):
        only = _widget(canvas, "only")
        below = only.mapTo(canvas.page_widget(), QPoint(only.width() // 2, only.height() + 12))
        _drag_widget_to(canvas, "only", below)
        assert any("New row" in sentence for sentence in host.sentences)
        assert _cells(session.document, "grid")["only"][0] == 1


def test_a_grid_span_move_keeps_the_span_and_the_other_cell() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0" colspan="2"><widget class="QPushButton" name="banner"><property name="text"><string>Banner</string></property></widget></item>
   <item row="1" column="0"><widget class="QPushButton" name="stay"><property name="text"><string>Stay</string></property></widget></item>
   <item row="2" column="0"><widget class="QPushButton" name="wide"><property name="text"><string>Wide</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        wide = _widget(canvas, "wide")
        # Row 1 column 1 is empty. The banner still spans both columns of row 0.
        target = wide.mapTo(canvas.page_widget(), QPoint(wide.width() + 30, -wide.height() // 2))
        _drag_widget_to(canvas, "wide", target)
        cells = _cells(session.document, "grid")
        assert cells["stay"][:2] == (1, 0)
        assert cells["banner"][1] == 0
        assert cells["banner"][3] == 2
        assert cells["wide"][3] == 1


def test_a_form_drop_opens_the_new_field_editor() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
   <item row="1" column="1"><widget class="QPushButton" name="go"><property name="text"><string>Go</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        email = _widget(canvas, "email")
        below = email.mapTo(canvas.page_widget(), QPoint(email.width() // 2, email.height() + 30))
        _drag_widget_to(canvas, "go", below)
        assert "New field:" in _label_texts(session.document)
        edits = [edit for edit in canvas.viewport().findChildren(QLineEdit) if edit.isVisible()]
        assert any(edit.text() == "New field:" and edit.selectedText() == "New field:" for edit in edits)
        assert len(session.log.entries()) == 1
        QTest.keyClick(edits[0], _key("Key_Escape"))
        _flush()
        assert "New field:" in _label_texts(session.document)


def test_a_form_label_cell_takes_a_widget() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
   <item row="1" column="0"><widget class="QLabel" name="spare"><property name="text"><string>Spare</string></property></widget></item>
   <item row="1" column="1"><widget class="QPushButton" name="go"><property name="text"><string>Go</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, host):
        email = _widget(canvas, "email")
        spot = email.mapTo(canvas.page_widget(), QPoint(-40, email.height() // 2))
        _drag_widget_to(canvas, "spare", spot)
        assert any("Label" in sentence for sentence in host.sentences)
        cells = _cells(session.document, "formLayout")
        assert cells["spare"][1] == 0


def test_a_splitter_drop_inserts_a_pane() -> None:
    text = form(
        'class="QSplitter" name="Form"',
        """
  <widget class="QPushButton" name="left"><property name="text"><string>Left</string></property></widget>
  <widget class="QPushButton" name="right"><property name="text"><string>Right</string></property></widget>
""",
    )
    with _shown(text) as (session, canvas, host):
        left = _widget(canvas, "left")
        _drag_widget_to(canvas, "right", left.mapTo(canvas.page_widget(), QPoint(4, left.height() // 2)))
        names = [child.object_name for child in session.document.root.child_widgets]
        assert names[0] == "right"
        assert "New pane" in " ".join(host.sentences) or names == ["right", "left"]


def test_a_page_drop_lands_in_the_current_page() -> None:
    cases = (
        (
            "tabs",
            'class="QWidget" name="Form"',
            """
  <layout class="QVBoxLayout" name="outer">
   <item>
    <widget class="QTabWidget" name="pages">
     <widget class="QWidget" name="page">
      <attribute name="title"><string>Settings</string></attribute>
      <layout class="QVBoxLayout" name="pageLayout">
       <item><widget class="QPushButton" name="keep"><property name="text"><string>Keep</string></property></widget></item>
      </layout>
     </widget>
    </widget>
   </item>
   <item><widget class="QPushButton" name="extra"><property name="text"><string>Extra</string></property></widget></item>
  </layout>
""",
        ),
        (
            "stack",
            'class="QWidget" name="Form"',
            """
  <layout class="QVBoxLayout" name="outer">
   <item>
    <widget class="QStackedWidget" name="pages">
     <widget class="QWidget" name="page">
      <layout class="QVBoxLayout" name="pageLayout">
       <item><widget class="QPushButton" name="keep"><property name="text"><string>Keep</string></property></widget></item>
      </layout>
     </widget>
    </widget>
   </item>
   <item><widget class="QPushButton" name="extra"><property name="text"><string>Extra</string></property></widget></item>
  </layout>
""",
        ),
        (
            "tools",
            'class="QWidget" name="Form"',
            """
  <layout class="QVBoxLayout" name="outer">
   <item>
    <widget class="QToolBox" name="pages">
     <widget class="QWidget" name="page">
      <attribute name="label"><string>First</string></attribute>
      <layout class="QVBoxLayout" name="pageLayout">
       <item><widget class="QPushButton" name="keep"><property name="text"><string>Keep</string></property></widget></item>
      </layout>
     </widget>
    </widget>
   </item>
   <item><widget class="QPushButton" name="extra"><property name="text"><string>Extra</string></property></widget></item>
  </layout>
""",
        ),
    )
    for _name, opening, inner in cases:
        with _shown(form(opening, inner)) as (session, canvas, _host):
            keep = _widget(canvas, "keep")
            _drag_widget_to(canvas, "extra", keep.mapTo(canvas.page_widget(), keep.rect().center()))
            page = _layout(session.document, "pageLayout")
            assert "extra" in _content_names(page)
            assert "extra" not in _content_names(_layout(session.document, "outer"))


def test_a_free_drop_on_a_bare_container_keeps_the_other_widget() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <widget class="QPushButton" name="loose">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>Loose</string></property>
  </widget>
  <widget class="QPushButton" name="other">
   <property name="geometry"><rect><x>40</x><y>120</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>Other</string></property>
  </widget>
""",
    )
    with _shown(text) as (session, canvas, host):
        _drag_widget_to(canvas, "other", _widget(canvas, "loose").mapTo(canvas.page_widget(), QPoint(160, 80)))
        other = next(node for node in session.document.iter_preorder() if getattr(node, "object_name", None) == "other")
        assert isinstance(other, WidgetNode)
        geometry = other.prop("geometry")
        assert geometry is not None
        assert session.document.root.layout is None
        assert any("x " in sentence for sentence in host.sentences) or session.log.undo_label() == "Move"


def test_escape_cancels_a_drag() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QPushButton" name="shop"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="receipts"><property name="text"><string>Receipts</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        shop = _widget(canvas, "shop")
        end = shop.mapTo(canvas.page_widget(), QPoint(shop.width() // 2, 4))
        _press_move(canvas, "receipts", end)
        QTest.keyClick(canvas.viewport(), _key("Key_Escape"))
        _flush()
        _release(canvas, end)
        assert _slot_names(session.document, "verticalLayout") == ["shop", "receipts"]
        assert session.log.undo_label() is None


def test_a_drop_into_itself_does_nothing() -> None:
    text = form(
        'class="QGroupBox" name="Form"',
        """
  <property name="title"><string>Box</string></property>
  <layout class="QVBoxLayout" name="inner">
   <item><widget class="QPushButton" name="inside"><property name="text"><string>Inside</string></property></widget></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        before = write_names(session.document)
        inside = _widget(canvas, "inside")
        _drag_widget_to(canvas, "Form", inside.mapTo(canvas.page_widget(), inside.rect().center()))
        assert write_names(session.document) == before
        assert session.log.undo_label() is None


def test_a_spacer_dropped_on_a_form_does_nothing() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="outer">
   <item>
    <layout class="QFormLayout" name="formLayout">
     <item row="0" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
     <item row="0" column="1"><widget class="QLineEdit" name="email"/></item>
    </layout>
   </item>
   <item>
    <spacer name="gap">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
    </spacer>
   </item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        before = write_names(session.document)
        label = _widget(canvas, "emailLabel")
        root = canvas.page_widget()
        assert root is not None
        outer = root.layout()
        assert outer is not None
        spacer = outer.itemAt(1).spacerItem()
        assert spacer is not None
        geom = spacer.geometry()
        start = QPoint(geom.x() + geom.width() // 2, geom.y() + max(geom.height() // 2, 1))
        _drag_points(canvas, start, label.mapTo(root, label.rect().center()))
        assert write_names(session.document) == before
        assert session.log.undo_label() is None
        assert any(isinstance(node, SpacerNode) and node.name == "gap" for node in session.document.iter_preorder())


@pytest.mark.pain("P-4")
def test_a_nested_row_accepts_a_line_edit() -> None:
    text = form(
        'class="QWidget" name="Form"',
        """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QHBoxLayout" name="row">
     <item><widget class="QPushButton" name="shop"><property name="text"><string>Shop</string></property></widget></item>
     <item><widget class="QPushButton" name="receipts"><property name="text"><string>Receipts</string></property></widget></item>
    </layout>
   </item>
   <item><widget class="QLineEdit" name="notes"/></item>
  </layout>
""",
    )
    with _shown(text) as (session, canvas, _host):
        shop = _widget(canvas, "shop")
        receipts = _widget(canvas, "receipts")
        gap_x = (shop.geometry().right() + receipts.geometry().left()) // 2
        gap = shop.mapTo(canvas.page_widget(), QPoint(gap_x - shop.geometry().x(), shop.height() // 2))
        _drag_widget_to(canvas, "notes", gap)
        row = _layout(session.document, "row")
        assert "notes" in _content_names(row)
        outer = _content_names(_layout(session.document, "verticalLayout"))
        assert "notes" not in outer
        assert row.class_name == "QHBoxLayout"
        assert session.log.undo()
        _flush()
        assert "notes" not in _content_names(_layout(session.document, "row"))


def _drag_widget_to(canvas: FormCanvas, name: str, end_on_page: QPoint) -> None:
    widget = _widget(canvas, name)
    root = canvas.page_widget()
    assert root is not None
    start = widget.mapTo(root, widget.rect().center())
    _drag_points(canvas, start, end_on_page)


def _press_move(canvas: FormCanvas, name: str, end_on_page: QPoint) -> None:
    widget = _widget(canvas, name)
    root = canvas.page_widget()
    assert root is not None
    start = _port(canvas, root, widget.mapTo(root, widget.rect().center()))
    end = _port(canvas, root, end_on_page)
    viewport = canvas.viewport()
    QTest.mousePress(viewport, _mouse("LeftButton"), _mods("NoModifier"), start)
    QTest.mouseMove(viewport, end)
    _flush()


def _release(canvas: FormCanvas, end_on_page: QPoint) -> None:
    root = canvas.page_widget()
    assert root is not None
    QTest.mouseRelease(canvas.viewport(), _mouse("LeftButton"), _mods("NoModifier"), _port(canvas, root, end_on_page))
    _flush()


def _drag_points(canvas: FormCanvas, start_on_page: QPoint, end_on_page: QPoint) -> None:
    root = canvas.page_widget()
    assert root is not None
    viewport = canvas.viewport()
    button = _mouse("LeftButton")
    mods = _mods("NoModifier")
    QTest.mousePress(viewport, button, mods, _port(canvas, root, start_on_page))
    QTest.mouseMove(viewport, _port(canvas, root, end_on_page))
    QTest.mouseRelease(viewport, button, mods, _port(canvas, root, end_on_page))
    _flush()


def _widget(canvas: FormCanvas, name: str) -> QWidget:
    root = canvas.page_widget()
    assert root is not None
    if root.objectName() == name:
        return root
    widget = root.findChild(QWidget, name)
    assert widget is not None
    return widget


def _port(canvas: FormCanvas, root: QWidget, point: QPoint) -> QPoint:
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(point))


def _layout(document: UiDocument, name: str) -> LayoutNode:
    found = next(node for node in document.iter_preorder() if isinstance(node, LayoutNode) and node.object_name == name)
    return found


def _content_names(layout: LayoutNode) -> List[str]:
    names = []
    for item in layout.items:
        content = item.content
        if content is None:
            names.append("")
        else:
            names.append(getattr(content, "object_name", "") or getattr(content, "name", "") or content.class_name)
    return names


def _slot_names(document: UiDocument, layout_name: str) -> List[str]:
    return _content_names(_layout(document, layout_name))


def _cells(document: UiDocument, layout_name: str) -> dict:
    found = {}
    for item in _layout(document, layout_name).items:
        content = item.content
        if content is None:
            continue
        name = getattr(content, "object_name", "") or getattr(content, "name", "")
        found[name] = (
            0 if item.row is None else item.row,
            0 if item.column is None else item.column,
            1 if item.rowspan is None else item.rowspan,
            1 if item.colspan is None else item.colspan,
        )
    return found


def write_names(document: UiDocument) -> Tuple[str, ...]:
    names = []
    for node in document.iter_preorder():
        name = getattr(node, "object_name", None) or getattr(node, "name", None) or ""
        names.append("%s:%s" % (type(node).__name__, name))
    return tuple(names)


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)


def _label_texts(document: UiDocument) -> List[str]:
    texts = []
    for node in document.iter_preorder():
        if not isinstance(node, WidgetNode) or node.class_name != "QLabel":
            continue
        value = node.value("text")
        text = getattr(value, "text", None)
        if isinstance(text, str):
            texts.append(text)
    return texts
