"""Core exception hierarchy for explicit validation failures."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class AppValidationError(ValueError):
    """Base class for validation errors with optional field/path context."""

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        manifest_path: Optional[Path] = None,
    ) -> None:
        self.message = message
        self.field = field
        self.manifest_path = manifest_path
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [self.message]
        if self.field:
            parts.append(f"field={self.field}")
        if self.manifest_path is not None:
            parts.append(f"path={self.manifest_path}")
        return " | ".join(parts)


class ProjectManifestValidationError(AppValidationError):
    """Raised when `.cbcs/project.json` fails validation."""


class ProjectLoadValidationError(AppValidationError):
    """Base class for project open/load validation failures."""

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        manifest_path: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self.project_root = project_root
        super().__init__(
            message,
            field=field,
            manifest_path=manifest_path,
        )

    def _format_message(self) -> str:
        base_message = super()._format_message()
        if self.project_root is None:
            return base_message
        return f"{base_message} | project_root={self.project_root}"


class ProjectStructureValidationError(ProjectLoadValidationError):
    """Raised when project filesystem layout is missing required structure."""


class ProjectEnumerationError(ProjectLoadValidationError):
    """Raised when project file enumeration fails unexpectedly."""


class RunManifestValidationError(AppValidationError):
    """Raised when runner manifest validation fails."""


class RunLifecycleError(AppValidationError):
    """Raised when run lifecycle actions fail (launch/stop/state)."""
