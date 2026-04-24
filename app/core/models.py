"""Shared data models used across bootstrap and services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_RUNTIME_SEVERITY_ORDER = {
    "clear": 0,
    "advisory": 1,
    "degraded": 2,
    "blocking": 3,
}


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
class RuntimeIssue:
    """Structured explanation item for runtime, project, run, or packaging state."""

    issue_id: str
    workflow: str
    severity: str
    title: str
    summary: str
    why_it_happened: str
    next_steps: list[str] = field(default_factory=list)
    help_topic: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocking(self) -> bool:
        return self.severity == "blocking"

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "workflow": self.workflow,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "why_it_happened": self.why_it_happened,
            "next_steps": list(self.next_steps),
            "help_topic": self.help_topic,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class RuntimeIssueReport:
    """Aggregate report of structured runtime issues."""

    workflow: str
    issues: list[RuntimeIssue]

    @property
    def total_count(self) -> int:
        return len(self.issues)

    @property
    def blocking_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "blocking")

    @property
    def degraded_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "degraded")

    @property
    def advisory_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "advisory")

    @property
    def is_clear(self) -> bool:
        return not self.issues

    @property
    def highest_severity(self) -> str:
        if not self.issues:
            return "clear"
        return max(
            (issue.severity for issue in self.issues),
            key=lambda severity: _RUNTIME_SEVERITY_ORDER.get(severity, 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "total_count": self.total_count,
            "blocking_count": self.blocking_count,
            "degraded_count": self.degraded_count,
            "advisory_count": self.advisory_count,
            "highest_severity": self.highest_severity,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class WorkflowPreflightResult:
    """Editor-side preflight result for a workflow before launch/export."""

    workflow: str
    issues: list[RuntimeIssue]
    summary: str

    @property
    def is_ready(self) -> bool:
        return not any(issue.is_blocking for issue in self.issues)

    @property
    def highest_severity(self) -> str:
        if not self.issues:
            return "clear"
        return max(
            (issue.severity for issue in self.issues),
            key=lambda severity: _RUNTIME_SEVERITY_ORDER.get(severity, 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "is_ready": self.is_ready,
            "summary": self.summary,
            "highest_severity": self.highest_severity,
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class ProjectMetadata:
    """Canonical `cbcs/project.json` metadata model."""

    schema_version: int
    name: str
    project_id: str = "proj_legacy_unknown"
    default_entry: str = "main.py"
    default_argv: list[str] = field(default_factory=list)
    working_directory: str = "."
    template: str = "utility_script"
    run_configs: list[dict[str, Any]] = field(default_factory=list)
    env_overrides: dict[str, str] = field(default_factory=dict)
    project_notes: str = ""
    exclude_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation with explicit defaults."""
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "name": self.name,
            "default_entry": self.default_entry,
            "default_argv": list(self.default_argv),
            "working_directory": self.working_directory,
            "template": self.template,
            "run_configs": [dict(config) for config in self.run_configs],
            "env_overrides": dict(self.env_overrides),
            "project_notes": self.project_notes,
        }
        if self.exclude_patterns:
            payload["exclude_patterns"] = list(self.exclude_patterns)
        return payload


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
    manifest_materialized: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "project_root": self.project_root,
            "manifest_path": self.manifest_path,
            "metadata": self.metadata.to_dict(),
            "entries": [entry.to_dict() for entry in self.entries],
            "manifest_materialized": self.manifest_materialized,
        }
