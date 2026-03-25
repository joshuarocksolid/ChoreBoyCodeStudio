"""Unit tests for tab-order editor panel."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.modes import TabOrderEditorPanel

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_tab_order_panel_reorders_and_emits() -> None:
    panel = TabOrderEditorPanel()
    panel.bind_tab_order(["lineEdit", "okButton", "cancelButton"])
    seen: list[list[str]] = []
    panel.tab_order_changed.connect(seen.append)

    panel._list.setCurrentRow(1)  # type: ignore[attr-defined]
    panel._move_up_button.click()  # type: ignore[attr-defined]

    assert seen[-1] == ["okButton", "lineEdit", "cancelButton"]
