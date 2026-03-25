"""Unit tests for designer naming lint rules."""

from __future__ import annotations

import pytest

from app.designer.model import UIModel, WidgetNode
from app.designer.validation import find_object_name_lint_issues

pytestmark = pytest.mark.unit


def test_find_object_name_lint_issues_flags_non_camel_case_names() -> None:
    model = UIModel(
        form_class_name="LintForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="RootWidget",
            children=[WidgetNode(class_name="QPushButton", object_name="validButton")],
        ),
    )
    issues = find_object_name_lint_issues(model)
    assert len(issues) == 1
    assert issues[0].code == "DLINT001"
    assert issues[0].object_name == "RootWidget"


def test_find_object_name_lint_issues_accepts_lower_camel_case() -> None:
    model = UIModel(
        form_class_name="LintForm",
        root_widget=WidgetNode(
            class_name="QWidget",
            object_name="rootWidget",
            children=[WidgetNode(class_name="QLineEdit", object_name="lineEdit")],
        ),
    )
    assert find_object_name_lint_issues(model) == []
