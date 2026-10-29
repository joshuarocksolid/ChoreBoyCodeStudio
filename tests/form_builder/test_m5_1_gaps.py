# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Seams M5.1 needs in files it does not own. Each is a strict xfail naming the owner."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.commands.catalog_ext.actions import NewAction
from app.features.form_builder.qtside.inspector.model import inspected_ids
from tests.form_builder.qtside.support import open_session

pytestmark = pytest.mark.unit


def test_the_inspector_accepts_an_action_as_an_owner() -> None:
    session = open_session(build_template_ui("main_window", "shop_window"))
    action = session.log.execute(NewAction("Open")).result
    assert inspected_ids(session.document, (action,)) == (action,)


def test_insert_search_offers_main_window_parts() -> None:
    from app.features.form_builder.qtside.insert.catalog import load_catalog
    from app.features.form_builder.qtside.insert.catalog.search import search

    catalog = load_catalog()
    for word, friendly in (("toolbar", "Toolbar"), ("menu bar", "Menu bar"), ("status bar", "Status bar")):
        hits = search(catalog.entries, catalog.windows, word)
        assert any("%s · add to this window" % friendly in getattr(hit.entry, "friendly", "") for hit in hits), word


def test_a_part_row_adds_to_this_window_and_a_plain_form_says_why() -> None:
    from app.features.form_builder.engine.commands.catalog_ext.main_window import AddMainWindowPart
    from app.features.form_builder.engine.commands.base import CommandRejected
    from app.features.form_builder.engine.query import actions as q

    window = open_session(build_template_ui("main_window", "shop_window"))
    window.log.execute(AddMainWindowPart("toolbar"))
    assert len(q.parts(window.document)["toolbar"]) == 1  # on this window, not a new form
    plain = open_session(build_template_ui("widget", "plain"))
    with pytest.raises(CommandRejected):
        plain.log.execute(AddMainWindowPart("toolbar"))
