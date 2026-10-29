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


@pytest.mark.xfail(strict=True, reason="UX-MAIN-002: Insert search rows run AddMainWindowPart. Owner: qtside/insert/pane.py and integration/workbench.py (M5.0s/M5.6), which route window rows to New form.")
def test_insert_search_offers_main_window_parts() -> None:
    from app.features.form_builder.qtside.insert.catalog import load_catalog
    from app.features.form_builder.qtside.insert.catalog.search import search

    catalog = load_catalog()
    hits = search(catalog.entries, catalog.windows, "toolbar")
    assert any("Toolbar · add to this window" in getattr(hit.entry, "friendly", "") for hit in hits)
