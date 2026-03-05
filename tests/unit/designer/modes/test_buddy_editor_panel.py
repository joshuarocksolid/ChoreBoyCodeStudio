"""Unit tests for buddy editor panel."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QComboBox

from app.designer.modes import BuddyEditorPanel

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_buddy_panel_emits_assignment_changes() -> None:
    panel = BuddyEditorPanel()
    panel.bind_buddy_rows([("nameLabel", "")], ["lineEdit", "okButton"])

    seen: list[tuple[str, str]] = []
    panel.buddy_assignment_changed.connect(lambda source, target: seen.append((source, target)))

    combo = panel.findChild(QComboBox)
    assert combo is not None
    combo.setCurrentIndex(combo.findData("lineEdit"))

    assert seen[-1] == ("nameLabel", "lineEdit")
