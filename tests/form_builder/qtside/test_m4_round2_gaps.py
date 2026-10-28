# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Round-2 gaps: Pages menu, dock-band chips, and the rows M4.0s cannot select."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.features.form_builder.engine.commands.catalog_ext.pages import InsertPage
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.layout_actions import OfferSheet
from app.features.form_builder.engine.query.outline import InPageSlot
from app.features.form_builder.engine.query.pages import pages
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.context_menu import build_context_menu
from app.features.form_builder.integration.menu_ext import default_registry
from app.features.form_builder.integration.workbench import _row_caption
from app.features.form_builder.qtside.canvas.core.frame import Chip, Fill
from app.features.form_builder.qtside.canvas.core.gesture import PlaceAsked
from app.features.form_builder.qtside.canvas.core.place import payload_for
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint
from app.features.form_builder.qtside.inspector.api import EditorKey
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.editors.dock_side import DOCK_SIDE, DockSideEditor
from app.features.form_builder.qtside.inspector.api import Written
from app.features.form_builder.qtside.inspector.model import NodeBody, project
from app.features.form_builder.engine.ui4.values import NumberValue
from app.qt.QtWidgets import QMenu, QToolButton, QWidget
from app.qt.qt_compat import delete_now
from tests.form_builder.qtside.support import form, open_session, opened
from tests.form_builder.qtside.test_m4_mdi import MDI, _canvas as _mdi_canvas
from tests.form_builder.qtside.test_m4_pages_canvas import TABS
from tests.form_builder.qtside.test_m4_scroll_area import _flush
from tests.form_builder.qtside.test_m4_wizard_canvas import WIZARD

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]


def _page_rows(session, node):  # type: ignore[no-untyped-def]
    """Labels and state, read before the menu wrapper can be released."""
    holder = QWidget()
    menu = QMenu(holder)
    ran: list = []

    def run(command: object) -> None:
        ran.append(command)
        session.log.execute(command)  # type: ignore[attr-defined]

    build_context_menu(
        menu,
        contributors=default_registry(),
        ids=(node,),
        current=node,
        session=session,
        dispatch=lambda _command_id: None,
        enabled=lambda _command_id: True,
        sheet=OfferSheet({}, None, ()),
        run=run,
    )
    pages_menu = next(child for child in menu.findChildren(QMenu) if child.title() == "Pages")
    rows = tuple(
        (action.text(), action.isEnabled(), action.toolTip(), action.isCheckable(), action.isChecked())
        for action in pages_menu.actions()
    )
    triggers = {action.text(): action.trigger for action in pages_menu.actions()}
    return holder, rows, triggers, ran


def test_pages_menu_inserts_a_tab_after_the_shown_page() -> None:
    with opened(TABS) as (session, _realizer):
        tabs = session.document.by_name("tabs")[0]
        _hold, rows, triggers, ran = _page_rows(session, tabs)
        labels = [row[0] for row in rows]
        assert any(label.startswith("Insert tab after \u201c") for label in labels)
        assert any(label.startswith("Insert tab before \u201c") for label in labels)
        move = next(row for row in rows if row[0] == "Move tab left")
        assert not move[1]
        assert move[2] == "This is already the first page."
        start = next(row for row in rows if row[0] == "Start on this page")
        assert start[3] and start[4]
        label = next(label for label in labels if label.startswith("Insert tab after"))
        triggers[label]()
        delete_now(_hold)
        assert ran and isinstance(ran[0], InsertPage) and ran[0].index == 1
        assert len(pages(session.document, tabs)) == 3


def test_a_wizard_menu_has_no_start_page_and_an_mdi_menu_adds_a_window() -> None:
    with opened(WIZARD) as (session, _realizer):
        wizard = session.document.by_name("wizard")[0]
        _hold, rows, _triggers, _ran = _page_rows(session, wizard)
        labels = [row[0] for row in rows]
        assert any(label.startswith("Insert step after") for label in labels)
        assert "Start on this page" not in labels
        delete_now(_hold)
    with opened(MDI) as (session, _realizer):
        area = session.document.by_name("mdi")[0]
        _hold, rows, triggers, ran = _page_rows(session, area)
        labels = [row[0] for row in rows]
        assert "Add window" in labels
        assert "Tile windows" in labels
        assert "Start on this page" not in labels
        triggers["Add window"]()
        delete_now(_hold)
        assert isinstance(ran[0], InsertPage)
        assert len(pages(session.document, area)) == 3


def test_dragging_a_dock_paints_the_four_bands_and_their_chips() -> None:
    text = form(
        'class="QMainWindow" name="Main"',
        """
  <widget class="QWidget" name="centralwidget"/>
  <widget class="QDockWidget" name="dock">
   <attribute name="dockWidgetArea"><number>1</number></attribute>
   <widget class="QWidget" name="dockContents"/>
  </widget>
""",
    )
    with _mdi_canvas(text) as (session, canvas, _host):
        _flush()
        controller = canvas._controller
        controller._index.ensure_fresh()
        main = session.document.by_name("Main")[0]
        dock = session.document.by_name("dock")[0]
        rect = controller._index.rect_of(main)
        assert rect is not None and rect.width > 40
        view = controller._stage.view_map()
        point = CanvasPoint(
            int(view.page_origin.x + (rect.x + 4) * view.factor),
            int(view.page_origin.y + (rect.y + rect.height // 2) * view.factor),
        )
        canvas.send(PlaceAsked(point, payload_for(session.document, (dock,))))
        _flush()
        items = canvas.overlay().items
        assert sum(1 for item in items if isinstance(item, Fill) and item.role == "dock_band") == 4
        texts = [item.text for item in items if isinstance(item, Chip)]
        assert {"Left side", "Right side", "Top", "Bottom"} <= set(texts)


def test_dock_side_editor_writes_the_qt_area_number() -> None:
    parent = QWidget()
    written: list = []

    class _Host:
        def commit(self, value: object, session: object = None) -> None:
            del session
            written.append(value)

    editor = DockSideEditor(None, _Host(), parent)  # type: ignore[arg-type]
    editor.show(Written(NumberValue(1)))
    right = next(button for button in editor.widget.findChildren(QToolButton) if button.text() == "Right")
    right.click()
    assert written == [NumberValue(2)]
    parent.deleteLater()


def test_container_rows_are_scoped_to_their_parent_class() -> None:
    rows = {row.key: row for row in default_catalog().rows()}
    assert rows["dockSide"].label == "Dock side"
    assert rows["dockSide"].parent_classes == ("QMainWindow",)
    assert rows["allowedAreas"].label == "Allowed sides"
    assert rows["startsOn"].classes == ("QTabWidget", "QToolBox", "QStackedWidget")
    assert rows["tabTitle"].parent_classes == ("QTabWidget",)
    assert rows["pageLabel"].parent_classes == ("QToolBox",)
    assert default_catalog().editor(DOCK_SIDE) is DockSideEditor


@pytest.mark.xfail(
    strict=True,
    reason="M4.0s owns inspector editor_key: a row cannot name EditorKey('dock_side'), so Dock side opens as a number",
)
def test_the_dock_side_row_selects_the_four_segment_editor() -> None:
    text = form(
        'class="QMainWindow" name="Main"',
        """
  <widget class="QWidget" name="centralwidget"/>
  <widget class="QDockWidget" name="dock">
   <attribute name="dockWidgetArea"><number>1</number></attribute>
   <widget class="QWidget" name="dockContents"/>
  </widget>
""",
    )
    session = open_session(text, "/tmp/cbcs-dock-side.ui")
    try:
        dock = session.document.by_name("dock")[0]
        session.selection.set((dock,), source=SelectionSource.CANVAS)
        body = project(session, default_catalog()).body
        assert isinstance(body, NodeBody)
        row = next(row for view in body.groups for row in view.rows() if row.key == "dockSide")
        assert row.editor == EditorKey("dock_side")
    finally:
        session.dispose()


@pytest.mark.xfail(
    strict=True,
    reason="M4.1 owns workbench._row_caption, which always says Page and cannot say Tab, Step or Window",
)
def test_an_outline_page_caption_uses_the_container_word() -> None:
    row = SimpleNamespace(
        kind="page",
        slot=InPageSlot(NodeId(1), 1),
        visible_text="Settings",
        friendly="",
        primary="",
    )
    assert _row_caption(row).startswith("Tab ")
