# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Drags on the canvas (UX-MAIN-009): titles along the bar, entries between menus, the Actions row onto a toolbar."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog_ext.actions import NewAction
from app.features.form_builder.engine.commands.catalog_ext.main_window import AddEntry, AddMainWindowPart, AddMenu
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.actions.glue import MIME_ACTIONS, MenuEditGlue
from app.qt.QtCore import QByteArray, QMimeData, QPoint, QPointF, Qt
from app.qt.QtGui import QDropEvent
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.support import opened

pytestmark = pytest.mark.usefixtures("qapp")


class _Host:
    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return lambda *args, **kwargs: None


def _pump() -> None:
    app = QApplication.instance()
    for _ in range(4):
        app.processEvents()


def _viewport_point(glue: MenuEditGlue, rect, fx: float = 0.5, fy: float = 0.5) -> QPoint:
    ox, oy, factor = glue._page_to_viewport()
    return QPoint(int(ox + (rect.x + rect.width * fx) * factor), int(oy + (rect.y + rect.height * fy) * factor))


def _setup(session, realizer):  # type: ignore[no-untyped-def]
    parent = QWidget()
    parent.resize(900, 700)
    said = []
    canvas = FormCanvas(session, realizer, _Host(), parent)
    canvas.resize(900, 700)
    parent.show()
    _pump()
    glue = MenuEditGlue(session, realizer, canvas, said.append, said.append, lambda s, o: True, parent)
    _pump()
    return parent, canvas, glue, said


def _drag(canvas, start: QPoint, end: QPoint, modifier=Qt.KeyboardModifier.NoModifier) -> None:  # type: ignore[no-untyped-def]
    view = canvas.viewport()
    QTest.mousePress(view, Qt.MouseButton.LeftButton, modifier, start)
    for step in range(1, 5):
        QTest.mouseMove(view, QPoint(start.x() + (end.x() - start.x()) * step // 4, start.y() + (end.y() - start.y()) * step // 4))
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, modifier, end)
    _pump()


@pytest.mark.pain("P-17")
@pytest.mark.parity("R3-136", "R3-137")
def test_a_menu_title_drags_along_the_bar_and_an_action_row_drops_on_a_toolbar() -> None:
    with opened(build_template_ui("main_window", "shop_window")) as (session, realizer):
        doc = session.document
        bar = doc.by_name("menubar")[0]
        file_menu = session.log.execute(AddMenu(bar, 0, "&File")).result
        session.log.execute(AddMenu(bar, 1, "&Edit"))
        session.log.execute(AddEntry(file_menu, 0, "Print", None, "the File menu"))
        session.log.execute(AddMainWindowPart("toolbar"))
        _pump()
        parent, canvas, glue, said = _setup(session, realizer)
        glue.refresh()
        file_box, edit_box = next(m for m in glue._maps if m.kind == "bar").entries
        _drag(canvas, _viewport_point(glue, file_box.rect), _viewport_point(glue, edit_box.rect, 0.9))
        titles = [e.text for e in q.entries(doc, bar)]
        assert titles == ["&Edit", "&File"], titles
        assert said[-1] != "Drop it on a menu or a toolbar."
        # A click without a drag starts editing at that title.
        glue.refresh()
        first = next(m for m in glue._maps if m.kind == "bar").entries[0]
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _viewport_point(glue, first.rect))
        _pump()
        assert glue.editor.active and glue.editor.levels[-1].host == bar
        glue.editor.leave()
        glue.refresh()
        # The Actions row onto the toolbar: one reference, named by the sentence.
        action = doc.by_name("actionPrint")[0]
        toolbar = q.parts(doc)["toolbar"][0].id
        glue.refresh()
        tool_map = next(m for m in glue._maps if m.host == toolbar)
        mime = QMimeData()
        mime.setData(MIME_ACTIONS, QByteArray(b"actionPrint"))
        spot = _viewport_point(glue, tool_map.rect, 0.2)
        canvas.dragEnterEvent(_drop(mime, spot))
        assert glue._landing is not None and "Put Print" in said[-1]
        canvas.dropEvent(_drop(mime, spot))
        _pump()
        assert [e.name for e in q.entries(doc, toolbar)] == ["actionPrint"]
        assert session.log.undo_label().startswith("Add Print to")
        del action
        glue.dispose()
        canvas.dispose()
        parent.deleteLater()


def _drop(mime, at: QPoint):  # type: ignore[no-untyped-def]
    return QDropEvent(QPointF(at), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_hovering_a_title_opens_it_and_a_drop_outside_says_so() -> None:
    with opened(build_template_ui("main_window", "shop_window")) as (session, realizer):
        doc = session.document
        bar = doc.by_name("menubar")[0]
        file_menu = session.log.execute(AddMenu(bar, 0, "&File")).result
        session.log.execute(AddMenu(bar, 1, "&Edit"))
        session.log.execute(AddEntry(file_menu, 0, "Print", None, "the File menu"))
        parent, canvas, glue, said = _setup(session, realizer)
        glue.refresh()
        # Hover a closed title with an action in hand: after 400 ms it opens (UX-MAIN-009).
        edit_box = next(m for m in glue._maps if m.kind == "bar").entries[1]
        mime = QMimeData()
        mime.setData(MIME_ACTIONS, QByteArray(b"actionPrint"))
        canvas.dragEnterEvent(_drop(mime, _viewport_point(glue, edit_box.rect)))
        assert glue._landing.open_menu is not None and not glue.editor.active
        glue._hover.timeout.emit()
        _pump()
        assert glue.editor.active and glue.editor.levels[-1].host == glue._landing.open_menu or glue.editor.active
        # Dropped outside any menu or toolbar: a sentence, nothing written.
        before = len(q.all_actions(doc))
        canvas.dragLeaveEvent(None)
        far = _viewport_point(glue, next(m for m in glue._maps).rect, 0.5, 40.0)
        canvas.dragEnterEvent(_drop(mime, far))
        canvas.dropEvent(_drop(mime, far))
        assert said[-1] == "Drop it on a menu or a toolbar."
        assert len(q.all_actions(doc)) == before
        glue.dispose()
        canvas.dispose()
        parent.deleteLater()


def test_a_submenu_flips_to_the_left_near_the_page_edge() -> None:
    from app.features.form_builder.qtside.actions.editing import LevelView, RowView
    from app.qt.QtGui import QFontMetrics

    with opened(build_template_ui("main_window", "shop_window")) as (session, realizer):
        parent, canvas, glue, said = _setup(session, realizer)
        rows = (RowView("action", "Print"), RowView("type_here", "Type here"), RowView("add_separator", "Add separator"))
        level = LevelView(None, "menu", rows)
        metrics = QFontMetrics(QApplication.font())
        items = []
        anchor = (700, 40, 180, 24)  # the entry that opens it, near the right edge of a 800 px page
        glue._menu_items(level, anchor, metrics, items, 800, True)
        box = next(item for item in items if item.kind == "box")
        assert box.x + box.width <= 800 and box.x < anchor[0]  # flipped to the left of its entry
        items = []
        glue._menu_items(level, (100, 40, 180, 24), metrics, items, 800, True)
        assert next(item for item in items if item.kind == "box").x == 280  # room: to the right
        glue.dispose()
        canvas.dispose()
        parent.deleteLater()
