# pyright: reportAttributeAccessIssue=false
"""M3.7a canvas regressions. Interactive cases drive a real main window."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog import SetProperty  # noqa: E402
from app.features.form_builder.engine.query.drop_target import DropPayload  # noqa: E402
from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.ui4.nodes import LayoutNode  # noqa: E402
from app.features.form_builder.engine.ui4.values import StringValue  # noqa: E402
from app.features.form_builder.integration.canvas import FormCanvas  # noqa: E402
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, CanvasRect  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.qtside.canvas.core.frame import Caption, Chip, Fill, Stroke  # noqa: E402
from app.features.form_builder.qtside.canvas.core.gesture import PlaceAsked  # noqa: E402
from app.features.form_builder.qtside.canvas.core.palette import MIME_INSERT  # noqa: E402
from app.features.form_builder.qtside.theme.overlay import overlay_palette  # noqa: E402
from app.qt.QtCore import QEvent, QMimeData, QObject, QPoint, QPointF, QRect, QRectF, Qt  # noqa: E402
from app.qt.QtGui import QDragEnterEvent, QDragMoveEvent, QMouseEvent  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QGroupBox,
    QLabel,
    QMenu,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QWidget,
)
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402
from tests.form_builder.qtside.support import opened  # noqa: E402

pytestmark = pytest.mark.unit

_FAR = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>1100</width><height>240</height></rect></property>
  <widget class="QPushButton" name="left">
   <property name="geometry"><rect><x>8</x><y>8</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>Left</string></property>
  </widget>
  <widget class="QPushButton" name="mid">
   <property name="geometry"><rect><x>120</x><y>8</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>Mid</string></property>
  </widget>
  <widget class="QPushButton" name="far">
   <property name="geometry"><rect><x>980</x><y>8</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>Far</string></property>
  </widget>
 </widget>
</ui>
"""

_TITLES = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>520</width><height>360</height></rect></property>
  <widget class="QGroupBox" name="box">
   <property name="geometry"><rect><x>16</x><y>16</y><width>200</width><height>80</height></rect></property>
   <property name="title"><string>Receipt</string></property>
   <widget class="QPushButton" name="child">
    <property name="geometry"><rect><x>8</x><y>28</y><width>80</width><height>28</height></rect></property>
    <property name="text"><string>Child</string></property>
   </widget>
  </widget>
  <widget class="QTabWidget" name="tabs">
   <property name="geometry"><rect><x>16</x><y>120</y><width>280</width><height>140</height></rect></property>
   <property name="currentIndex"><number>0</number></property>
   <widget class="QWidget" name="page">
    <attribute name="title"><string>First</string></attribute>
    <widget class="QPushButton" name="paged">
     <property name="geometry"><rect><x>8</x><y>8</y><width>80</width><height>28</height></rect></property>
     <property name="text"><string>Paged</string></property>
    </widget>
   </widget>
  </widget>
 </widget>
</ui>
"""

_TALL = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>1600</height></rect></property>
  <widget class="QLabel" name="mark">
   <property name="geometry"><rect><x>16</x><y>1500</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>Bottom</string></property>
  </widget>
 </widget>
</ui>
"""

_BARE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>280</height></rect></property>
  <widget class="QFrame" name="frame">
   <property name="geometry"><rect><x>24</x><y>24</y><width>220</width><height>120</height></rect></property>
   <widget class="QPushButton" name="ok">
    <property name="geometry"><rect><x>16</x><y>16</y><width>80</width><height>28</height></rect></property>
    <property name="text"><string>OK</string></property>
   </widget>
  </widget>
 </widget>
</ui>
"""

_NEST = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>280</height></rect></property>
  <widget class="QGroupBox" name="box">
   <property name="geometry"><rect><x>20</x><y>20</y><width>240</width><height>120</height></rect></property>
   <property name="title"><string>Nest</string></property>
   <layout class="QHBoxLayout" name="row"/>
  </widget>
 </widget>
</ui>
"""

_PAGES = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>240</height></rect></property>
  <layout class="QHBoxLayout" name="row">
   <item>
    <widget class="QTabWidget" name="tabs">
     <widget class="QWidget" name="tabPage"><attribute name="title"><string>One</string></attribute></widget>
    </widget>
   </item>
   <item>
    <widget class="QStackedWidget" name="stack">
     <widget class="QWidget" name="stackPage"/>
    </widget>
   </item>
   <item>
    <widget class="QToolBox" name="tools">
     <widget class="QWidget" name="toolPage"><attribute name="label"><string>Tool</string></attribute></widget>
    </widget>
   </item>
   <item>
    <widget class="QGroupBox" name="plain">
     <property name="title"><string>Plain</string></property>
     <property name="minimumSize"><size><width>220</width><height>80</height></size></property>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""

_KEYS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>280</height></rect></property>
  <widget class="QPushButton" name="free">
   <property name="geometry"><rect><x>16</x><y>16</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>Free</string></property>
  </widget>
  <widget class="QFrame" name="holder">
   <property name="geometry"><rect><x>16</x><y>80</y><width>300</width><height>80</height></rect></property>
   <layout class="QHBoxLayout" name="row">
    <item>
     <widget class="QPushButton" name="laid">
      <property name="text"><string>Laid</string></property>
     </widget>
    </item>
   </layout>
  </widget>
 </widget>
</ui>
"""

_WIDE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>220</height></rect></property>
  <layout class="QHBoxLayout" name="row">
   <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
   <item><widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget></item>
  </layout>
 </widget>
</ui>
"""

_DRAG = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>200</height></rect></property>
  <layout class="QVBoxLayout" name="column">
   <item>
    <widget class="QGroupBox" name="box">
     <property name="title"><string>Box</string></property>
     <layout class="QVBoxLayout" name="inner">
      <item>
       <widget class="QPushButton" name="child"><property name="text"><string>Child</string></property></widget>
      </item>
     </layout>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _key(name: str) -> Qt.Key:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _button(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _open(window: MainWindow, qapp: QApplication, path: Path, text: str, width: int = 1400, height: int = 900) -> object:
    path.write_text(text, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    stack = window._center_stack  # noqa: SLF001
    assert stack is not None
    stack.setCurrentIndex(1)
    window.resize(width, height)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def _canvas(surface: object) -> QWidget:
    canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
    assert canvas is not None
    return canvas


def _port(canvas: QWidget, widget: QWidget) -> QPoint:
    host = widget
    while host is not None and host.graphicsProxyWidget() is None:
        host = host.parentWidget()
    assert host is not None
    proxy = host.graphicsProxyWidget()
    assert proxy is not None
    center = widget.rect().center()
    on_host = center if widget is host else widget.mapTo(host, center)
    return canvas.mapFromScene(proxy.mapToScene(on_host))


def _click(canvas: QWidget, widget: QWidget, modifier: Optional[Qt.KeyboardModifier] = None) -> None:
    QTest.mouseClick(
        canvas.viewport(),
        _button("LeftButton"),
        modifier or _mod("NoModifier"),
        _port(canvas, widget),
    )


class _PaintCount(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == getattr(getattr(QEvent, "Type", QEvent), "Paint"):
            self.count += 1
        return False


def test_a_far_widget_is_not_repainted_for_selection_or_a_text_edit(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "far.ui", _FAR)
        canvas = _canvas(surface)
        root = canvas.page_widget()
        assert root is not None
        far = root.findChild(QPushButton, "far")
        left = root.findChild(QPushButton, "left")
        mid = root.findChild(QPushButton, "mid")
        assert far is not None and left is not None and mid is not None
        counter = _PaintCount()
        far.installEventFilter(counter)
        qapp.processEvents()
        counter.count = 0
        _click(canvas, left)
        qapp.processEvents()
        _click(canvas, mid)
        qapp.processEvents()
        assert counter.count == 0
        document = surface._session.document  # type: ignore[attr-defined]
        owner = document.by_name("left")[0]
        surface._session.log.execute(SetProperty(owner, "toolTip", StringValue("note")))  # type: ignore[attr-defined]
        qapp.processEvents()
        assert counter.count == 0
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_a_child_chip_clears_the_group_title_and_the_tab_bar(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "titles.ui", _TITLES)
        canvas = _canvas(surface)
        root = canvas.page_widget()
        assert root is not None
        child = root.findChild(QPushButton, "child")
        paged = root.findChild(QPushButton, "paged")
        box = root.findChild(QGroupBox, "box")
        tabs = root.findChild(QTabWidget, "tabs")
        assert child is not None and paged is not None and box is not None and tabs is not None
        _click(canvas, child)
        qapp.processEvents()
        title = _local_band(canvas, box, 0, 0, box.width(), box.contentsRect().top())
        chip = _chip_for(canvas, surface, "child")
        assert title.height > 0
        assert not chip.intersects(title)
        _click(canvas, paged)
        qapp.processEvents()
        bar = tabs.tabBar()
        band = _local_band(canvas, tabs, bar.x(), bar.y(), bar.width(), bar.height())
        chip = _chip_for(canvas, surface, "paged")
        assert not chip.intersects(band)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_the_page_name_stays_clear_of_the_pinned_caption(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "tall.ui", _TALL, 1080, 600)
        canvas = _canvas(surface)
        name = canvas.findChild(QLabel, "formBuilder.name")
        title = canvas.findChild(QWidget, "formBuilder.pageTitle")
        assert name is not None and title is not None
        bar = canvas.verticalScrollBar()
        assert bar.maximum() > 0
        step = max(1, bar.maximum() // 6)
        value = 0
        while value <= bar.maximum():
            bar.setValue(value)
            qapp.processEvents()
            if name.isVisible() and title.isVisible():
                assert not name.geometry().intersects(title.geometry())
            value += step
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_clicking_the_no_layout_chip_opens_the_popover(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "bare.ui", _BARE, 1080, 600)
        canvas = _canvas(surface)
        frame = canvas.overlay()  # type: ignore[attr-defined]
        chip = next(item for item in frame.items if isinstance(item, Chip) and item.text == "No layout")
        port = canvas.mapFromScene(QPointF(chip.rect.x + chip.rect.width / 2, chip.rect.y + chip.rect.height / 2))
        QTest.mouseClick(canvas.viewport(), _button("LeftButton"), _mod("NoModifier"), port)
        qapp.processEvents()
        menu = surface.findChild(QMenu, "formBuilder.layoutPopover")  # type: ignore[attr-defined]
        assert isinstance(menu, QMenu)
        assert menu.isVisible()
    finally:
        menu = surface.findChild(QMenu, "formBuilder.layoutPopover")  # type: ignore[attr-defined]
        if menu is not None:
            menu.close()
        shutdown_main_window_for_test(window, qapp)


def test_the_canvas_paints_no_ghost_while_the_pointer_is_on_the_outline(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "ghost.ui", _FAR)
        canvas = _canvas(surface)
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
        assert tree is not None
        controller = canvas._controller  # type: ignore[attr-defined]
        spot = QPoint(24, 24)
        before = _pixel(canvas, spot)
        mime = QMimeData()
        mime.setData(MIME_INSERT, b"QPushButton")
        enter = QDragEnterEvent(spot, _drop_action(), mime, _button("LeftButton"), _mod("NoModifier"))
        canvas.dragEnterEvent(enter)
        qapp.processEvents()
        assert controller.ghost_shown()
        assert _pixel(canvas, spot) != before
        move = QDragMoveEvent(QPoint(8, 8), _drop_action(), mime, _button("LeftButton"), _mod("NoModifier"))
        # Qt drops a DragMove that has no QDrag in progress before object filters.
        pane = tree.parent()
        assert pane.eventFilter(tree.viewport(), move)
        qapp.processEvents()
        assert not controller.ghost_shown()
        assert _pixel(canvas, spot) == before
        back = QDragMoveEvent(spot, _drop_action(), mime, _button("LeftButton"), _mod("NoModifier"))
        canvas.dragMoveEvent(back)
        qapp.processEvents()
        assert controller.ghost_shown()
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_an_empty_nested_layout_indicator_covers_the_empty_mark() -> None:
    _require()
    body = _NEST
    with opened(body) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(640, 480)
        parent.show()
        QApplication.instance().processEvents()  # type: ignore[union-attr]
        layout = next(node for node in session.document.iter_preorder() if isinstance(node, LayoutNode) and node.object_name == "row")
        qlayout = realizer.layout_for(layout.id)
        assert qlayout is not None
        host = qlayout.parentWidget()
        assert host is not None
        page = canvas.page_widget()
        assert page is not None
        center = host.mapTo(page, qlayout.geometry().center())
        proxy = page.graphicsProxyWidget()
        assert proxy is not None
        scene = proxy.mapToScene(center)
        canvas._controller.post(PlaceAsked(CanvasPoint(int(scene.x()), int(scene.y())), DropPayload("widget"), "QPushButton"))  # noqa: SLF001
        QApplication.instance().processEvents()  # type: ignore[union-attr]
        items = canvas.overlay().items
        mark = next(item.rect for item in items if isinstance(item, Stroke) and item.role == "layout_faint")
        indicator = next(
            item.rect
            for item in items
            if isinstance(item, Stroke) and item.role == "select" and item.style == "dashed" and item.width == 1.5
        )
        assert mark.width >= 48 and mark.height >= 32
        assert indicator == mark
        assert any(isinstance(item, Fill) and item.role == "drop_fill" and item.rect == mark for item in items)
        canvas.dispose()
        parent.deleteLater()


def test_a_refused_drop_over_an_empty_container_hides_its_drop_hint() -> None:
    _require()
    with opened(_NEST) as (session, realizer):
        parent = QWidget()
        parent.resize(640, 480)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(640, 480)
        parent.show()
        QApplication.instance().processEvents()  # type: ignore[union-attr]
        layout = next(node for node in session.document.iter_preorder() if isinstance(node, LayoutNode) and node.object_name == "row")
        qlayout = realizer.layout_for(layout.id)
        assert qlayout is not None
        host = qlayout.parentWidget()
        page = canvas.page_widget()
        assert host is not None and page is not None
        proxy = page.graphicsProxyWidget()
        assert proxy is not None
        scene = proxy.mapToScene(host.mapTo(page, qlayout.geometry().center()))
        hints = lambda: [i for i in canvas.overlay().items if isinstance(i, Caption) and i.lines == ("Drop widgets here",)]  # noqa: E731
        assert hints()
        canvas._controller.post(PlaceAsked(CanvasPoint(int(scene.x()), int(scene.y())), DropPayload("widget", wizard_page=True), "QWidget"))  # noqa: SLF001
        QApplication.instance().processEvents()  # type: ignore[union-attr]
        assert any(isinstance(i, Stroke) and i.role == "problem" for i in canvas.overlay().items)
        assert not hints()
        canvas.dispose()
        parent.deleteLater()


def test_empty_pages_name_the_page_and_a_group_box_does_not() -> None:
    _require()
    with opened(_PAGES) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 400)
        canvas = FormCanvas(session, realizer, _Host(), parent)
        canvas.resize(900, 400)
        parent.show()
        QApplication.instance().processEvents()  # type: ignore[union-attr]
        lines = [item.lines for item in canvas.overlay().items if isinstance(item, Caption)]
        assert lines.count(("Drop widgets on this page",)) >= 3
        assert ("Drop widgets here",) in lines
        canvas.dispose()
        parent.deleteLater()


def test_the_second_refused_drop_shows_the_plain_toast(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "drag.ui", _DRAG)
        canvas = _canvas(surface)
        root = canvas.page_widget()
        assert root is not None
        box = root.findChild(QGroupBox, "box")
        child = root.findChild(QPushButton, "child")
        assert box is not None and child is not None
        title = _port_local(canvas, box, QPoint(box.width() // 2, max(1, box.contentsRect().top() // 2)))
        onto = _port(canvas, child)
        _drag(canvas, title, onto)
        qapp.processEvents()
        assert _toast(surface) != "A widget can't go inside itself."
        _drag(canvas, title, onto)
        qapp.processEvents()
        assert _toast(surface) == "A widget can't go inside itself."
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_ctrl_alt_arrow_leaves_a_free_widget_and_a_laid_widget(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "keys.ui", _KEYS)
        canvas = _canvas(surface)
        root = canvas.page_widget()
        assert root is not None
        for name in ("free", "laid"):
            widget = root.findChild(QPushButton, name)
            assert widget is not None
            _click(canvas, widget)
            qapp.processEvents()
            before = _snapshot(surface)
            canvas.viewport().setFocus()
            for modifiers in (
                _mod("ControlModifier") | _mod("AltModifier"),
                _mod("ControlModifier") | _mod("AltModifier") | _mod("ShiftModifier"),
            ):
                for key in ("Key_Left", "Key_Right", "Key_Up", "Key_Down"):
                    QTest.keyClick(canvas.viewport(), _key(key), modifiers)
                    qapp.processEvents()
            assert _snapshot(surface) == before
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_ctrl_click_in_the_wide_copy_selects_both_widgets(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "wide.ui", _WIDE)
        canvas = _canvas(surface)
        QTest.mouseClick(window.findChild(QWidget, "formBuilder.twoWidths"), _button("LeftButton"))
        qapp.processEvents()
        one, two = _mirror_pair(canvas, "one", "two")
        _click(canvas, one, _mod("ControlModifier"))
        qapp.processEvents()
        _click(canvas, two, _mod("ControlModifier"))
        qapp.processEvents()
        ids = surface._session.selection.state.ids  # type: ignore[attr-defined]
        assert len(ids) == 2
        design = canvas.page_widget()
        assert design is not None
        for widget in (design.findChild(QPushButton, "one"), design.findChild(QPushButton, "two"), one, two):
            assert widget is not None
            assert _stroked(canvas, widget)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_a_selected_layout_is_framed_on_the_wide_copy(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "wide.ui", _WIDE)
        canvas = _canvas(surface)
        QTest.mouseClick(window.findChild(QWidget, "formBuilder.twoWidths"), _button("LeftButton"))
        qapp.processEvents()
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
        assert tree is not None
        item = _row(tree, "row")
        rect = tree.visualItemRect(item)
        QTest.mouseClick(tree.viewport(), _button("LeftButton"), _mod("NoModifier"), rect.center())
        qapp.processEvents()
        layout = canvas.preview._mirror.layout_for(  # type: ignore[attr-defined]
            surface._session.selection.state.current  # type: ignore[attr-defined]
        )
        assert layout is not None
        host = layout.parentWidget()
        assert host is not None
        assert _edge_pixel(canvas, host, layout.geometry()) is not None
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_two_widths_keeps_the_zoom_and_clears_its_chips(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "wide.ui", _WIDE, 1080, 600)
        _assert_widths(window, surface, qapp, 400)
        _assert_widths(window, surface, qapp, 2000)
        window.resize(1400, 900)
        qapp.processEvents()
        _assert_widths(window, surface, qapp, 400)
        _assert_widths(window, surface, qapp, 2000)
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_root_layout_ticks_lie_on_the_page_edges(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "wide.ui", _WIDE)
        canvas = _canvas(surface)
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
        assert tree is not None
        item = _row(tree, "row")
        rect = tree.visualItemRect(item)
        QTest.mouseClick(tree.viewport(), _button("LeftButton"), _mod("NoModifier"), rect.center())
        qapp.processEvents()
        page = canvas._stage.view_map().page_rect()  # type: ignore[attr-defined]
        ticks = [
            item
            for item in canvas.overlay().items  # type: ignore[attr-defined]
            if isinstance(item, Stroke)
            and item.role == "layout"
            and item.width == 1.5
            and _anchor_tick(item.rect, page)
        ]
        assert len(ticks) == 4
        chips = [chip.rect for chip in canvas.overlay().items if isinstance(chip, Chip)]  # type: ignore[attr-defined]
        for tick in ticks:
            assert all(not tick.rect.intersects(chip) for chip in chips)
    finally:
        shutdown_main_window_for_test(window, qapp)


def _assert_widths(window: MainWindow, surface: object, qapp: QApplication, wide: int) -> None:
    canvas = _canvas(surface)
    zoom = window.findChild(QWidget, "formBuilder.zoomLabel")
    assert zoom is not None
    before = zoom.text()
    scale = canvas._stage.view_map().factor  # type: ignore[attr-defined]
    canvas.preview.set_wide(wide)  # type: ignore[attr-defined]
    button = window.findChild(QWidget, "formBuilder.twoWidths")
    assert button is not None
    if canvas.preview.widths_open:  # type: ignore[attr-defined]
        QTest.mouseClick(button, _button("LeftButton"))
        qapp.processEvents()
    QTest.mouseClick(button, _button("LeftButton"))
    qapp.processEvents()
    assert zoom.text() == before
    assert canvas._stage.view_map().factor == scale  # type: ignore[attr-defined]
    _assert_clear_chips(canvas)
    QTest.mouseClick(button, _button("LeftButton"))
    qapp.processEvents()


def _assert_clear_chips(canvas: QWidget) -> None:
    title = canvas.findChild(QWidget, "formBuilder.pageTitle")
    size = canvas.findChild(QWidget, "formBuilder.sizeReadout")
    assert title is not None and size is not None
    blockers = [title.geometry(), size.geometry(), _page_rect(canvas)]
    mirror = canvas.preview._mirror_proxy  # type: ignore[attr-defined]
    if mirror is not None and mirror.isVisible():
        blockers.append(_scene_rect(canvas, mirror.sceneBoundingRect()))
    for name in ("formBuilder.narrowChip", "formBuilder.wideChip", "formBuilder.previewPill"):
        chip = canvas.findChild(QWidget, name)
        if chip is None or not chip.isVisible():
            continue
        assert all(not chip.geometry().intersects(other) for other in blockers)


def _snapshot(surface: object) -> Tuple[int, Tuple[int, ...], bool]:
    session = surface._session  # type: ignore[attr-defined]
    state = session.selection.state
    return (session.document.revision, tuple(int(node) for node in state.ids), session.log.can_undo())


def _toast(surface: object) -> str:
    label = surface.findChild(QLabel, "formBuilder.toastText")  # type: ignore[attr-defined]
    if label is None or not label.isVisible():
        return ""
    return label.text()


def _drag(canvas: QWidget, start: QPoint, end: QPoint) -> None:
    QTest.mousePress(canvas.viewport(), _button("LeftButton"), _mod("NoModifier"), start)
    step = QPoint(start)
    for _index in range(4):
        step = QPoint((step.x() * 3 + end.x()) // 4, (step.y() * 3 + end.y()) // 4)
        _post_move(canvas, step)
    _post_move(canvas, end)
    QTest.mouseRelease(canvas.viewport(), _button("LeftButton"), _mod("NoModifier"), end)


def _post_move(canvas: QWidget, at: QPoint) -> None:
    kind = getattr(getattr(QEvent, "Type", QEvent), "MouseMove")
    event = QMouseEvent(kind, QPointF(at), _button("LeftButton"), _button("LeftButton"), _mod("NoModifier"))
    QApplication.sendEvent(canvas.viewport(), event)


def _chip_for(canvas: QWidget, surface: object, name: str):
    document = surface._session.document  # type: ignore[attr-defined]
    node = document.by_name(name)[0]
    frame = canvas.overlay()  # type: ignore[attr-defined]
    rects = [rect for rect, owner in frame.chips if owner == node]
    assert rects
    return rects[0]


def _local_band(canvas: QWidget, widget: QWidget, x: int, y: int, width: int, height: int) -> CanvasRect:
    root = canvas.page_widget()
    assert root is not None
    top_left = widget.mapTo(root, QPoint(x, y))
    bottom_right = widget.mapTo(root, QPoint(x + width, y + height))
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    scene_tl = proxy.mapToScene(top_left)
    scene_br = proxy.mapToScene(bottom_right)
    return CanvasRect(
        int(min(scene_tl.x(), scene_br.x())),
        int(min(scene_tl.y(), scene_br.y())),
        max(1, int(abs(scene_br.x() - scene_tl.x()))),
        max(1, int(abs(scene_br.y() - scene_tl.y()))),
    )


def _port_local(canvas: QWidget, widget: QWidget, local: QPoint) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    on_root = widget.mapTo(root, local)
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(on_root))


def _pixel(canvas: QWidget, at: QPoint) -> int:
    image = canvas.viewport().grab().toImage()
    return int(image.pixel(at.x(), at.y()))


def _drop_action() -> Qt.DropAction:
    return getattr(getattr(Qt, "DropAction", Qt), "CopyAction")


def _mirror_pair(canvas: QWidget, first: str, second: str) -> Tuple[QWidget, QWidget]:
    design = canvas.page_widget()
    assert design is not None
    found = []
    for proxy in canvas.scene().items():  # type: ignore[attr-defined]
        widget = proxy.widget() if hasattr(proxy, "widget") else None
        if widget is None or widget is design:
            continue
        one = widget.findChild(QPushButton, first)
        two = widget.findChild(QPushButton, second)
        if one is not None and two is not None:
            found.append((one, two))
    assert found
    return found[0]


def _stroked(canvas: QWidget, widget: QWidget) -> bool:
    proxy, scene = _widget_scene(widget)
    if proxy is None:
        return False
    canvas.centerOn(scene.center())  # type: ignore[attr-defined]
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    image = canvas.viewport().grab().toImage()
    top = canvas.mapFromScene(QPointF(scene.center().x(), scene.top()))  # type: ignore[attr-defined]
    want = _select_rgb()
    for dy in range(-8, 6):
        point = QPoint(int(top.x()), int(top.y()) + dy)
        if not image.rect().contains(point):
            continue
        color = image.pixelColor(point)
        if abs(color.red() - want[0]) < 48 and abs(color.green() - want[1]) < 48 and abs(color.blue() - want[2]) < 48:
            return True
    return False


def _widget_scene(widget: QWidget):
    host = widget
    while host is not None and host.graphicsProxyWidget() is None:
        host = host.parentWidget()
    if host is None:
        return None, None
    proxy = host.graphicsProxyWidget()
    origin = widget.mapTo(host, QPoint(0, 0))
    local = QRectF(float(origin.x()), float(origin.y()), float(widget.width()), float(widget.height()))
    return proxy, proxy.mapRectToScene(local)


def _select_rgb() -> Tuple[int, int, int]:
    text = overlay_palette(False).select[1:]
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _edge_pixel(canvas: QWidget, root: QWidget, local) -> Optional[int]:
    proxy = root.graphicsProxyWidget()
    if proxy is None:
        host = root
        while host is not None and host.graphicsProxyWidget() is None:
            host = host.parentWidget()
        if host is None:
            return None
        proxy = host.graphicsProxyWidget()
        origin = root.mapTo(host, local.topLeft() if hasattr(local, "topLeft") else QPoint(0, 0))
    else:
        origin = local.topLeft() if hasattr(local, "topLeft") else QPoint(int(local.x()), int(local.y()))
    scene = proxy.mapToScene(QPoint(int(origin.x()) + 4, int(origin.y())))
    port = canvas.mapFromScene(QPointF(scene.x(), scene.y() - 2))
    image = canvas.viewport().grab().toImage()
    if not image.rect().contains(port):
        return None
    return int(image.pixel(port.x(), port.y()))


def _row(tree: QTreeWidget, text: str) -> object:
    found = None

    def walk(item: object) -> None:
        nonlocal found
        if item.text(0) == text:  # type: ignore[attr-defined]
            found = item
        for index in range(item.childCount()):  # type: ignore[attr-defined]
            child = item.child(index)  # type: ignore[attr-defined]
            if child is not None:
                walk(child)

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)
        if top is not None:
            walk(top)
    assert found is not None
    return found


def _anchor_tick(rect: object, page: object) -> bool:
    horizontal = rect.width == 8 and rect.height == 2
    vertical = rect.width == 2 and rect.height == 8
    on_left = horizontal and abs(rect.x - page.x) <= 1
    on_right = horizontal and abs((rect.x + rect.width) - (page.x + page.width)) <= 1
    on_top = vertical and abs(rect.y - page.y) <= 1
    on_bottom = vertical and abs((rect.y + rect.height) - (page.y + page.height)) <= 1
    return on_left or on_right or on_top or on_bottom


def _page_rect(canvas: QWidget) -> QRect:
    root = canvas.page_widget()
    assert root is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return _scene_rect(canvas, proxy.sceneBoundingRect())


def _scene_rect(canvas: QWidget, scene: object) -> QRect:
    top_left = canvas.mapFromScene(scene.topLeft())  # type: ignore[attr-defined]
    bottom_right = canvas.mapFromScene(scene.bottomRight())  # type: ignore[attr-defined]
    return QRect(top_left, bottom_right).normalized()


class _Host:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

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



class _PaintRegions(QObject):
    """Review repro: the union of regions the viewport actually repainted."""

    def __init__(self) -> None:
        super().__init__()
        self.rects = []

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == getattr(getattr(QEvent, "Type", QEvent), "Paint"):
            self.rects.extend(QRect(rect) for rect in event.region())
        return False

    def covers(self, rect: QRect) -> bool:
        from app.qt.QtGui import QRegion

        painted = QRegion()
        for part in self.rects:
            painted = painted.united(QRegion(part))
        return QRegion(rect).subtracted(painted).isEmpty()


_WIDE_FREE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>200</height></rect></property>
  <widget class="QPushButton" name="one">
   <property name="geometry"><rect><x>8</x><y>8</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>One</string></property>
  </widget>
  <widget class="QPushButton" name="two">
   <property name="geometry"><rect><x>200</x><y>120</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>Two</string></property>
  </widget>
 </widget>
</ui>
"""


def test_review_wide_copy_stroke_is_repainted_when_the_selection_moves(qapp: QApplication, tmp_path: Path) -> None:
    """Clipped damage covers only design-copy frame items; the wide copy keeps stale strokes."""
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "wide.ui", _WIDE_FREE, 2400, 1400)
        canvas = _canvas(surface)
        QTest.mouseClick(window.findChild(QWidget, "formBuilder.twoWidths"), _button("LeftButton"))
        qapp.processEvents()
        one, two = _mirror_pair(canvas, "one", "two")
        session = surface._session  # type: ignore[attr-defined]
        first = session.document.by_name("one")[0]
        second = session.document.by_name("two")[0]
        # Warm up: the first selection after open builds the inspector and repaints everything.
        for node in (first, second, first):
            session.selection.set((node,), source=SelectionSource.CANVAS)
            qapp.processEvents()
        regions = _PaintRegions()
        canvas.viewport().installEventFilter(regions)
        session.selection.set((second,), source=SelectionSource.CANVAS)
        qapp.processEvents()
        canvas.viewport().removeEventFilter(regions)
        for widget in (one, two):
            _proxy, scene = _widget_scene(widget)
            port = canvas.mapFromScene(scene).boundingRect()  # type: ignore[attr-defined]
            port = port.intersected(canvas.viewport().rect())
            assert not port.isEmpty()
            # The old stroke on "one" must be erased and the new one on "two" drawn.
            assert regions.covers(port), (widget.objectName(), port)
    finally:
        shutdown_main_window_for_test(window, qapp)


def _long_form(count: int) -> str:
    items = "".join(
        '<item><widget class="QPushButton" name="b%03d"><property name="text"><string>B%d</string></property></widget></item>'
        % (index, index)
        for index in range(count)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><ui version="4.0"><class>Form</class>'
        '<widget class="QWidget" name="Form"><layout class="QVBoxLayout" name="column">%s</layout></widget></ui>' % items
    )


def test_selecting_an_off_screen_widget_scrolls_its_outline_row_into_view(qapp: QApplication, tmp_path: Path) -> None:
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "long.ui", _long_form(120))
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
        assert tree is not None
        session = surface._session  # type: ignore[attr-defined]
        last = session.document.by_name("b119")[0]
        session.selection.set((last,), source=SelectionSource.CANVAS)
        qapp.processEvents()
        item = _row(tree, "b119")
        assert tree.viewport().rect().contains(tree.visualItemRect(item))
    finally:
        shutdown_main_window_for_test(window, qapp)


class _LayoutRequests(QObject):
    def __init__(self, watched: QWidget) -> None:
        super().__init__()
        self.watched = watched
        self.count = 0

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if obj is self.watched and event.type() == getattr(getattr(QEvent, "Type", QEvent), "LayoutRequest"):
            self.count += 1
        return False


def test_selecting_another_widget_does_not_relayout_the_inspector_header(qapp: QApplication, tmp_path: Path) -> None:
    """The header's class line and crumbs change text on every select. That must
    not invalidate the header, which re-lays out every shell ancestor up to the
    MainWindow (about 17 ms of a 24 ms select at 1000 widgets)."""
    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "keys.ui", _KEYS)
        session = surface._session  # type: ignore[attr-defined]
        pane = surface.findChild(QWidget, "formBuilder.inspectorHeader")  # type: ignore[attr-defined]
        assert pane is not None
        ids = [session.document.by_name(name)[0] for name in ("free", "holder", "laid")]
        for node in ids:
            session.selection.set((node,), source=SelectionSource.CANVAS)
            qapp.processEvents()
        counter = _LayoutRequests(pane)
        qapp.installEventFilter(counter)
        try:
            for node in ids:
                session.selection.set((node,), source=SelectionSource.CANVAS)
                qapp.processEvents()
        finally:
            qapp.removeEventFilter(counter)
        assert counter.count == 0
    finally:
        shutdown_main_window_for_test(window, qapp)


_WIDE_COLUMN = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="column">
   <item><widget class="QPushButton" name="one"><property name="text"><string>One</string></property></widget></item>
   <item><widget class="QPushButton" name="two"><property name="text"><string>Two</string></property></widget></item>
  </layout>
 </widget>
</ui>
"""


@pytest.mark.parametrize("select_first", [False, True])
def test_two_widths_overlay_matches_the_narrowed_design_page(
    qapp: QApplication, tmp_path: Path, select_first: bool
) -> None:
    """Two widths narrows the design page without a ChangeSet. At 100% (no refit
    to hide it) the selection stroke must follow the narrowed widget, and each
    width caption sits above its own copy, clear of the page name."""
    from app.features.form_builder.qtside.canvas.core.gesture import ZoomAsked
    from app.features.form_builder.qtside.canvas.core.space import ZoomTo

    _require()
    window = MainWindow(state_root=str(tmp_path / "state"))
    try:
        surface = _open(window, qapp, tmp_path / "column.ui", _WIDE_COLUMN)
        canvas = _canvas(surface)
        session = surface._session  # type: ignore[attr-defined]
        two = session.document.by_name("two")[0]
        canvas.send(ZoomAsked(ZoomTo(1.0)))  # type: ignore[attr-defined]
        qapp.processEvents()
        if select_first:
            session.selection.set((two,), source=SelectionSource.OUTLINE)
            qapp.processEvents()
        QTest.mouseClick(window.findChild(QWidget, "formBuilder.twoWidths"), _button("LeftButton"))
        qapp.processEvents()
        if not select_first:
            session.selection.set((two,), source=SelectionSource.OUTLINE)
            qapp.processEvents()
        page = canvas.page_widget()
        assert page is not None
        button = page.findChild(QPushButton, "two")
        assert button is not None
        _proxy, live = _widget_scene(button)
        strokes = [
            item.rect
            for item in canvas.overlay().items  # type: ignore[attr-defined]
            if isinstance(item, Stroke) and item.role == "select" and item.width == 2
        ]
        assert strokes
        stroke = strokes[0]
        assert live is not None
        assert abs(stroke.x - live.x()) <= 2 and abs(stroke.y - live.y()) <= 2
        assert abs(stroke.width - live.width()) <= 4 and abs(stroke.height - live.height()) <= 4
        name = canvas.findChild(QLabel, "formBuilder.name")
        narrow = canvas.findChild(QLabel, "formBuilder.narrowChip")
        wide = canvas.findChild(QWidget, "formBuilder.wideChip")
        assert narrow is not None and wide is not None
        if name is not None and name.isVisible():
            assert not narrow.geometry().intersects(name.geometry())
        mirror = canvas.preview._mirror_proxy  # type: ignore[attr-defined]
        top = canvas.mapFromScene(mirror.sceneBoundingRect().topLeft())  # type: ignore[attr-defined]
        assert wide.geometry().bottom() < top.y() <= wide.geometry().bottom() + 24
        design = canvas.mapFromScene(canvas._stage.proxy.sceneBoundingRect().topLeft())  # type: ignore[attr-defined]
        assert narrow.geometry().bottom() < design.y()
    finally:
        shutdown_main_window_for_test(window, qapp)
