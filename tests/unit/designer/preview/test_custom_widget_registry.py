"""Unit tests for custom-widget preview registry helpers."""

from __future__ import annotations

import pytest

from app.designer.model import CustomWidgetModel, UIModel, WidgetNode
from app.designer.preview import (
    build_preview_safety_decision,
    preview_registry_from_model,
    promoted_class_names,
    requires_isolated_preview,
)

pytestmark = pytest.mark.unit


def test_preview_registry_from_model_maps_custom_widgets() -> None:
    model = UIModel(
        form_class_name="Form",
        root_widget=WidgetNode(class_name="QWidget", object_name="Form"),
        custom_widgets=[CustomWidgetModel(class_name="FancyWidget", extends="QWidget", header="fancy_widget")],
    )
    registry = preview_registry_from_model(model)
    assert len(registry) == 1
    assert registry[0].class_name == "FancyWidget"
    assert registry[0].header == "fancy_widget"


def test_requires_isolated_preview_flags_promoted_widget_forms() -> None:
    plain_model = UIModel(form_class_name="Plain", root_widget=WidgetNode(class_name="QWidget", object_name="Plain"))
    promoted_model = UIModel(
        form_class_name="Promoted",
        root_widget=WidgetNode(class_name="QWidget", object_name="Promoted"),
        custom_widgets=[CustomWidgetModel(class_name="FancyWidget", extends="QWidget", header="fancy_widget")],
    )
    assert requires_isolated_preview(plain_model) is False
    assert requires_isolated_preview(promoted_model) is True
    assert promoted_class_names(promoted_model) == ("FancyWidget",)
    assert build_preview_safety_decision(promoted_model).requires_isolation is True
