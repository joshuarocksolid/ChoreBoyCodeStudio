"""Project/runtime diagnostics and health-check reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.bootstrap.capability_probe import run_startup_capability_probe
from app.bootstrap.paths import PathInput
from app.core.models import CapabilityProbeReport


@dataclass(frozen=True)
class DiagnosticItem:
    """One diagnostic check result."""

    check_id: str
    is_ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectHealthReport:
    """Aggregate diagnostics for project and runtime checks."""

    project_root: str
    checks: list[DiagnosticItem]

    @property
    def all_ok(self) -> bool:
        return all(check.is_ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "all_ok": self.all_ok,
            "checks": [
                {
                    "check_id": check.check_id,
                    "is_ok": check.is_ok,
                    "message": check.message,
                    "details": dict(check.details),
                }
                for check in self.checks
            ],
        }


def build_project_health_report(
    project_root: str,
    project_checks: list[DiagnosticItem],
    *,
    state_root: PathInput | None = None,
    temp_root: PathInput | None = None,
) -> ProjectHealthReport:
    """Merge project checks with runtime capability probe results."""
    checks = list(project_checks)
    capability_report = run_startup_capability_probe(state_root=state_root, temp_root=temp_root)
    checks.extend(capability_checks_from_probe(capability_report))
    return ProjectHealthReport(project_root=project_root, checks=checks)


def capability_checks_from_probe(capability_report: CapabilityProbeReport) -> list[DiagnosticItem]:
    """Convert capability probe results into diagnostic items."""
    return [
        DiagnosticItem(
            check_id=f"runtime.{check.check_id}",
            is_ok=check.is_available,
            message=check.message,
            details=check.details,
        )
        for check in capability_report.checks
    ]
