"""Vendor native artifact validation helpers for packaging."""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.models import RuntimeIssue
from app.project.native_extension_scan import iter_native_artifacts_in_tree
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING


def collect_imported_top_levels_from_tree(tree: ast.AST) -> set[str]:
    """Collect imported top-level module names from one parsed AST."""
    top_levels: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_levels.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_levels.add(node.module.split(".")[0])
    return top_levels


def orphan_vendor_native_issues(
    *,
    project_root: Path,
    imported_top_levels: frozenset[str],
) -> list[RuntimeIssue]:
    """Return blocking issues for native vendor artifacts not referenced by imports."""
    vendor_root = project_root / "vendor"
    if not vendor_root.is_dir():
        return []
    issues: list[RuntimeIssue] = []
    seen_top_levels: set[str] = set()
    for artifact in iter_native_artifacts_in_tree(vendor_root):
        top_level = _native_artifact_top_level(vendor_root, artifact)
        if not top_level or top_level in imported_top_levels or top_level in seen_top_levels:
            continue
        seen_top_levels.add(top_level)
        issues.append(
            RuntimeIssue(
                issue_id=f"package.dependency.orphan_native.{top_level}",
                workflow="package",
                severity="blocking",
                title="Vendored native extension is not referenced by project imports",
                summary=(
                    f"A compiled extension for `{top_level}` exists under `vendor/`, "
                    "but no project import references that top-level module."
                ),
                why_it_happened=(
                    "Packaging blocks orphan native payloads that are not tied to an import graph entry."
                ),
                next_steps=[
                    "Remove the unused native artifact from vendor/.",
                    "Or add an explicit import that references the vendored module before exporting.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={
                    "top_level": top_level,
                    "artifact_path": artifact.relative_to(project_root).as_posix(),
                },
            )
        )
    return issues


def _native_artifact_top_level(vendor_root: Path, artifact: Path) -> str:
    try:
        relative = artifact.relative_to(vendor_root)
    except ValueError:
        return ""
    if not relative.parts:
        return ""
    if len(relative.parts) == 1:
        stem = artifact.stem
        if ".cpython-" in stem:
            stem = stem.split(".cpython-", 1)[0]
        return stem
    return relative.parts[0]
