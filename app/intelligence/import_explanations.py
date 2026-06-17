"""Map classifier and layout hints to unresolved-import explanations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.models import ProjectMetadata
from app.intelligence.diagnostics_models import ImportExplanation
from app.intelligence.runtime_import_probe import (
    RuntimeImportProbeResult,
    probe_runtime_module_importability,
)
from app.project.dependency_classifier import (
    CATEGORY_VENDORED_NATIVE,
    ClassifiedModule,
    classify_module,
    has_compiled_extension_candidate,
)
from app.project.import_layout import (
    ProjectImportLayout,
    module_path_prefix_exists,
    module_path_prefix_exists_at_base,
    resolve_project_import_layout,
    suggest_missing_source_root,
)


def build_import_explanation(
    project_root: str | Path,
    module_name: str,
    *,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    project_metadata: ProjectMetadata | None = None,
) -> ImportExplanation:
    """Classify an unresolved import and return a user-facing explanation."""
    root = Path(project_root).expanduser().resolve()
    layout = resolve_project_import_layout(root, project_metadata)
    top_level = module_name.split(".")[0].strip()
    probe_result: RuntimeImportProbeResult | None = None
    if allow_runtime_import_probe and top_level:
        probe_result = probe_runtime_module_importability(top_level)

    missing_source_root = suggest_missing_source_root(layout, module_name)
    project_prefix_exists = module_path_prefix_exists(layout, module_name)
    classified = classify_module(
        project_root=root,
        module_name=module_name,
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=allow_runtime_import_probe,
        metadata=project_metadata,
        layout=layout,
    )
    evidence = _build_evidence(
        module_name=module_name,
        top_level=top_level,
        layout=layout,
        classified=classified,
        missing_source_root=missing_source_root,
        project_prefix_exists=project_prefix_exists,
        probe_result=probe_result,
    )

    if missing_source_root:
        return _source_root_missing_explanation(module_name, missing_source_root, evidence)

    if project_prefix_exists:
        return _project_module_missing_explanation(module_name, evidence)

    if classified.category == CATEGORY_VENDORED_NATIVE:
        return _compiled_extension_unknown_explanation(module_name, evidence)

    if (
        probe_result is not None
        and not probe_result.is_importable
        and probe_result.failure_reason == "import_error"
        and _looks_like_runtime_specific_module(top_level)
    ):
        return _runtime_module_unavailable_explanation(module_name, evidence)

    return _vendored_dependency_missing_explanation(module_name, evidence)


def _build_evidence(
    *,
    module_name: str,
    top_level: str,
    layout: ProjectImportLayout,
    classified: ClassifiedModule,
    missing_source_root: str | None,
    project_prefix_exists: bool,
    probe_result: RuntimeImportProbeResult | None,
) -> dict[str, Any]:
    vendor_root = layout.vendor_root
    evidence: dict[str, Any] = {
        "module_name": module_name,
        "top_level": top_level,
        "project_prefix_exists": project_prefix_exists,
        "vendor_prefix_exists": module_path_prefix_exists_at_base(vendor_root, module_name),
        "vendor_dir_exists": vendor_root.exists(),
        "compiled_extension_candidate": classified.category == CATEGORY_VENDORED_NATIVE
        or has_compiled_extension_candidate(vendor_root, top_level)
        or has_compiled_extension_candidate(layout.project_root, top_level),
        "missing_source_root": missing_source_root,
        "classification_category": classified.category,
    }
    if classified.resolved_path is not None:
        evidence["resolved_path"] = classified.resolved_path
    if probe_result is not None:
        evidence["runtime_probe_reason"] = probe_result.failure_reason
        evidence["runtime_probe_detail"] = probe_result.detail
        evidence["runtime_path"] = probe_result.runtime_path
    return evidence


def _source_root_missing_explanation(
    module_name: str,
    missing_source_root: str,
    evidence: dict[str, Any],
) -> ImportExplanation:
    return ImportExplanation(
        module_name=module_name,
        kind="source_root_missing",
        summary=f"Import root missing for: {module_name}",
        why_it_happened=(
            f"Project files for this import live under `{missing_source_root}/`, but that folder is not configured as a source root. "
            "Imports are resolved from the project root and configured source roots."
        ),
        next_steps=[
            f"Mark `{missing_source_root}` as a Sources Root in the project tree, or add it to source_roots in cbcs/project.json.",
            "Re-run import analysis after updating import roots.",
        ],
        evidence=evidence,
    )


def _project_module_missing_explanation(module_name: str, evidence: dict[str, Any]) -> ImportExplanation:
    return ImportExplanation(
        module_name=module_name,
        kind="project_module_missing",
        summary=f"Project module path is incomplete or missing: {module_name}",
        why_it_happened=(
            "The import points at code that should live inside the project tree, but the full module path cannot be resolved from the current files."
        ),
        next_steps=[
            "Check the module/package file names inside the project.",
            "Add missing `__init__.py` files where package imports are expected.",
            "Update the import path if the module was moved or renamed.",
        ],
        evidence=evidence,
    )


def _compiled_extension_unknown_explanation(module_name: str, evidence: dict[str, Any]) -> ImportExplanation:
    return ImportExplanation(
        module_name=module_name,
        kind="compiled_extension_unknown",
        summary=f"Compiled dependency may not be compatible with the runtime: {module_name}",
        why_it_happened=(
            "The import name matches a compiled extension candidate, and compiled modules can fail on ChoreBoy when the Python/AppRun build does not match."
        ),
        next_steps=[
            "Prefer a pure-Python dependency when possible.",
            "If this must be compiled, verify it targets the same runtime and Python ABI as the shipped AppRun environment.",
            "Re-run import analysis after replacing or rebuilding the dependency.",
        ],
        evidence=evidence,
    )


def _runtime_module_unavailable_explanation(module_name: str, evidence: dict[str, Any]) -> ImportExplanation:
    return ImportExplanation(
        module_name=module_name,
        kind="runtime_module_unavailable",
        summary=f"Module is not available in the shipped runtime: {module_name}",
        why_it_happened=(
            "The editor checked the top-level import in the target runtime process and it did not import successfully there."
        ),
        next_steps=[
            "Do not assume this module exists just because it imports on another machine or Python install.",
            "Vendor the dependency under `vendor/` if the workflow allows it.",
            "Or change the code to use modules known to exist in the AppRun runtime.",
        ],
        evidence=evidence,
    )


def _vendored_dependency_missing_explanation(module_name: str, evidence: dict[str, Any]) -> ImportExplanation:
    return ImportExplanation(
        module_name=module_name,
        kind="vendored_dependency_missing",
        summary=f"Dependency is not present in the project or vendored runtime: {module_name}",
        why_it_happened=(
            "The import is not resolved from project files, vendored dependencies, or known runtime modules."
        ),
        next_steps=[
            "Vendor the dependency under `vendor/` if it is a third-party package.",
            "If it should be part of the project, add the missing module/package files under the project root.",
            "Re-run import analysis after updating the project or vendored dependency tree.",
        ],
        evidence=evidence,
    )


def _looks_like_runtime_specific_module(top_level: str) -> bool:
    if not top_level:
        return False
    if top_level[0].isupper():
        return True
    return top_level.startswith("PySide")
