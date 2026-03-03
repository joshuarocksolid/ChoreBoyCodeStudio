"""Shared data models used across bootstrap and services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilityCheckResult:
    """Structured result for a single runtime capability check."""

    check_id: str
    is_available: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "check_id": self.check_id,
            "is_available": self.is_available,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class CapabilityProbeReport:
    """Aggregate capability check results captured at startup."""

    checks: list[CapabilityCheckResult]

    @property
    def all_available(self) -> bool:
        """Return True when every check is available."""
        return all(check.is_available for check in self.checks)

    @property
    def available_count(self) -> int:
        """Return the number of passing checks."""
        return sum(1 for check in self.checks if check.is_available)

    @property
    def total_count(self) -> int:
        """Return the total number of checks."""
        return len(self.checks)

    @property
    def failed_check_ids(self) -> list[str]:
        """Return failed check identifiers in deterministic order."""
        return [check.check_id for check in self.checks if not check.is_available]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "checks": [check.to_dict() for check in self.checks],
            "all_available": self.all_available,
            "available_count": self.available_count,
            "total_count": self.total_count,
            "failed_check_ids": self.failed_check_ids,
        }


@dataclass(frozen=True)
class ProjectMetadata:
    """Canonical `cbcs/project.json` metadata model."""

    schema_version: int
    name: str
    default_entry: str = "main.py"
    default_argv: list[str] = field(default_factory=list)
    working_directory: str = "."
    template: str = "utility_script"
    run_configs: list[dict[str, Any]] = field(default_factory=list)
    env_overrides: dict[str, str] = field(default_factory=dict)
    project_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation with explicit defaults."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "default_entry": self.default_entry,
            "default_argv": list(self.default_argv),
            "working_directory": self.working_directory,
            "template": self.template,
            "run_configs": [dict(config) for config in self.run_configs],
            "env_overrides": dict(self.env_overrides),
            "project_notes": self.project_notes,
        }


@dataclass(frozen=True)
class ProjectFileEntry:
    """Structured filesystem entry for project tree rendering."""

    relative_path: str
    absolute_path: str
    is_directory: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "relative_path": self.relative_path,
            "absolute_path": self.absolute_path,
            "is_directory": self.is_directory,
        }


@dataclass(frozen=True)
class LoadedProject:
    """Structured output for project open/load orchestration."""

    project_root: str
    manifest_path: str
    metadata: ProjectMetadata
    entries: list[ProjectFileEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "project_root": self.project_root,
            "manifest_path": self.manifest_path,
            "metadata": self.metadata.to_dict(),
            "entries": [entry.to_dict() for entry in self.entries],
        }
