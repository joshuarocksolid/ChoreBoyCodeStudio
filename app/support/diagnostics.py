"""Project/runtime diagnostics and health-check reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.bootstrap.capability_probe import run_startup_capability_probe
from app.bootstrap.paths import PathInput
from app.core.errors import AppValidationError, ProjectManifestValidationError, ProjectStructureValidationError
from app.project.project_service import ProjectRootState, assess_project_root, open_project


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


def run_project_health_check(
    project_root: PathInput,
    *,
    state_root: PathInput | None = None,
    temp_root: PathInput | None = None,
) -> ProjectHealthReport:
    """Run filesystem + manifest + runtime capability diagnostics."""
    checks: list[DiagnosticItem] = []
    normalized_project_root = str(project_root)

    project_assessment = assess_project_root(project_root)
    normalized_project_root = str(project_assessment.project_root)
    if project_assessment.state != ProjectRootState.INVALID:
        checks.append(
            DiagnosticItem(
                check_id="project_structure",
                is_ok=True,
                message=project_assessment.message,
                details={
                    "project_root": normalized_project_root,
                    "state": project_assessment.state.value,
                    "inferred_entry": project_assessment.inferred_entry,
                },
            )
        )
    else:
        checks.append(
            DiagnosticItem(
                check_id="project_structure",
                is_ok=False,
                message=project_assessment.message,
                details={
                    "project_root": normalized_project_root,
                    "state": project_assessment.state.value,
                },
            )
        )
        capability_report = run_startup_capability_probe(state_root=state_root, temp_root=temp_root)
        checks.extend(_capability_checks(capability_report))
        return ProjectHealthReport(project_root=normalized_project_root, checks=checks)

    try:
        loaded_project = open_project(project_root)
    except (AppValidationError, ProjectManifestValidationError, ProjectStructureValidationError) as exc:
        checks.append(DiagnosticItem(check_id="project_manifest", is_ok=False, message=str(exc)))
    else:
        manifest_message = (
            "Project manifest on disk."
            if loaded_project.manifest_materialized
            else "Project metadata loaded (in-memory; cbcs/project.json not written yet)."
        )
        checks.append(
            DiagnosticItem(
                check_id="project_manifest",
                is_ok=True,
                message=manifest_message,
                details={
                    "project_name": loaded_project.metadata.name,
                    "entry_count": len(loaded_project.entries),
                    "manifest_materialized": loaded_project.manifest_materialized,
                },
            )
        )

    capability_report = run_startup_capability_probe(state_root=state_root, temp_root=temp_root)
    checks.extend(_capability_checks(capability_report))
    return ProjectHealthReport(project_root=normalized_project_root, checks=checks)


def _capability_checks(capability_report: Any) -> list[DiagnosticItem]:
    return [
        DiagnosticItem(
            check_id=f"runtime.{check.check_id}",
            is_ok=check.is_available,
            message=check.message,
            details=check.details,
        )
        for check in capability_report.checks
    ]
