"""Static dependency audit tailored to ChoreBoy packaging constraints."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from app.core.models import RuntimeIssue
from app.packaging.layout import is_packaging_excluded_path
from app.packaging.models import DependencyAuditRecord, DependencyAuditReport
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
from app.project.file_inventory import iter_python_files
from app.project.import_layout import ProjectImportLayout, resolve_project_import_layout
from app.project.native_extension_scan import iter_native_artifacts_in_tree
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING

_SUBPROCESS_CALL_NAMES = {"Popen", "call", "check_call", "check_output", "run"}

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

    for file_path in iter_python_files(root, extra_top_level_skips=("vendor",)):
        rel_path = file_path.relative_to(root)
        if is_packaging_excluded_path(rel_path):
            continue
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

        for issue in _subprocess_issues(tree=tree, file_path=file_path, project_root=root):
            _append_issue(issues, issue_keys, issue)

    imported_top_levels = _collect_imported_top_levels(root)
    for orphan_issue in _orphan_vendor_native_issues(
        project_root=root,
        imported_top_levels=imported_top_levels,
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


def _subprocess_issues(
    *,
    tree: ast.AST,
    file_path: Path,
    project_root: Path,
) -> list[RuntimeIssue]:
    issues: list[RuntimeIssue] = []
    rel_file = file_path.relative_to(project_root).as_posix()
    if _imports_subprocess_module(tree):
        issues.append(
            RuntimeIssue(
                issue_id=f"package.subprocess.review.{rel_file}",
                workflow="package",
                severity="degraded",
                title="Project uses subprocess APIs that need ChoreBoy review",
                summary="This project imports `subprocess`, which can behave differently on constrained ChoreBoy systems.",
                why_it_happened="Inside the validated AppRun environment, subprocess execution is intentionally restricted and should not assume arbitrary executables are available.",
                next_steps=[
                    "Review subprocess calls for reliance on executables other than `/bin/sh`.",
                    "Prefer in-process Python or documented shell entrypoints where possible.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={"source_file": rel_file},
            )
        )
    for lineno, command_name in _literal_external_commands(tree):
        issues.append(
            RuntimeIssue(
                issue_id=f"package.subprocess.literal_binary.{rel_file}.{lineno}",
                workflow="package",
                severity="blocking",
                title="Package hardcodes a subprocess target that is unlikely to work on ChoreBoy",
                summary=f"A subprocess call launches `{command_name}` directly instead of `/bin/sh`.",
                why_it_happened="The validated ChoreBoy runtime only guarantees subprocess compatibility through `/bin/sh` inside AppRun.",
                next_steps=[
                    "Rewrite the subprocess call to use a supported shell entrypoint or an in-process alternative.",
                    "Re-run packaging after removing the direct binary assumption.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={
                    "source_file": rel_file,
                    "line_number": lineno,
                    "command_name": command_name,
                },
            )
        )
    for lineno in _shell_true_subprocess_calls(tree):
        issues.append(
            RuntimeIssue(
                issue_id=f"package.subprocess.shell_true.{rel_file}.{lineno}",
                workflow="package",
                severity="blocking",
                title="Package uses shell=True subprocess execution",
                summary="A subprocess call opts into shell parsing, which is not part of the supported ChoreBoy packaging contract.",
                why_it_happened="Shell-mediated subprocesses hide the executable boundary and are difficult to validate under ChoreBoy's restricted runtime.",
                next_steps=[
                    "Replace shell=True with an explicit argv-list launch.",
                    "If a shell is required, call `/bin/sh` explicitly and document the command contract.",
                ],
                help_topic=HELP_TOPIC_PACKAGING,
                evidence={"source_file": rel_file, "line_number": lineno},
            )
        )
    return issues


def _imports_subprocess_module(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "subprocess" for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "subprocess":
                return True
    return False


def _literal_external_commands(tree: ast.AST) -> list[tuple[int, str]]:
    commands: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        command_name = ""
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "subprocess" and func.attr in _SUBPROCESS_CALL_NAMES:
                command_name = _first_command_name(node)
            elif func.value.id == "os" and func.attr in {"execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe", "system", "popen"}:
                command_name = _first_command_name(node)
        if not command_name:
            continue
        if command_name != "/bin/sh":
            commands.append((int(getattr(node, "lineno", 1) or 1), command_name))
    return commands


def _first_command_name(node: ast.Call) -> str:
    if not node.args:
        return ""
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        command_text = first_arg.value.strip()
        if not command_text:
            return ""
        return command_text.split()[0]
    if isinstance(first_arg, (ast.List, ast.Tuple)) and first_arg.elts:
        first_element = first_arg.elts[0]
        if isinstance(first_element, ast.Constant) and isinstance(first_element.value, str):
            return first_element.value.strip()
    return ""


def _shell_true_subprocess_calls(tree: ast.AST) -> list[int]:
    line_numbers: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        if func.value.id != "subprocess" or func.attr not in _SUBPROCESS_CALL_NAMES:
            continue
        for keyword in node.keywords:
            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                line_numbers.append(int(getattr(node, "lineno", 1) or 1))
    return line_numbers


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


def _collect_imported_top_levels(project_root: Path) -> frozenset[str]:
    top_levels: set[str] = set()
    for file_path in iter_python_files(project_root, extra_top_level_skips=("vendor",)):
        rel_path = file_path.relative_to(project_root)
        if is_packaging_excluded_path(rel_path):
            continue
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_levels.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_levels.add(node.module.split(".")[0])
    return frozenset(top_levels)


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


def _orphan_vendor_native_issues(
    *,
    project_root: Path,
    imported_top_levels: frozenset[str],
) -> list[RuntimeIssue]:
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


def check_manifest_consistency(*, project_root: str) -> list[RuntimeIssue]:
    """Check that cbcs/dependencies.json entries are consistent with vendor/ state."""
    from app.project.dependency_manifest import (
        CLASSIFICATION_NATIVE_EXTENSION,
        CLASSIFICATION_PURE_PYTHON,
        load_dependency_manifest,
    )
    from app.project.native_extension_scan import tree_contains_native_artifacts

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
    parts = [f"Dependency audit found {blocking_count} blocking" if blocking_count else "Dependency audit has no blocking issues"]
    if degraded_count:
        parts.append(f"{degraded_count} degraded")
    if count_text:
        parts.append(count_text)
    return "; ".join(parts) + "."
