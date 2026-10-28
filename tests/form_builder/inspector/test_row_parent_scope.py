# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""RowSpec.parent_classes: a row shows only when the selected widget's parent widget admits it."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector.api import GroupId, Prop, RowSpec
from app.features.form_builder.qtside.inspector.catalog import Registrations
from app.features.form_builder.qtside.inspector.model import LiveClass, LiveProperty, NodeBody, project
from tests.form_builder.qtside.support import form, open_session

pytestmark = pytest.mark.unit

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="lay">
   <item><widget class="QTabWidget" name="tabs">
     <widget class="QWidget" name="page"/>
   </widget></item>
   <item><widget class="QWidget" name="plain"><widget class="QLabel" name="inside"/></widget></item>
  </layout>
""",
)

_SPEC = RowSpec(
    key="test.pageAttr",
    group=GroupId.CONTENT,
    label="Page label",
    help="",
    source=Prop("toolTip"),
    parent_classes=("QTabWidget",),
)


def _live(session) -> dict:  # type: ignore[no-untyped-def]
    """Live class data for each widget, so the Prop row binds (as the realized form supplies it)."""
    found = {}
    for name in ("tabs", "page", "plain", "inside"):
        node = session.document.by_name(name)[0]
        cls = session.document.node(node).class_name
        chain = (cls, "QWidget", "QObject") if cls != "QWidget" else ("QWidget", "QObject")
        found[node] = LiveClass(chain, (LiveProperty("toolTip", "QWidget", "string"),), (), ())
    return found


def _rows_for(name: str) -> tuple:
    found = Registrations()
    found.scope("tests.parent").row(_SPEC)
    session = open_session(_FORM, "/tmp/cbcs-parent-scope.ui")
    try:
        session.selection.set((session.document.by_name(name)[0],), source=SelectionSource.CANVAS)
        body = project(session, found.freeze(), live=_live(session)).body
        assert isinstance(body, NodeBody)
        return tuple(row.key for view in body.groups for row in view.rows())
    finally:
        session.dispose()


def test_a_page_of_a_tab_widget_shows_the_parent_scoped_row() -> None:
    assert "test.pageAttr" in _rows_for("page")


def test_a_widget_whose_parent_is_not_a_tab_widget_hides_it() -> None:
    assert "test.pageAttr" not in _rows_for("plain")


def test_the_nearest_parent_widget_counts_not_a_layout() -> None:
    # "inside" sits in "plain" (a QWidget) inside the layout; its parent widget is not a tab widget.
    assert "test.pageAttr" not in _rows_for("inside")
