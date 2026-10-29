# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Form > Main window and the context menu rows (UX-MAIN-002, 017, 019)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.integration.form_menu_ext import default_registry
from app.features.form_builder.integration.menu_ext import MenuContext, default_registry as menu_registry
from app.features.form_builder.engine.commands.catalog_ext.actions import NewAction
from app.features.form_builder.engine.query import actions as q
from app.qt.QtWidgets import QMenu, QWidget
from tests.form_builder.qtside.test_m5_1_actions_pane import _MAIN
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]


@pytest.mark.parity("R3-135", "R3-138", "R3-144")
def test_main_window_items_are_offered_only_where_they_apply(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host = QWidget()
    surface = _open(host, _MAIN, tmp_path / "shop.ui")
    try:
        items = {item.command_id: item for _m, item in default_registry().items()}
        assert all(items[i].offered(surface) for i in items if i.startswith("form.mainWindow."))
        items["form.mainWindow.addMenuBar"].run(surface)
        items["form.mainWindow.addStatusBar"].run(surface)
        assert not items["form.mainWindow.addMenuBar"].offered(surface)
        assert not items["form.mainWindow.addStatusBar"].offered(surface)
        items["form.mainWindow.addToolbar"].run(surface)
        items["form.mainWindow.addToolbar"].run(surface)
        assert [w.object_name for w in q.parts(surface.session.document)["toolbar"]] == ["toolBar", "toolBar_2"]
    finally:
        host.deleteLater()


def test_the_page_menu_adds_parts_and_a_widget_menu_lists_actions(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    host = QWidget()
    surface = _open(host, _MAIN, tmp_path / "shop.ui")
    try:
        session = surface.session
        ran = []
        menu = QMenu()
        ctx = MenuContext(menu, (session.document.root.id,), session.document.root.id, session, lambda s: None, run=ran.append)
        menu_registry().run("structure", ctx)
        titles = [action.text() for action in menu.actions()]
        assert "Main window" in titles
        session.log.execute(NewAction("Print"))
        central = session.document.by_name("centralwidget")[0]
        second = QMenu()
        menu_registry().run("structure", MenuContext(second, (central,), central, session, lambda s: None, run=ran.append))
        subs = [child for child in second.findChildren(QMenu) if child.title() == "Actions"]
        assert [a.text() for a in subs[0].actions()] == ["Print"]
        subs[0].actions()[0].trigger()
        assert type(ran[-1]).__name__ == "SetWidgetAction" and ran[-1].on
    finally:
        host.deleteLater()
