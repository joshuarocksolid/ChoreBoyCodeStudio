"""Adapt intelligence import diagnostics into support-layer snapshots."""

from __future__ import annotations

from app.intelligence.diagnostics_service import ImportDiagnostic, explain_unresolved_import
from app.support.contracts import ImportExplanationSnapshot, UnresolvedImportDiagnostic


def unresolved_import_diagnostic_from_intelligence(diagnostic: ImportDiagnostic) -> UnresolvedImportDiagnostic:
    """Convert one intelligence diagnostic into the support DTO."""
    return UnresolvedImportDiagnostic(
        file_path=diagnostic.file_path,
        line_number=diagnostic.line_number,
        message=diagnostic.message,
    )


def resolve_import_explanation(
    project_root: str,
    module_name: str,
    known_runtime_modules: frozenset[str] | None,
    allow_runtime_import_probe: bool,
) -> ImportExplanationSnapshot:
    """Resolve one import explanation via the intelligence service."""
    explanation = explain_unresolved_import(
        project_root,
        module_name,
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=allow_runtime_import_probe,
    )
    return ImportExplanationSnapshot(
        module_name=explanation.module_name,
        kind=explanation.kind,
        summary=explanation.summary,
        why_it_happened=explanation.why_it_happened,
        next_steps=list(explanation.next_steps),
        evidence=dict(explanation.evidence),
    )
