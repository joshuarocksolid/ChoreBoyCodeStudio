# pyright: reportAttributeAccessIssue=false
"""M5.R review repros: Settings reaches an inspector that is already open."""

from __future__ import annotations

import pytest

from app.features.form_builder.integration.memory import WorkbenchMemoryStore, reread_qt_names
from app.qt.QtWidgets import QApplication, QLabel, QWidget
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane, _select

pytestmark = [pytest.mark.unit]


def test_show_qt_names_from_settings_reaches_an_open_inspector(tmp_path, qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        store = WorkbenchMemoryStore(str(tmp_path))
        pane.bind_settings(store)
        _select(session, "email")
        pane.flush()
        # Settings > Form designer > "Show Qt names in the inspector" saved by another store (the dialog).
        WorkbenchMemoryStore(str(tmp_path)).set_qt_names(True)
        reread_qt_names()
        qapp.processEvents()
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        qt_name = row.findChild(QLabel, "formBuilder.rowQtName")
        assert qt_name is not None and qt_name.isVisible()
    finally:
        _close(window, pane, realizer, session, qapp)
