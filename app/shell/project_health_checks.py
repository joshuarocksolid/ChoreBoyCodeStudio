"""Shell-owned project health check collection (project layer seam)."""

from __future__ import annotations

from app.bootstrap.paths import PathInput
from app.core.errors import AppValidationError, ProjectManifestValidationError, ProjectStructureValidationError
from app.project.project_service import ProjectRootState, assess_project_root, open_project
from app.support.diagnostics import DiagnosticItem, ProjectHealthReport, build_project_health_report


def collect_project_health_checks(project_root: PathInput) -> tuple[str, list[DiagnosticItem]]:
    """Collect project structure and manifest diagnostics for one root."""
    checks: list[DiagnosticItem] = []
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
        return normalized_project_root, checks

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

    return normalized_project_root, checks


def run_project_health_check(
    project_root: PathInput,
    *,
    state_root: PathInput | None = None,
    temp_root: PathInput | None = None,
) -> ProjectHealthReport:
    """Run filesystem + manifest + runtime capability diagnostics."""
    normalized_project_root, project_checks = collect_project_health_checks(project_root)
    return build_project_health_report(
        normalized_project_root,
        project_checks,
        state_root=state_root,
        temp_root=temp_root,
    )
