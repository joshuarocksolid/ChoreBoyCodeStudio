"""Validation aggregation contracts for Designer surface."""

from __future__ import annotations

from dataclasses import dataclass

from app.designer.model import UIModel
from app.designer.validation.lint_rules import find_object_name_lint_issues
from app.designer.validation.name_rules import find_duplicate_object_name_issues


@dataclass(frozen=True)
class ValidationIssue:
    """Normalized validation issue payload."""

    severity: str
    code: str
    message: str
    object_name: str = ""


def build_validation_issues(model: UIModel, *, enable_naming_lint: bool = True) -> list[ValidationIssue]:
    """Build baseline D1 validation issues for the model."""
    issues: list[ValidationIssue] = []
    for issue in find_duplicate_object_name_issues(model):
        issues.append(
            ValidationIssue(
                severity="error",
                code=issue.code,
                message=issue.message,
                object_name=issue.object_name,
            )
        )
    if enable_naming_lint:
        for issue in find_object_name_lint_issues(model):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code=issue.code,
                    message=issue.message,
                    object_name=issue.object_name,
                )
            )

    if model.root_widget.layout is None:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="DLAYOUT001",
                message="Top-level form has no layout.",
                object_name=model.root_widget.object_name,
            )
        )
    return issues
