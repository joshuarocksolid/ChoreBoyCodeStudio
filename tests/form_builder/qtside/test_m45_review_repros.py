# pyright: reportAttributeAccessIssue=false
"""M4.5 review repros: bugs the M4 review found in the shop-owner walkthrough."""

from __future__ import annotations

import pytest

from app.features.form_builder.integration.insert_memory import InMemoryInsertMemory
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.test_m4_insert_pane import _pane

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


@pytest.mark.parametrize(("typed", "first"), [(("field",), "QLineEdit"), (("text", "number"), "QSpinBox")])
def test_enter_in_insert_search_takes_the_first_result_of_the_new_query(typed: tuple, first: str) -> None:
    """Typing kept the entry that matched an earlier prefix current, so Enter
    inserted the second result ("field" gave an input field, "number" an LCD)."""
    parent = QWidget()
    pane = _pane(parent, InMemoryInsertMemory())
    parent.show()
    for word in typed:
        pane.filter.setFocus()
        pane.filter.selectAll()
        QTest.keyClicks(pane.filter, word)
        QApplication.processEvents()
    assert pane.body.item(0).data(int(Qt.ItemDataRole.UserRole)) == first
    current = pane.current_row()
    assert current is not None and current.key == first
