# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""The Pages group slot (UX-CONT-019): a group with no curated rows shows only when its body applies."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector.api import GROUP_ORDER, GroupId
from app.features.form_builder.qtside.inspector.catalog import Registrations
from app.features.form_builder.qtside.inspector.editors import default_catalog
from app.features.form_builder.qtside.inspector.model import NodeBody, project
from tests.form_builder.qtside.support import form, open_session

pytestmark = pytest.mark.unit

_TABS = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="lay">
   <item><widget class="QTabWidget" name="tabs"/></item>
  </layout>
""",
)


class _Body:
    def __init__(self) -> None:
        self._widget = object()

    @property
    def widget(self):  # type: ignore[no-untyped-def]
        return self._widget

    def show(self, rows) -> None:  # type: ignore[no-untyped-def]
        del rows


def _body(*_args: object) -> _Body:
    return _Body()


def _groups_of(catalog, search: str = "") -> tuple:  # type: ignore[no-untyped-def]
    session = open_session(_TABS, "/tmp/cbcs-pages-slot.ui")
    try:
        session.selection.set((session.document.by_name("tabs")[0],), source=SelectionSource.CANVAS)
        body = project(session, catalog, search=search).body
        assert isinstance(body, NodeBody)
        return tuple(view.group for view in body.groups)
    finally:
        session.dispose()


def test_pages_follows_content_in_the_group_order() -> None:
    assert GROUP_ORDER.index(GroupId.PAGES) == GROUP_ORDER.index(GroupId.CONTENT) + 1
    assert GroupId.PAGES.title == "Pages"


def test_pages_group_shows_for_a_page_container() -> None:
    """M4.4 fills the Pages slot. A tab widget shows the group."""
    assert GroupId.PAGES in _groups_of(default_catalog())


def test_pages_group_shows_when_its_body_applies() -> None:
    found = Registrations()
    found.scope("tests.pages").group_body(GroupId.PAGES, _body, applies=lambda document, owners: bool(owners))
    shown = _groups_of(found.freeze())
    assert GroupId.PAGES in shown
    assert shown == tuple(group for group in GROUP_ORDER if group in shown)


def test_pages_group_stays_hidden_when_its_body_does_not_apply() -> None:
    found = Registrations()
    found.scope("tests.pages").group_body(GroupId.PAGES, _body, applies=lambda document, owners: False)
    assert GroupId.PAGES not in _groups_of(found.freeze())


def test_pages_group_is_hidden_while_searching() -> None:
    found = Registrations()
    found.scope("tests.pages").group_body(GroupId.PAGES, _body, applies=lambda document, owners: True)
    assert GroupId.PAGES not in _groups_of(found.freeze(), search="zzz-no-such-row")


def test_an_override_body_does_not_keep_the_baseline_applies() -> None:
    found = Registrations()
    found.scope("tests.base").group_body(GroupId.PAGES, _body, baseline=True, applies=lambda document, owners: True)
    found.scope("tests.over").group_body(GroupId.PAGES, _body)
    assert GroupId.PAGES not in _groups_of(found.freeze())


def test_a_second_pages_applies_registration_is_a_conflict() -> None:
    from app.features.form_builder.qtside.inspector.catalog import RegistryConflict

    found = Registrations()
    found.scope("tests.a").group_body(GroupId.PAGES, _body, baseline=True, applies=lambda d, o: True)
    with pytest.raises(RegistryConflict):
        found.scope("tests.b").group_body(GroupId.PAGES, _body, baseline=True, applies=lambda d, o: True)
