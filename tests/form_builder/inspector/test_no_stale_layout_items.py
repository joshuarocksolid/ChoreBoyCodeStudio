# pyright: reportAttributeAccessIssue=false
"""Inspector repaints must not pile up QLayoutItem wrappers.

PySide keeps every ``QLayout.itemAt`` wrapper alive with its layout. Qt deletes
the item when its widget goes, but the wrapper stays registered, and a later
object at the same address comes back as a ``QWidgetItem`` (seen as
"'QWidgetItem' object has no attribute 'fontMetrics' / 'type'" in full runs).
"""

from __future__ import annotations

import gc

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.qt.QtWidgets import QApplication, QLayout, QLayoutItem
from tests.form_builder.perf.reference import reference_form
from tests.form_builder.qtside.support import opened

pytestmark = pytest.mark.usefixtures("qapp")


def _held_items() -> int:
    gc.collect()
    return sum(1 for obj in gc.get_objects() if isinstance(obj, QLayoutItem) and not isinstance(obj, QLayout))


def test_repainting_the_inspector_holds_no_new_layout_items() -> None:
    app = QApplication.instance()
    assert app is not None
    with opened(reference_form(25).xml) as (session, realizer):
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None)
        pane.resize(236, 700)
        pane.show()
        try:
            for group in GroupId:
                pane.set_group_expanded(group, True)
            classes = {}
            for node in session.document.iter_widgets():
                classes.setdefault(node.class_name, node.id)
            ids = list(classes.values())
            assert len(ids) >= 5

            def tour() -> None:
                for node_id in ids:
                    session.selection.set((node_id,), source=SelectionSource.PROGRAM)
                    pane.flush()
                    app.processEvents()

            tour()
            before = _held_items()
            tour()
            tour()
            # Before the fix every repaint wrapped every inspector layout item
            # (thousands per tour), and a later object came back as a stale
            # QWidgetItem inside tour(). A few wrappers per class remain from
            # code outside the tab chain; see the M3.7 ticket.
            assert _held_items() - before <= 2 * len(ids)
        finally:
            pane.dispose()
            pane.deleteLater()
            app.processEvents()
