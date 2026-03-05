"""Unit tests for icon picker field widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.properties.icon_picker import IconPickerField

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_icon_picker_set_path_updates_value_and_signal() -> None:
    picker = IconPickerField()
    seen: list[str] = []
    picker.path_changed.connect(seen.append)

    picker.set_path("icons/run.png")
    picker._emit_path()  # type: ignore[attr-defined]

    assert picker.path() == "icons/run.png"
    assert seen == ["icons/run.png"]
