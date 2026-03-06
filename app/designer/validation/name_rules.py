"""Name validation rules for Designer object trees."""

from __future__ import annotations

from dataclasses import dataclass

from app.designer.model import UIModel


@dataclass(frozen=True)
class NameValidationIssue:
    """Duplicate-name issue payload."""

    code: str
    message: str
    object_name: str


def find_duplicate_object_name_issues(model: UIModel) -> list[NameValidationIssue]:
    """Return duplicate object-name issues for the provided model."""
    issues: list[NameValidationIssue] = []
    for duplicate_name in model.duplicate_object_names():
        issues.append(
            NameValidationIssue(
                code="DNAME001",
                message=f"Duplicate objectName '{duplicate_name}' found.",
                object_name=duplicate_name,
            )
        )
    return issues
