"""Unit tests for connection editor panel."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication, QComboBox

from app.designer.connections.connection_editor_panel import ConnectionEditorPanel
from app.designer.connections.signal_slot_metadata import ConnectionObjectOption
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
    panel.bind_connection_context(
        [
            ConnectionObjectOption(object_name="Form", class_name="QWidget"),
            ConnectionObjectOption(object_name="pushButton", class_name="QPushButton"),
        ]
    )
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


def test_connection_panel_emits_field_edits() -> None:
    panel = ConnectionEditorPanel()
    panel.bind_connection_context(
        [
            ConnectionObjectOption(object_name="Form", class_name="QWidget"),
            ConnectionObjectOption(object_name="pushButton", class_name="QPushButton"),
            ConnectionObjectOption(object_name="lineEdit", class_name="QLineEdit"),
        ]
    )
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
    seen: list[tuple[int, str, str]] = []
    panel.connection_edited.connect(lambda idx, field, value: seen.append((idx, field, value)))

    receiver_combo = panel._table.cellWidget(0, 2)  # type: ignore[attr-defined]
    slot_combo = panel._table.cellWidget(0, 3)  # type: ignore[attr-defined]
    assert receiver_combo is not None
    assert slot_combo is not None
    receiver_combo.setCurrentIndex(receiver_combo.findData("lineEdit"))
    slot_combo.setCurrentIndex(slot_combo.findData("clear()"))

    assert "receiver" in {entry[1] for entry in seen}
    assert seen[-1] == (0, "slot", "clear()")


def test_connection_panel_shows_validation_warning_for_incompatible_legacy_pair() -> None:
    panel = ConnectionEditorPanel()
    panel.bind_connection_context(
        [
            ConnectionObjectOption(object_name="Form", class_name="QWidget"),
            ConnectionObjectOption(object_name="pushButton", class_name="QPushButton"),
        ]
    )
    panel.bind_connections(
        [
            ConnectionModel(
                sender="pushButton",
                signal="clicked(bool)",
                receiver="Form",
                slot="setText(QString)",
            )
        ]
    )

    assert panel._validation_label.text() != ""  # type: ignore[attr-defined]
    assert "Potential mismatch" in panel._validation_label.text()  # type: ignore[attr-defined]


def test_connection_panel_slot_options_are_filtered_by_signal_signature() -> None:
    panel = ConnectionEditorPanel()
    panel.bind_connection_context(
        [
            ConnectionObjectOption(object_name="Form", class_name="QWidget"),
            ConnectionObjectOption(object_name="pushButton", class_name="QPushButton"),
            ConnectionObjectOption(object_name="lineEdit", class_name="QLineEdit"),
        ]
    )
    panel.bind_connections(
        [
            ConnectionModel(
                sender="pushButton",
                signal="clicked()",
                receiver="lineEdit",
                slot="setText(QString)",
            )
        ]
    )
    seen: list[tuple[int, str, str]] = []
    panel.connection_edited.connect(lambda idx, field, value: seen.append((idx, field, value)))

    signal_combo = panel._table.cellWidget(0, 1)  # type: ignore[attr-defined]
    slot_combo = panel._table.cellWidget(0, 3)  # type: ignore[attr-defined]
    assert isinstance(signal_combo, QComboBox)
    assert isinstance(slot_combo, QComboBox)
    assert slot_combo.findData("setText(QString)") >= 0

    signal_combo.setCurrentIndex(signal_combo.findData("clicked(bool)"))
    assert slot_combo.findData("setText(QString)") == -1
    slot_index = slot_combo.findData("setEnabled(bool)")
    assert slot_index >= 0
    slot_combo.setCurrentIndex(slot_index)

    assert seen[-1] == (0, "slot", "setEnabled(bool)")
