"""Unit tests for designer drop rule helpers."""

from __future__ import annotations

import pytest

from app.designer.canvas.drop_rules import can_insert_widget, is_parent_drop_target

pytestmark = pytest.mark.unit


def test_is_parent_drop_target_for_supported_container_classes() -> None:
    assert is_parent_drop_target("QWidget") is True
    assert is_parent_drop_target("QGroupBox") is True
    assert is_parent_drop_target("QLineEdit") is False


def test_can_insert_widget_rejects_non_container_parent() -> None:
    assert (
        can_insert_widget(
            parent_class_name="QLineEdit",
            child_class_name="QPushButton",
            is_layout_item=False,
            parent_has_layout=False,
        )
        is False
    )


def test_can_insert_widget_requires_layout_for_layout_items() -> None:
    assert (
        can_insert_widget(
            parent_class_name="QWidget",
            child_class_name="QSpacerItem",
            is_layout_item=True,
            parent_has_layout=False,
        )
        is False
    )
    assert (
        can_insert_widget(
            parent_class_name="QWidget",
            child_class_name="QSpacerItem",
            is_layout_item=True,
            parent_has_layout=True,
        )
        is True
    )


def test_can_insert_widget_allows_tranche_one_widgets_under_container_parent() -> None:
    supported_widgets = [
        "QSpinBox",
        "QDoubleSpinBox",
        "QSlider",
        "QProgressBar",
        "QDateEdit",
        "QTimeEdit",
        "QDateTimeEdit",
        "QDial",
        "QToolButton",
        "QDialogButtonBox",
    ]
    for class_name in supported_widgets:
        assert (
            can_insert_widget(
                parent_class_name="QWidget",
                child_class_name=class_name,
                is_layout_item=False,
                parent_has_layout=False,
            )
            is True
        )


def test_can_insert_widget_allows_tranche_two_widgets_under_container_parent() -> None:
    supported_widgets = [
        "QListWidget",
        "QTreeWidget",
        "QTableWidget",
        "QStackedWidget",
        "QSplitter",
    ]
    for class_name in supported_widgets:
        assert (
            can_insert_widget(
                parent_class_name="QWidget",
                child_class_name=class_name,
                is_layout_item=False,
                parent_has_layout=False,
            )
            is True
        )

    assert (
        can_insert_widget(
            parent_class_name="QWidget",
            child_class_name="QMainWindow",
            is_layout_item=False,
            parent_has_layout=False,
        )
        is True
    )
    assert (
        can_insert_widget(
            parent_class_name="QGroupBox",
            child_class_name="QMainWindow",
            is_layout_item=False,
            parent_has_layout=False,
        )
        is False
    )
