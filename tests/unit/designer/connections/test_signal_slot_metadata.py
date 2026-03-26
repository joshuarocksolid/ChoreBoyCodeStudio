"""Unit tests for signal/slot metadata helpers."""

from __future__ import annotations

import pytest

from app.designer.connections.signal_slot_metadata import (
    ConnectionObjectOption,
    connection_object_options,
    has_class_specific_signal_catalog,
    has_class_specific_slot_catalog,
    is_signal_slot_pair_compatible,
    signal_supported_for_class,
    slot_supported_for_class,
)
from app.designer.model import UIModel, WidgetNode

pytestmark = pytest.mark.unit


def test_connection_object_options_collects_widget_class_metadata() -> None:
    root = WidgetNode(
        class_name="QWidget",
        object_name="Form",
        children=[
            WidgetNode(class_name="QPushButton", object_name="pushButton"),
            WidgetNode(class_name="QLineEdit", object_name="lineEdit"),
        ],
    )
    model = UIModel(form_class_name="Form", root_widget=root)

    options = connection_object_options(model)

    assert options == [
        ConnectionObjectOption(object_name="Form", class_name="QWidget"),
        ConnectionObjectOption(object_name="pushButton", class_name="QPushButton"),
        ConnectionObjectOption(object_name="lineEdit", class_name="QLineEdit"),
    ]


def test_signal_slot_pair_compatibility_checks_signature_shape() -> None:
    assert is_signal_slot_pair_compatible("clicked()", "setFocus()") is True
    assert is_signal_slot_pair_compatible("clicked(bool)", "setEnabled(bool)") is True
    assert is_signal_slot_pair_compatible("clicked()", "setText(QString)") is False
    assert is_signal_slot_pair_compatible("clicked(bool)", "setText(QString)") is False


def test_signal_slot_catalog_support_checks() -> None:
    assert has_class_specific_signal_catalog("QPushButton") is True
    assert has_class_specific_slot_catalog("QWidget") is True
    assert signal_supported_for_class("QPushButton", "clicked()") is True
    assert slot_supported_for_class("QWidget", "setFocus()") is True
    assert signal_supported_for_class("QPushButton", "missingSignal()") is False
    assert slot_supported_for_class("QWidget", "missingSlot()") is False
