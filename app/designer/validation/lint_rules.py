"""Optional lint rules for designer naming conventions."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.designer.model import UIModel

_OBJECT_NAME_RE = re.compile(r"^[a-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class NamingLintIssue:
    """Naming lint issue payload."""

    code: str
    message: str
    object_name: str


def find_object_name_lint_issues(model: UIModel) -> list[NamingLintIssue]:
    """Return naming-convention lint issues for object names."""
    issues: list[NamingLintIssue] = []
    for object_name in model.collect_object_names():
        if _OBJECT_NAME_RE.match(object_name):
            continue
        issues.append(
            NamingLintIssue(
                code="DLINT001",
                message=(
                    f"objectName '{object_name}' violates naming lint: "
                    "use lowerCamelCase with letters, numbers, and underscores."
                ),
                object_name=object_name,
            )
        )
    return issues
