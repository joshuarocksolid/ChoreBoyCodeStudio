"""Unit tests for component library panel interactions."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.components import ComponentLibraryPanel

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_component_library_panel_binds_and_emits_insert() -> None:
    panel = ComponentLibraryPanel()
    panel.bind_components(["ButtonPart", "HeaderPart"])
    seen: list[str] = []
    panel.insert_requested.connect(seen.append)

    panel._list.setCurrentRow(1)  # type: ignore[attr-defined]
    panel._insert_button.click()  # type: ignore[attr-defined]

    assert seen == ["HeaderPart"]
