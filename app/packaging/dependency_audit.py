"""Static dependency audit tailored to ChoreBoy packaging constraints."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from app.core.models import RuntimeIssue
from app.packaging.manifest_consistency_audit import check_manifest_consistency
from app.packaging.models import DependencyAuditRecord, DependencyAuditReport
from app.packaging.payload_policy import DEFAULT_PACKAGING_PAYLOAD_POLICY
from app.packaging.subprocess_packaging_rules import subprocess_issues
from app.packaging.vendor_native_validation import (
    collect_imported_top_levels_from_tree,
    orphan_vendor_native_issues,
)
from app.project.dependency_classifier import (
    CATEGORY_FIRST_PARTY,
    CATEGORY_FIRST_PARTY_RELATIVE,
    CATEGORY_MISSING,
    CATEGORY_MISSING_RELATIVE,
    CATEGORY_RUNTIME,
    CATEGORY_STDLIB,
    CATEGORY_VENDORED,
    CATEGORY_VENDORED_NATIVE,
    classify_module,
    classify_relative_import,
)
from app.project.import_layout import ProjectImportLayout, resolve_project_import_layout
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING

_CATEGORY_DETAILS: dict[str, str] = {
    CATEGORY_STDLIB: "Python standard library import.",
    CATEGORY_FIRST_PARTY: "Project-local module resolved from source tree.",
    CATEGORY_FIRST_PARTY_RELATIVE: "Relative import resolved inside the project source tree.",
    CATEGORY_VENDORED: "Vendored dependency included under project vendor/.",
    CATEGORY_VENDORED_NATIVE: "Vendored dependency appears to ship a compiled extension.",
    CATEGORY_RUNTIME: "Resolved from AppRun runtime module inventory.",
    CATEGORY_MISSING: "Import is not resolved from project files, vendor/, or the AppRun runtime.",
    CATEGORY_MISSING_RELATIVE: "Relative import target could not be resolved from the current package path.",
}

_CATEGORY_TO_CLASSIFICATION: dict[str, str] = {
    CATEGORY_STDLIB: "stdlib",
    CATEGORY_FIRST_PARTY: "first_party",
    CATEGORY_FIRST_PARTY_RELATIVE: "first_party_relative",
    CATEGORY_VENDORED: "vendored",
    CATEGORY_VENDORED_NATIVE: "vendored_native",
    CATEGORY_RUNTIME: "runtime",
    CATEGORY_MISSING: "missing",
    CATEGORY_MISSING_RELATIVE: "missing_relative",
}


def run_dependency_audit(
    *,
    project_root: str,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    layout: ProjectImportLayout | None = None,
) -> DependencyAuditReport:
    """Audit first-party project imports against project, vendor, and runtime availability."""
    root = Path(project_root).expanduser().resolve()
    resolved_layout = layout or resolve_project_import_layout(root)
    records: list[DependencyAuditRecord] = []
    issues: list[RuntimeIssue] = []
    issue_keys: set[tuple[str, str, str]] = set()
    classification_counts: Counter[str] = Counter()
    imported_top_levels: set[str] = set()

    for file_path in DEFAULT_PACKAGING_PAYLOAD_POLICY.iter_audit_python_files(root):
        rel_path = file_path.relative_to(root)
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            _append_issue(
                issues,
                issue_keys,
                RuntimeIssue(
                    issue_id="package.audit.syntax_error",
                    workflow="package",
                    severity="degraded",
                    title="Dependency audit skipped a file with syntax errors",
                    summary="One Python file could not be parsed for dependency checks.",
                    why_it_happened="Static packaging validation does not execute project code and needs valid Python syntax to inspect imports.",
                    next_steps=[
                        "Fix the syntax error and run Package Project again for a full dependency audit.",
                        "If you intentionally want to export broken work-in-progress code, review the package report before sharing it.",
                    ],
                    help_topic=HELP_TOPIC_PACKAGING,
                    evidence={
                        "file_path": str(rel_path),
                        "line_number": int(exc.lineno or 1),
                        "message": exc.msg,
                    },
                ),
            )
            continue

        imported_top_levels.update(collect_imported_top_levels_from_tree(tree))

        for record in _collect_import_records(
            tree=tree,
            file_path=file_path,
            project_root=root,
            layout=resolved_layout,
            known_runtime_modules=known_runtime_modules,
            allow_runtime_import_probe=allow_runtime_import_probe,
        ):
            records.append(record)
            classification_counts[record.classification] += 1
            issue = _issue_for_record(record)
            if issue is not None:
                _append_issue(issues, issue_keys, issue)

        for issue in subprocess_issues(tree=tree, file_path=file_path, project_root=root):
            _append_issue(issues, issue_keys, issue)

    for orphan_issue in orphan_vendor_native_issues(
        project_root=root,
        imported_top_levels=frozenset(imported_top_levels),
    ):
        _append_issue(issues, issue_keys, orphan_issue)

    summary = _build_summary(classification_counts, issues)
    records.sort(key=lambda item: (item.source_file, item.line_number, item.module_name))
    return DependencyAuditReport(
        project_root=str(root),
        records=records,
        issues=issues,
        summary=summary,
    )


def _collect_import_records(
    *,
    tree: ast.AST,
    file_path: Path,
    project_root: Path,
    layout: ProjectImportLayout,
    known_runtime_modules: frozenset[str] | None,
    allow_runtime_import_probe: bool,
) -> list[DependencyAuditRecord]:
    records: list[DependencyAuditRecord] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                records.append(
                    _classify_import(
                        module_name=alias.name,
                        file_path=file_path,
                        line_number=int(getattr(node, "lineno", 1) or 1),
                        project_root=project_root,
                        layout=layout,
                        known_runtime_modules=known_runtime_modules,
                        allow_runtime_import_probe=allow_runtime_import_probe,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            line_number = int(getattr(node, "lineno", 1) or 1)
            if node.level > 0:
                relative_module = node.module or ""
                if relative_module:
                    records.append(
                        _classify_relative_import_record(
                            module_name=relative_module,
                            level=node.level,
                            file_path=file_path,
                            line_number=line_number,
                            project_root=project_root,
                            layout=layout,
                        )
                    )
                else:
                    for alias in node.names:
                        records.append(
                            _classify_relative_import_record(
                                module_name=alias.name,
                                level=node.level,
                                file_path=file_path,
                                line_number=line_number,
                                project_root=project_root,
                                layout=layout,
                            )
                        )
            elif node.module:
                records.append(
                    _classify_import(
                        module_name=node.module,
                        file_path=file_path,
                        line_number=line_number,
                        project_root=project_root,
                        layout=layout,
                        known_runtime_modules=known_runtime_modules,
                        allow_runtime_import_probe=allow_runtime_import_probe,
                    )
                )
    return records


def _classify_import(
    *,
    module_name: str,
    file_path: Path,
    line_number: int,
    project_root: Path,
    layout: ProjectImportLayout,
    known_runtime_modules: frozenset[str] | None,
    allow_runtime_import_probe: bool,
) -> DependencyAuditRecord:
    rel_file = file_path.relative_to(project_root).as_posix()
    classification = classify_module(
        project_root=project_root,
        module_name=module_name,
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=allow_runtime_import_probe,
        layout=layout,
    )
    return DependencyAuditRecord(
        source_file=rel_file,
        line_number=line_number,
        module_name=module_name,
        classification=_CATEGORY_TO_CLASSIFICATION[classification.category],
        resolved_path=classification.resolved_path,
        detail=_audit_detail_for(classification.category, classification.resolved_path),
    )


def _classify_relative_import_record(
    *,
    module_name: str,
    level: int,
    file_path: Path,
    line_number: int,
    project_root: Path,
    layout: ProjectImportLayout,
) -> DependencyAuditRecord:
    rel_file = file_path.relative_to(project_root).as_posix()
    classification = classify_relative_import(
        project_root=project_root,
        file_path=file_path,
        module_name=module_name,
        level=level,
        layout=layout,
    )
    return DependencyAuditRecord(
        source_file=rel_file,
        line_number=line_number,
        module_name=classification.module_name,
        classification=_CATEGORY_TO_CLASSIFICATION[classification.category],
        resolved_path=classification.resolved_path,
        detail=_CATEGORY_DETAILS[classification.category],
    )


def _audit_detail_for(category: str, resolved_path: str | None) -> str:
    if category == CATEGORY_VENDORED_NATIVE and resolved_path is None:
        return (
            "Vendored native extension detected without an approved in-process loader declaration."
        )
    return _CATEGORY_DETAILS[category]


def _issue_for_record(record: DependencyAuditRecord) -> RuntimeIssue | None:
    if record.classification == "missing":
        return RuntimeIssue(
            issue_id=f"package.dependency.missing.{record.module_name}",
            workflow="package",
            severity="blocking",
            title="Dependency is missing from the package/runtime",
            summary=f"The package depends on `{record.module_name}`, but it is not available from project files, vendor/, or AppRun.",
            why_it_happened="Exports should fail before sharing when a dependency is obviously absent on the target runtime.",
            next_steps=[
                "Vendor the dependency under `vendor/`, or add the missing project module.",
                "If the dependency should come from the runtime, verify it imports successfully under FreeCAD AppRun.",
            ],
            help_topic=HELP_TOPIC_PACKAGING,
            evidence={
                "source_file": record.source_file,
                "line_number": record.line_number,
                "module_name": record.module_name,
            },
        )
    if record.classification == "missing_relative":
        return RuntimeIssue(
            issue_id=f"package.dependency.relative_missing.{record.module_name}",
            workflow="package",
            severity="blocking",
            title="Relative import target is missing",
            summary=f"The package references a relative import that does not resolve: `{record.module_name}`.",
            why_it_happened="A relative import points at code that is missing, renamed, or no longer packaged from the current folder layout.",
            next_steps=[
                "Restore the missing module/package path.",
                "Or update the import to match the current source tree before packaging again.",
            ],
            help_topic=HELP_TOPIC_PACKAGING,
            evidence={
                "source_file": record.source_file,
                "line_number": record.line_number,
                "module_name": record.module_name,
            },
        )
    if record.classification == "vendored_native":
        return RuntimeIssue(
            issue_id=f"package.dependency.native_extension.{record.module_name}",
            workflow="package",
            severity="blocking",
            title="Vendored native extension needs an explicit loader strategy",
            summary=f"`{record.module_name}` appears to rely on compiled extension files under `vendor/`.",
            why_it_happened="ChoreBoy writable locations are mounted `noexec`, so native modules need an approved in-process load path rather than a normal extracted wheel assumption.",
            next_steps=[
                "Prefer a pure-Python dependency when practical.",
                "If the native dependency is required, document and ship an approved AppRun-compatible in-process loader strategy before exporting.",
            ],
            help_topic=HELP_TOPIC_PACKAGING,
            evidence={
                "source_file": record.source_file,
                "line_number": record.line_number,
                "module_name": record.module_name,
                "resolved_path": record.resolved_path,
            },
        )
    return None


def _append_issue(
    issues: list[RuntimeIssue],
    issue_keys: set[tuple[str, str, str]],
    issue: RuntimeIssue,
) -> None:
    key = (issue.issue_id, issue.title, issue.summary)
    if key in issue_keys:
        return
    issue_keys.add(key)
    issues.append(issue)


def _build_summary(classification_counts: Counter[str], issues: list[RuntimeIssue]) -> str:
    if not classification_counts and not issues:
        return "No Python imports were discovered for package dependency audit."
    count_text = ", ".join(
        f"{classification_counts[name]} {name.replace('_', ' ')}"
        for name in sorted(classification_counts.keys())
    )
    blocking_count = sum(1 for issue in issues if issue.severity == "blocking")
    degraded_count = sum(1 for issue in issues if issue.severity == "degraded")
    if not issues:
        return f"Dependency audit is clear: {count_text}."
    parts = [
        f"Dependency audit found {blocking_count} blocking"
        if blocking_count
        else "Dependency audit has no blocking issues"
    ]
    if degraded_count:
        parts.append(f"{degraded_count} degraded")
    if count_text:
        parts.append(count_text)
    return "; ".join(parts) + "."


__all__ = ("check_manifest_consistency", "run_dependency_audit")
