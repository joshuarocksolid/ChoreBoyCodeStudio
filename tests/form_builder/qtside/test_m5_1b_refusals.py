# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""A widget cannot go on a toolbar, menu or status bar (UX-MAIN-016, pain 17)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog_ext.main_window import AddMainWindowPart
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.query.drop_target import (
    CENTRAL_NOTE,
    PART_REFUSALS,
    DropPayload,
    RefusedDrop,
    central_redirect,
    hosts_from,
    resolve_drop,
)
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.commands.drop_plan import auto_target
from tests.form_builder.qtside.support import open_session

pytestmark = pytest.mark.unit


def _window():  # type: ignore[no-untyped-def]
    session = open_session(build_template_ui("main_window", "shop_window"))
    session.log.execute(AddMainWindowPart("toolbar"))
    return session


@pytest.mark.pain("P-17")
def test_a_widget_dragged_over_a_toolbar_a_menu_bar_or_a_status_bar_is_refused_with_the_spec_sentence() -> None:
    session = _window()
    doc = session.document
    parts = q.parts(doc)
    rects = {doc.root.id: Rect(0, 0, 600, 400)}
    boxes = {"menubar": Rect(0, 0, 600, 24), "toolbar": Rect(0, 24, 600, 32), "statusbar": Rect(0, 376, 600, 24), "central": Rect(0, 56, 600, 320)}
    for key, rect in boxes.items():
        rects[parts[key][0].id] = rect
    root = hosts_from(doc, rects)
    expected = {"menubar": "menu", "toolbar": "toolbar", "statusbar": "status"}
    for key, kind in expected.items():
        rect = boxes[key]
        result = resolve_drop(root, (rect.x + 20, rect.y + rect.height // 2), DropPayload("widget"))
        assert isinstance(result, RefusedDrop), key
        assert result.sentence == PART_REFUSALS[kind]
        assert result.indicator.role == "problem"


def test_a_keyboard_insert_with_a_toolbar_selected_goes_to_the_central_area_and_says_so() -> None:
    session = _window()
    doc = session.document
    toolbar = q.parts(doc)["toolbar"][0].id
    central = q.parts(doc)["central"][0].id
    assert central_redirect(doc, toolbar) == central
    assert central_redirect(doc, central) is None
    target = auto_target(doc, toolbar, DropPayload("widget"))
    assert target is not None and not isinstance(target, RefusedDrop)
    assert target.host == central or doc.contains(target.host)
    assert CENTRAL_NOTE == "Inserted in the central area."
