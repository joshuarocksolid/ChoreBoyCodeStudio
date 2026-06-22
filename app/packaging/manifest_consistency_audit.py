"""Dependency manifest consistency checks for packaging export."""

from __future__ import annotations

from pathlib import Path

from app.core.models import RuntimeIssue
from app.project.dependency_manifest import (
    CLASSIFICATION_NATIVE_EXTENSION,
    CLASSIFICATION_PURE_PYTHON,
    load_dependency_manifest,
)
from app.project.native_extension_scan import tree_contains_native_artifacts
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING


def check_manifest_consistency(*, project_root: str) -> list[RuntimeIssue]:
    """Check that cbcs/dependencies.json entries are consistent with vendor/ state."""
    root = Path(project_root).expanduser().resolve()
    manifest = load_dependency_manifest(project_root)
    issues: list[RuntimeIssue] = []

    for entry in manifest.active_entries():
        if not entry.vendor_path:
            continue
        vendor_path = root / entry.vendor_path
        if not vendor_path.exists():
            issues.append(
                RuntimeIssue(
                    issue_id=f"package.dependency.manifest_missing_vendor.{entry.name}",
                    workflow="package",
                    severity="blocking",
                    title=f"Dependency '{entry.name}' is in manifest but missing from vendor/",
                    summary=(
                        f"The dependency manifest lists '{entry.name}' as active, "
                        f"but the vendored files at '{entry.vendor_path}' are missing."
                    ),
                    why_it_happened=(
                        "The vendor directory may have been cleaned, or the dependency "
                        "was removed from disk without updating the manifest."
                    ),
                    next_steps=[
                        f"Re-add '{entry.name}' through the Add Dependency wizard.",
                        "Or remove the entry from the dependency manifest.",
                    ],
                )
            )
            continue

        has_native = tree_contains_native_artifacts(vendor_path)
        if entry.classification == CLASSIFICATION_PURE_PYTHON and has_native:
            issues.append(
                RuntimeIssue(
                    issue_id=f"package.dependency.manifest_native_mismatch.{entry.name}",
                    workflow="package",
                    severity="blocking",
                    title=f"Dependency '{entry.name}' manifest says pure Python but vendor/ has native files",
                    summary=(
                        f"The manifest classifies '{entry.name}' as pure Python, "
                        f"but compiled extension files were found under '{entry.vendor_path}'."
                    ),
                    why_it_happened=(
                        "The dependency manifest classification no longer matches the vendored payload."
                    ),
                    next_steps=[
                        "Re-ingest the dependency so the manifest classification is updated.",
                        "Or remove the native artifacts if they were added accidentally.",
                    ],
                    help_topic=HELP_TOPIC_PACKAGING,
                    evidence={"vendor_path": entry.vendor_path},
                )
            )
        elif entry.classification == CLASSIFICATION_NATIVE_EXTENSION and not has_native:
            issues.append(
                RuntimeIssue(
                    issue_id=f"package.dependency.manifest_pure_mismatch.{entry.name}",
                    workflow="package",
                    severity="degraded",
                    title=f"Dependency '{entry.name}' manifest says native but vendor/ is pure Python",
                    summary=(
                        f"The manifest classifies '{entry.name}' as a native extension, "
                        f"but no compiled extension files were found under '{entry.vendor_path}'."
                    ),
                    why_it_happened=(
                        "The dependency manifest classification may be stale relative to the vendored files."
                    ),
                    next_steps=[
                        "Re-ingest the dependency to refresh manifest classification.",
                        "Or update the manifest entry if the dependency is now pure Python.",
                    ],
                    help_topic=HELP_TOPIC_PACKAGING,
                    evidence={"vendor_path": entry.vendor_path},
                )
            )
    return issues
