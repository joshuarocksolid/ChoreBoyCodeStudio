"""Unit tests for connection editor panel."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.connections.connection_editor_panel import ConnectionEditorPanel
from app.designer.model import ConnectionModel

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_connection_panel_binds_connections_and_emits_actions() -> None:
    panel = ConnectionEditorPanel()
    panel.bind_connections(
        [
            ConnectionModel(
                sender="pushButton",
                signal="clicked()",
                receiver="Form",
                slot="accept()",
            )
        ]
    )
    assert panel._table.rowCount() == 1  # type: ignore[attr-defined]
    assert "1 connection" in panel._summary_label.text()  # type: ignore[attr-defined]

    seen_add: list[bool] = []
    seen_remove: list[int] = []
    panel.add_requested.connect(lambda: seen_add.append(True))
    panel.remove_requested.connect(seen_remove.append)

    panel._add_button.click()  # type: ignore[attr-defined]
    panel._table.setCurrentCell(0, 0)  # type: ignore[attr-defined]
    panel._remove_button.click()  # type: ignore[attr-defined]

    assert seen_add == [True]
    assert seen_remove == [0]
