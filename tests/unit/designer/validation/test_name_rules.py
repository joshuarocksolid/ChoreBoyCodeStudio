"""Unit tests for designer name validation rules."""

from __future__ import annotations

import pytest

from app.designer.model import UIModel, WidgetNode
from app.designer.validation.name_rules import find_duplicate_object_name_issues
from app.designer.validation.validation_panel import build_validation_issues

pytestmark = pytest.mark.unit


def test_find_duplicate_object_name_issues_returns_error_issue() -> None:
    model = UIModel(
        form_class_name="NameForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="duplicate",
            children=[WidgetNode(class_name="QPushButton", object_name="duplicate")],
        ),
    )

    issues = find_duplicate_object_name_issues(model)

    assert len(issues) == 1
    assert issues[0].code == "DNAME001"
    assert "duplicate" in issues[0].message


def test_build_validation_issues_includes_no_layout_warning() -> None:
    model = UIModel(
        form_class_name="WarnForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="rootWidget"),
    )

    issues = build_validation_issues(model)

    assert any(issue.code == "DLAYOUT001" for issue in issues)


def test_build_validation_issues_can_disable_naming_lint() -> None:
    model = UIModel(
        form_class_name="WarnForm",
        root_widget=WidgetNode(class_name="QWidget", object_name="RootWidget"),
    )

    issues_with_lint = build_validation_issues(model)
    issues_without_lint = build_validation_issues(model, enable_naming_lint=False)

    assert any(issue.code == "DLINT001" for issue in issues_with_lint)
    assert not any(issue.code == "DLINT001" for issue in issues_without_lint)
