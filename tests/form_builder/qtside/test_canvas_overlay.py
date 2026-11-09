# pyright: reportAttributeAccessIssue=false
"""Hover, frames, spacers, and chips on the realized canvas."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pytest

from app.qt.QtCore import QEvent, QPoint, QRect, Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QMouseEvent, QPalette  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDockWidget,
    QGroupBox,
    QLabel,
    QTabWidget,
    QToolBox,
    QWidget,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.reader import UiReadError
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import Chip, Spring, Stroke
from app.features.form_builder.qtside.canvas.core.gesture import ZoomAsked
from app.features.form_builder.qtside.canvas.core.chips import CHIP_GAP
from app.features.form_builder.qtside.canvas.core.space import CanvasRect, ZoomFit, ZoomTo
from app.features.form_builder.qtside.canvas.core.words import no_layout_text
from app.features.form_builder.qtside.theme.chrome import on_accent_for
from app.shell.theme_tokens import tokens_from_palette
from app.features.form_builder.qtside.realize import NODE_ID_PROPERTY, Realizer
from app.features.form_builder.qtside.canvas.core.structure import managed_container
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"
_LOADABLE = ("synthetic", "qt_examples")

BUTTON = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)

SPACER = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="ok">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
   <item>
    <spacer name="verticalSpacer">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
    </spacer>
   </item>
  </layout>
""",
)

BARE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QFrame" name="box">
   <property name="geometry"><rect><x>30</x><y>30</y><width>240</width><height>160</height></rect></property>
   <widget class="QPushButton" name="ok">
    <property name="geometry"><rect><x>20</x><y>20</y><width>80</width><height>28</height></rect></property>
    <property name="text"><string>OK</string></property>
   </widget>
  </widget>
""",
)


INVOICE = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry"><rect><x>0</x><y>0</y><width>620</width><height>520</height></rect></property>
  <property name="windowTitle"><string>Invoice</string></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item>
    <widget class="QGroupBox" name="customerGroup">
     <property name="title"><string>Customer</string></property>
     <layout class="QFormLayout" name="customerForm">
      <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
      <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
      <item row="1" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
      <item row="1" column="1"><widget class="QLineEdit" name="emailEdit"><property name="placeholderText"><string>name@example.com</string></property></widget></item>
      <item row="2" column="0"><widget class="QLabel" name="addressLabel"><property name="text"><string>Address</string></property></widget></item>
      <item row="2" column="1"><widget class="QPlainTextEdit" name="addressEdit"><property name="maximumSize"><size><width>16777215</width><height>48</height></size></property></widget></item>
      <item row="3" column="0"><widget class="QLabel" name="dateLabel"><property name="text"><string>Date</string></property></widget></item>
      <item row="3" column="1"><widget class="QDateEdit" name="dateEdit"/></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QGroupBox" name="optionsGroup">
     <property name="title"><string>Options</string></property>
     <property name="minimumSize"><size><width>0</width><height>90</height></size></property>
     <widget class="QCheckBox" name="taxCheck"><property name="geometry"><rect><x>16</x><y>28</y><width>120</width><height>22</height></rect></property><property name="text"><string>Charge tax</string></property></widget>
     <widget class="QCheckBox" name="paidCheck"><property name="geometry"><rect><x>16</x><y>56</y><width>120</width><height>22</height></rect></property><property name="text"><string>Paid</string></property></widget>
     <widget class="QComboBox" name="termsCombo"><property name="geometry"><rect><x>200</x><y>28</y><width>140</width><height>24</height></rect></property></widget>
     <widget class="QSpinBox" name="discountSpin"><property name="geometry"><rect><x>200</x><y>58</y><width>80</width><height>24</height></rect></property></widget>
     <widget class="QRadioButton" name="netRadio"><property name="geometry"><rect><x>380</x><y>28</y><width>100</width><height>22</height></rect></property><property name="text"><string>Net 30</string></property></widget>
     <widget class="QRadioButton" name="codRadio"><property name="geometry"><rect><x>380</x><y>56</y><width>100</width><height>22</height></rect></property><property name="text"><string>COD</string></property></widget>
    </widget>
   </item>
   <item>
    <widget class="QTableWidget" name="linesTable"/>
   </item>
   <item>
    <layout class="QGridLayout" name="totalsGrid">
     <item row="0" column="0"><widget class="QLabel" name="subtotalLabel"><property name="text"><string>Subtotal</string></property></widget></item>
     <item row="0" column="1"><widget class="QLineEdit" name="subtotalEdit"><property name="readOnly"><bool>true</bool></property></widget></item>
     <item row="1" column="0"><widget class="QLabel" name="taxLabel"><property name="text"><string>Tax</string></property></widget></item>
     <item row="1" column="1"><widget class="QLineEdit" name="taxEdit"/></item>
     <item row="2" column="0"><widget class="QLabel" name="totalLabel"><property name="text"><string>Total</string></property></widget></item>
     <item row="2" column="1"><widget class="QLineEdit" name="totalEdit"/></item>
    </layout>
   </item>
   <item>
    <layout class="QHBoxLayout" name="buttonRow">
     <item><widget class="QPushButton" name="printButton"><property name="text"><string>Print</string></property></widget></item>
     <item><spacer name="buttonSpacer"><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
     <item><widget class="QPushButton" name="cancelButton"><property name="text"><string>Cancel</string></property></widget></item>
     <item><widget class="QPushButton" name="saveButton"><property name="text"><string>Save invoice</string></property></widget></item>
    </layout>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _Host:
    def __init__(self) -> None:
        self.hovered: List[object] = []

    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        self.hovered.append(node)

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None

    def open_context_menu(self, node: object, at: object) -> None:
        return None


def test_hover_names_the_widget_under_the_pointer() -> None:
    host = _Host()
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, host)
        _move(canvas, "ok")
        assert host.hovered[-1] == _id(session.document, "ok")
        assert any(isinstance(item, Stroke) and item.role == "hover" for item in canvas.overlay().items)
        canvas.dispose()
        parent.deleteLater()


def test_a_selected_widget_has_a_frame() -> None:
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host())
        _click(canvas, "ok")
        assert session.selection.state.current == _id(session.document, "ok")
        assert any(isinstance(item, Stroke) and item.role == "select" for item in canvas.overlay().items)
        canvas.dispose()
        parent.deleteLater()


def test_a_spacer_draws_a_spring() -> None:
    with opened(SPACER) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host())
        assert any(isinstance(item, Spring) for item in canvas.overlay().items)
        canvas.dispose()
        parent.deleteLater()


def test_a_container_without_a_layout_shows_a_chip_beside_its_child() -> None:
    with opened(BARE) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host())
        chips = [item for item in canvas.overlay().items if isinstance(item, Chip) and item.text == "No layout"]
        assert len(chips) == 1
        button = _widget_rect(canvas, "ok")
        assert not chips[0].rect.intersects(button)
        canvas.dispose()
        parent.deleteLater()


@pytest.mark.timeout(180)
def test_chips_do_not_cover_content_on_loadable_corpus_forms() -> None:
    checked = 0
    for path in _forms():
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            with opened(text, str(path)) as (session, realizer):
                root = realizer.root_widget
                if root is None or root.width() <= 0 or root.height() <= 0:
                    continue
                canvas, parent = _canvas(session, realizer, _Host())
                try:
                    _assert_clear(canvas, session, realizer, path)
                    for node in session.document.iter_preorder():
                        if not isinstance(node, WidgetNode):
                            continue
                        if realizer.widget_for(node.id) is None:
                            continue
                        session.selection.set((node.id,), current=node.id, source=SelectionSource.CANVAS)
                        _flush()
                        _assert_clear(canvas, session, realizer, path)
                    _assert_zoom_widths(canvas, session, realizer, path)
                    checked += 1
                finally:
                    canvas.dispose()
                    parent.deleteLater()
                    _flush()
        except UiReadError:
            continue
    assert checked >= 100


@pytest.mark.timeout(120)
def test_the_selection_chip_stays_with_its_widget_on_the_choreboy_canvas() -> None:
    """UX-CHIP-002 on the ChoreBoy canvas (1080 x 600 window) at Fit, 100% and 200%.

    Every widget's chip exists. It touches its widget, or a leader reaches the
    widget, or it is docked on the caption strip right above the widget's x.
    """
    with opened(INVOICE) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host(), 440, 270)
        root_id = session.document.root.id
        nodes = [
            node.id
            for node in session.document.iter_preorder()
            if isinstance(node, WidgetNode) and node.id != root_id and realizer.widget_for(node.id) is not None
        ]
        assert len(nodes) >= 20
        try:
            for zoom in (ZoomFit(), ZoomTo(1.0), ZoomTo(2.0)):
                canvas.send(ZoomAsked(zoom))
                _flush()
                for node_id in nodes:
                    session.selection.set((node_id,), current=node_id, source=SelectionSource.OUTLINE)
                    _flush()
                    _assert_chip_attached(canvas, session.document, node_id, zoom)
        finally:
            canvas.dispose()
            parent.deleteLater()


def _assert_chip_attached(canvas: FormCanvas, document: UiDocument, node_id: NodeId, zoom: object) -> None:
    frame = canvas.overlay()
    where = "%s at %r" % (_name(document, node_id), zoom)
    chips = [item for item in frame.items if isinstance(item, Chip) and item.role in ("select", "layout")]
    assert len(chips) == 1, "no selection chip for " + where
    chip = chips[0]
    outline = next(
        item for item in frame.items if isinstance(item, Stroke) and item.role == "select" and item.width == 2
    )
    target = outline.rect.grown(-1)
    if chip.docked:
        assert frame.dock is not None and _fully_inside(chip.rect, frame.dock), where
        assert chip.rect.x < target.x + target.width and target.x < chip.rect.x + chip.rect.width, where
        return
    if _gap(chip.rect, target) <= CHIP_GAP + 1:
        return
    leader = chip.leader
    assert leader is not None, "detached chip for " + where
    assert leader.start.y == leader.end.y, where
    assert leader.end.x in (target.x, target.x + target.width), where
    assert target.y <= leader.end.y <= target.y + target.height, where


def _gap(a: CanvasRect, b: CanvasRect) -> int:
    dx = max(b.x - (a.x + a.width), a.x - (b.x + b.width), 0)
    dy = max(b.y - (a.y + a.height), a.y - (b.y + b.height), 0)
    return max(dx, dy)


def _forms() -> List[Path]:
    found = []
    for folder in _LOADABLE:
        found.extend(sorted((_CORPUS / folder).rglob("*.ui")))
    return found


def _assert_clear(canvas: FormCanvas, session: FormSession, realizer: Realizer, path: Path) -> None:
    """UX-CHIP-001. Ancestors are not content. The chip's own widget is."""
    root = canvas.page_widget()
    assert root is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    document = session.document
    widgets: List[Tuple[NodeId, CanvasRect]] = []
    for node in document.iter_preorder():
        if not isinstance(node, WidgetNode):
            continue
        widget = realizer.widget_for(node.id)
        if widget is None or not widget.isVisible() or widget.width() <= 0 or widget.height() <= 0:
            continue
        widgets.append((node.id, _mapped(proxy, root, widget)))
    view = canvas.visible_canvas_rect()
    frame = canvas.overlay()
    docked = {item.rect for item in frame.items if isinstance(item, Chip) and item.docked}
    # A "No layout" chip marks its own container's frame and may sit on its empty inside.
    bare = {item.rect for item in frame.items if isinstance(item, Chip) and item.text == no_layout_text()}
    for chip_rect, node_id in frame.chips:
        assert _fully_inside(chip_rect, view), "%s chip on %s leaves the viewport" % (
            path.name,
            _name(document, node_id),
        )
        if chip_rect in docked:
            # The dock is view chrome (the page caption). It covers no content.
            assert frame.dock is not None and _fully_inside(chip_rect, frame.dock)
            continue
        allowed = set(document.ancestors(node_id))
        if chip_rect in bare:
            allowed.add(node_id)
        for other_id, other in widgets:
            if other_id in allowed:
                continue
            assert not chip_rect.intersects(other), "%s chip on %s covers %s" % (
                path.name,
                _name(document, node_id),
                _name(document, other_id),
            )
        for owner_id, band in _title_bands(root, proxy, document):
            if not document.is_ancestor(owner_id, node_id):
                continue
            assert not chip_rect.intersects(band), "%s chip on %s covers a title" % (
                path.name,
                _name(document, node_id),
            )


def _assert_zoom_widths(
    canvas: FormCanvas, session: FormSession, realizer: Realizer, path: Path
) -> None:
    """50/100/200 percent, down to a 700 px wide viewport. Root and one child."""
    child = None
    root_id = session.document.root.id
    for node in session.document.iter_preorder():
        if not isinstance(node, WidgetNode) or node.id == root_id:
            continue
        if realizer.widget_for(node.id) is None:
            continue
        child = node.id
        break
    parent = canvas.parentWidget()
    for width in (960, 700):
        if parent is not None:
            parent.resize(width, 720)
        canvas.resize(width, 720)
        for factor in (0.5, 1.0, 2.0):
            canvas.send(ZoomAsked(ZoomTo(factor)))
            _flush()
            session.selection.set((), source=SelectionSource.CANVAS)
            _flush()
            _assert_clear(canvas, session, realizer, path)
            if child is None:
                continue
            session.selection.set((child,), current=child, source=SelectionSource.CANVAS)
            _flush()
            _assert_clear(canvas, session, realizer, path)


@pytest.mark.timeout(180)
def test_unlaid_containers_keep_a_chip_on_the_choreboy_canvas() -> None:
    """Every in-view container without a layout shows "No layout" at Fit, 100% and 200%."""
    checked = 0
    for path in _forms():
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            with opened(text, str(path)) as (session, realizer):
                root = realizer.root_widget
                if root is None or root.width() <= 0:
                    continue
                canvas, parent = _canvas(session, realizer, _Host(), 440, 270)
                try:
                    pending = _unlaid(session.document, realizer)
                    if not pending:
                        continue
                    for zoom in (ZoomFit(), ZoomTo(1.0), ZoomTo(2.0)):
                        canvas.send(ZoomAsked(zoom))
                        _flush()
                        visible = _unlaid_in_view(canvas, session, realizer)
                        if not visible:
                            continue
                        shown = _bare_nodes(canvas)
                        missing = [node for node in visible if node not in shown]
                        assert not missing, "%s at %r missing a No layout chip" % (path.name, zoom)
                        checked += 1
                finally:
                    canvas.dispose()
                    parent.deleteLater()
                    _flush()
        except UiReadError:
            continue
    assert checked >= 1


def _unlaid(document: UiDocument, realizer: Realizer) -> List[NodeId]:
    found = []
    for node in document.iter_widgets():
        if node.id == document.root.id or node.layout is not None or not node.child_widgets:
            continue
        if managed_container(document, node):
            continue
        if realizer.widget_for(node.id) is None:
            continue
        found.append(node.id)
    return found


def _unlaid_in_view(canvas: FormCanvas, session: FormSession, realizer: Realizer) -> List[NodeId]:
    root = canvas.page_widget()
    assert root is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    view = canvas.visible_canvas_rect()
    found = []
    for node_id in _unlaid(session.document, realizer):
        widget = realizer.widget_for(node_id)
        if widget is None or not widget.isVisible() or widget.width() <= 0 or widget.height() <= 0:
            continue
        if _mapped(proxy, root, widget).intersects(view):
            found.append(node_id)
    return found


def _bare_nodes(canvas: FormCanvas) -> set:
    frame = canvas.overlay()
    text = no_layout_text()
    bare = {item.rect for item in frame.items if isinstance(item, Chip) and item.text == text}
    return {node_id for rect, node_id in frame.chips if rect in bare}


def _title_bands(root: QWidget, proxy: object, document: UiDocument) -> List[Tuple[NodeId, CanvasRect]]:
    bands = []
    for widget in [root] + list(root.findChildren(QWidget)):
        if not widget.isVisible() or widget.width() <= 0 or widget.height() <= 0:
            continue
        node_id = _live_node(widget)
        if node_id is None or not document.contains(node_id):
            continue
        local = _strip(widget)
        if local is None:
            continue
        bands.append((node_id, _mapped_local(proxy, root, widget, local)))
    return bands


def _strip(widget: QWidget) -> QRect | None:
    if isinstance(widget, QGroupBox):
        top = int(widget.contentsRect().top())
        if top <= 0:
            return None
        return QRect(0, 0, widget.width(), top)
    if isinstance(widget, QTabWidget):
        bar = widget.tabBar()
        if bar.height() <= 0:
            return None
        return QRect(bar.geometry())
    if isinstance(widget, QToolBox):
        buttons = [child for child in widget.children() if isinstance(child, QAbstractButton) and child.isVisible()]
        if not buttons:
            return None
        rect = QRect(buttons[0].geometry())
        for button in buttons[1:]:
            rect = rect.united(QRect(button.geometry()))
        return rect
    if isinstance(widget, QDockWidget):
        bar = widget.titleBarWidget()
        if bar is not None and bar.isVisible() and bar.height() > 0:
            return QRect(bar.geometry())
        top = int(widget.contentsRect().top())
        if top <= 0:
            return None
        return QRect(0, 0, widget.width(), top)
    return None


def _live_node(widget: QWidget) -> NodeId | None:
    raw = widget.property(NODE_ID_PROPERTY)
    if isinstance(raw, int):
        return NodeId(raw)
    return None


def _mapped_local(proxy: object, root: QWidget, widget: QWidget, local: QRect) -> CanvasRect:
    top_left = local.topLeft()
    bottom_right = local.bottomRight()
    if widget is not root:
        top_left = widget.mapTo(root, top_left)
        bottom_right = widget.mapTo(root, bottom_right)
    scene_tl = proxy.mapToScene(top_left)  # type: ignore[attr-defined]
    scene_br = proxy.mapToScene(bottom_right)  # type: ignore[attr-defined]
    return CanvasRect(
        int(min(scene_tl.x(), scene_br.x())),
        int(min(scene_tl.y(), scene_br.y())),
        max(1, int(abs(scene_br.x() - scene_tl.x()))),
        max(1, int(abs(scene_br.y() - scene_tl.y()))),
    )


def _fully_inside(inner: CanvasRect, outer: CanvasRect) -> bool:
    return (
        inner.x >= outer.x
        and inner.y >= outer.y
        and inner.x + inner.width <= outer.x + outer.width
        and inner.y + inner.height <= outer.y + outer.height
    )


def test_the_page_name_uses_the_selection_fill_when_the_form_is_selected() -> None:
    tokens = tokens_from_palette(QPalette(), force_mode="light")
    with opened(BUTTON) as (session, realizer):
        canvas, parent = _canvas(session, realizer, _Host())
        canvas.apply_theme(tokens)
        _flush()
        name = canvas.findChild(QLabel, "formBuilder.name")
        assert name is not None
        assert tokens.tree_selected_bg in name.styleSheet()
        assert on_accent_for(tokens.tree_selected_bg) in name.styleSheet()
        ok = _id(session.document, "ok")
        session.selection.set((ok,), current=ok, source=SelectionSource.CANVAS)
        _flush()
        assert name.styleSheet() == ""
        assert tokens.panel_bg in canvas.styleSheet()
        session.selection.set((), source=SelectionSource.CANVAS)
        _flush()
        assert tokens.tree_selected_bg in name.styleSheet()
        canvas.dispose()
        parent.deleteLater()


def _name(document: UiDocument, node_id: NodeId) -> str:
    found = document.get(node_id)
    name = getattr(found, "object_name", None)
    if isinstance(name, str) and name:
        return name
    return str(node_id)


def _mapped(proxy: object, root: QWidget, widget: QWidget) -> CanvasRect:
    top_left = widget.rect().topLeft()
    bottom_right = widget.rect().bottomRight()
    if widget is not root:
        top_left = widget.mapTo(root, top_left)
        bottom_right = widget.mapTo(root, bottom_right)
    scene_tl = proxy.mapToScene(top_left)  # type: ignore[attr-defined]
    scene_br = proxy.mapToScene(bottom_right)  # type: ignore[attr-defined]
    return CanvasRect(
        int(min(scene_tl.x(), scene_br.x())),
        int(min(scene_tl.y(), scene_br.y())),
        max(1, int(abs(scene_br.x() - scene_tl.x()))),
        max(1, int(abs(scene_br.y() - scene_tl.y()))),
    )


def _canvas(
    session: object, realizer: object, host: _Host, width: int = 960, height: int = 720
) -> Tuple[FormCanvas, QWidget]:
    parent = QWidget()
    parent.resize(width, height)
    canvas = FormCanvas(session, realizer, host, parent)  # type: ignore[arg-type]
    canvas.resize(width, height)
    parent.show()
    _flush()
    return canvas, parent


def _click(canvas: FormCanvas, name: str) -> None:
    QTest.mouseClick(canvas.viewport(), _mouse("LeftButton"), _mods("NoModifier"), _center(canvas, name))
    _flush()


def _move(canvas: FormCanvas, name: str) -> None:
    # QTest.mouseMove keeps the buttons from an earlier press in this process.
    # A hover is a move with nothing held.
    local = _center(canvas, name)
    viewport = canvas.viewport()
    kind = getattr(getattr(QEvent, "Type", QEvent), "MouseMove")
    event = QMouseEvent(
        kind,
        local,
        viewport.mapToGlobal(local),
        _mouse("NoButton"),
        _mouse("NoButton"),
        _mods("NoModifier"),
    )
    QApplication.sendEvent(viewport, event)
    _flush()


def _center(canvas: FormCanvas, name: str) -> QPoint:
    return _port(canvas, _widget_point(canvas, name))


def _widget_rect(canvas: FormCanvas, name: str) -> CanvasRect:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return _mapped(proxy, root, widget)


def _widget_point(canvas: FormCanvas, name: str) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    widget = root.findChild(QWidget, name)
    assert widget is not None
    return widget.mapTo(root, widget.rect().center())


def _port(canvas: FormCanvas, point: QPoint) -> QPoint:
    root = canvas.page_widget()
    assert root is not None
    proxy = root.graphicsProxyWidget()
    assert proxy is not None
    return canvas.mapFromScene(proxy.mapToScene(point))


def _id(document: UiDocument, name: str) -> NodeId:
    matches = [node.id for node in document.iter_preorder() if getattr(node, "object_name", None) == name]
    assert len(matches) == 1
    return matches[0]


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    # Show posts a resize after the first frame. Drain until that frame lands.
    for _ in range(4):
        app.processEvents()


def _mouse(name: str) -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), name)


def _mods(name: str) -> Qt.KeyboardModifier:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)
