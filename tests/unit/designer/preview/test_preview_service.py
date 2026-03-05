"""Unit tests for designer preview service contracts."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)
pytest.importorskip("PySide2.QtUiTools", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.designer.preview import load_widget_from_ui_xml, probe_ui_xml_compatibility

pytestmark = pytest.mark.unit

_VALID_UI = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    "<ui version=\"4.0\"><class>PreviewForm</class>"
    "<widget class=\"QWidget\" name=\"PreviewForm\"/>"
    "<resources/><connections/></ui>\n"
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_probe_ui_xml_compatibility_passes_for_valid_ui() -> None:
    result = probe_ui_xml_compatibility(_VALID_UI)
    assert result.is_compatible is True


def test_probe_ui_xml_compatibility_fails_for_invalid_ui() -> None:
    result = probe_ui_xml_compatibility("<ui><broken></ui>")
    assert result.is_compatible is False


def test_load_widget_from_ui_xml_returns_qwidget_instance() -> None:
    widget = load_widget_from_ui_xml(_VALID_UI)
    assert widget.objectName() == "PreviewForm"
    widget.deleteLater()
