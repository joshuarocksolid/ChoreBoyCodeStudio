"""Static dependency audit tailored to ChoreBoy packaging constraints."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from app.core.models import RuntimeIssue
from app.packaging.manifest_consistency_audit import check_manifest_consistency
from app.packaging.models import DependencyAuditRecord, DependencyAuditReport
from app.packaging.payload_policy import DEFAULT_PACKAGING_PAYLOAD_POLICY
from app.packaging.subprocess_packaging_rules import running_freecad_table_key, subprocess_issues
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
from app.project.import_layout import (
    ProjectImportLayout,
    resolve_import_at_base,
    resolve_import_from_module,
    resolve_project_import_layout,
)
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


@dataclass(frozen=True)
class _ImportSite:
    module_level: bool
    guarded: bool


def run_dependency_audit(
    *,
    project_root: str,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    layout: ProjectImportLayout | None = None,
    entry_file: str = "",
    freecad_version: str | None = None,
) -> DependencyAuditReport:
    """Audit first-party project imports against project, vendor, and runtime availability."""
    if freecad_version is None:
        freecad_version = running_freecad_table_key()
    root = Path(project_root).expanduser().resolve()
    resolved_layout = layout or resolve_project_import_layout(root)
    import_paths = _reachable_import_paths(root, entry_file.strip(), resolved_layout)
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

        rel_posix = rel_path.as_posix()
        reachable = not import_paths or rel_posix in import_paths
        import_path = import_paths.get(rel_posix, "")
        if not reachable:
            import_path = "not imported by any file the app loads"
        for record, module_level, guarded in _collect_import_records(
            tree=tree,
            file_path=file_path,
            project_root=root,
            layout=resolved_layout,
            known_runtime_modules=known_runtime_modules,
            allow_runtime_import_probe=allow_runtime_import_probe,
        ):
            records.append(record)
            classification_counts[record.classification] += 1
            issue = _issue_for_record(
                record,
                reachable=reachable,
                module_level=module_level,
                guarded=guarded,
                import_path=import_path,
            )
            if issue is not None:
                _append_issue(issues, issue_keys, issue)

        for issue in subprocess_issues(
            tree=tree,
            file_path=file_path,
            project_root=root,
            import_path=import_path,
            freecad_version=freecad_version,
        ):
            if not reachable and issue.is_blocking:
                issue = replace(
                    issue,
                    severity="degraded",
                    why_it_happened=(
                        issue.why_it_happened
                        + " The export continues because the app never loads this file."
                    ),
                )
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
) -> list[tuple[DependencyAuditRecord, bool, bool]]:
    sites = _import_sites(tree)
    records: list[tuple[DependencyAuditRecord, bool, bool]] = []

    def _append(node: ast.AST, record: DependencyAuditRecord) -> None:
        site = sites.get(id(node), _ImportSite(module_level=True, guarded=False))
        records.append((record, site.module_level, site.guarded))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _append(
                    node,
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
                    _append(
                        node,
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
                        _append(
                            node,
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
                _append(
                    node,
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


def _issue_for_record(
    record: DependencyAuditRecord,
    *,
    reachable: bool,
    module_level: bool,
    guarded: bool,
    import_path: str,
) -> RuntimeIssue | None:
    if record.classification in {"missing", "missing_relative"}:
        return _missing_import_issue(
            record,
            reachable=reachable,
            module_level=module_level,
            guarded=guarded,
            import_path=import_path,
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
                "import_path": import_path,
                "report_row": f"Native extension: {record.module_name}",
            },
        )
    return None


def _missing_import_issue(
    record: DependencyAuditRecord,
    *,
    reachable: bool,
    module_level: bool,
    guarded: bool,
    import_path: str,
) -> RuntimeIssue:
    stops_export = reachable and module_level and not guarded
    module_name = record.module_name
    source = record.source_file
    if stops_export:
        summary = (
            f"{source} runs `import {module_name}` when the app starts. "
            f"{module_name} is not in your project and not in ChoreBoy's FreeCAD, "
            "so the packaged app would stop with ModuleNotFoundError."
        )
        why = (
            "CBCS follows the imports from your entry file. "
            f"This file is always loaded ({import_path}), and the import is not inside try."
        )
        next_steps = [
            "Copy the module into your project's vendor/ folder, or",
            "remove the import, or",
            "if the app can run without it, put the import inside try: ... except ImportError:.",
        ]
        row = f"Missing module: {module_name}"
        severity = "blocking"
    elif guarded and reachable:
        summary = (
            f"{source} imports {module_name} inside try: ... except ImportError:, "
            "so the app can start without it. The parts of your app that use it will not work on ChoreBoy."
        )
        why = (
            "This is only a warning because your code already handles the missing module. "
            "The export continues."
        )
        next_steps = [
            f"If you need {module_name} on ChoreBoy, copy it into vendor/.",
            "Otherwise, no change is needed.",
        ]
        row = f"Optional module not found: {module_name}"
        severity = "degraded"
    elif not reachable:
        summary = (
            f"{source} imports {module_name}, but no file your app loads imports {source}. "
            "The packaged app will start normally."
        )
        why = (
            "CBCS follows the imports from the entry file and never reaches this file. "
            "The export continues."
        )
        next_steps = [
            f"Delete {source} if you no longer use it, or",
            "leave it. It does not affect the packaged app.",
        ]
        row = f"Unused file imports a missing module: {module_name}"
        severity = "degraded"
    else:
        summary = (
            f"{source} imports {module_name} inside a function, so the import does not run when the app starts."
        )
        why = "The export continues. The packaged app fails only if that function runs and the module is still missing."
        next_steps = [
            f"If that function must work on ChoreBoy, copy {module_name} into vendor/.",
            "Otherwise, no change is needed.",
        ]
        row = f"Optional module not found: {module_name}"
        severity = "degraded"
    prefix = "package.dependency.missing" if record.classification == "missing" else "package.dependency.relative_missing"
    return RuntimeIssue(
        issue_id=f"{prefix}.{module_name}",
        workflow="package",
        severity=severity,
        title=f"{module_name} is not in the package",
        summary=summary,
        why_it_happened=why,
        next_steps=next_steps,
        help_topic=HELP_TOPIC_PACKAGING,
        evidence={
            "source_file": source,
            "line_number": record.line_number,
            "module_name": module_name,
            "import_path": import_path,
            "report_row": row,
        },
    )


def _import_sites(tree: ast.AST) -> dict[int, _ImportSite]:
    sites: dict[int, _ImportSite] = {}

    def visit(node: ast.AST, *, function_depth: int, guard_depth: int, type_checking_depth: int) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            sites[id(node)] = _ImportSite(
                module_level=function_depth == 0 and type_checking_depth == 0,
                guarded=guard_depth > 0 or type_checking_depth > 0,
            )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in node.body:
                visit(
                    child,
                    function_depth=function_depth + 1,
                    guard_depth=guard_depth,
                    type_checking_depth=type_checking_depth,
                )
            return
        if isinstance(node, ast.Lambda):
            visit(
                node.body,
                function_depth=function_depth + 1,
                guard_depth=guard_depth,
                type_checking_depth=type_checking_depth,
            )
            return
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                visit(
                    child,
                    function_depth=function_depth,
                    guard_depth=guard_depth,
                    type_checking_depth=type_checking_depth + 1,
                )
            for child in node.orelse:
                visit(
                    child,
                    function_depth=function_depth,
                    guard_depth=guard_depth,
                    type_checking_depth=type_checking_depth,
                )
            return
        if isinstance(node, ast.Try) and _try_catches_import_error(node):
            for child in node.body:
                visit(
                    child,
                    function_depth=function_depth,
                    guard_depth=guard_depth + 1,
                    type_checking_depth=type_checking_depth,
                )
            for child in node.handlers + node.orelse + node.finalbody:
                visit(
                    child,
                    function_depth=function_depth,
                    guard_depth=guard_depth,
                    type_checking_depth=type_checking_depth,
                )
            return
        for child in ast.iter_child_nodes(node):
            visit(
                child,
                function_depth=function_depth,
                guard_depth=guard_depth,
                type_checking_depth=type_checking_depth,
            )

    visit(tree, function_depth=0, guard_depth=0, type_checking_depth=0)
    return sites


def _is_type_checking(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    if isinstance(node, ast.Attribute):
        return node.attr == "TYPE_CHECKING"
    return False


def _try_catches_import_error(node: ast.Try) -> bool:
    for handler in node.handlers:
        if handler.type is None:
            return True
        if _exception_names(handler.type) & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
            return True
    return False


def _exception_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for elt in node.elts:
            names.update(_exception_names(elt))
        return names
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def _reachable_import_paths(
    project_root: Path,
    entry_file: str,
    layout: ProjectImportLayout,
) -> dict[str, str]:
    """Map each file loaded from *entry_file* to its import chain.

    An empty result means the caller did not name an entry file, so every
    audited file is treated as reachable.
    """
    if not entry_file:
        return {}
    entry_path = (project_root / entry_file).resolve()
    if not entry_path.is_file():
        return {}
    try:
        entry_rel = entry_path.relative_to(project_root).as_posix()
    except ValueError:
        return {}
    chains: dict[str, str] = {entry_rel: entry_rel}
    queue: list[Path] = [entry_path]
    while queue:
        current = queue.pop(0)
        current_rel = current.relative_to(project_root).as_posix()
        try:
            tree = ast.parse(current.read_text(encoding="utf-8"), filename=str(current))
        except (OSError, SyntaxError):
            continue
        sites = _import_sites(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            site = sites.get(id(node))
            if site is not None and site.guarded and not site.module_level:
                continue
            if isinstance(node, ast.Import):
                module_names = [alias.name for alias in node.names]
                level = 0
            else:
                module_names = [node.module or ""]
                level = node.level
                if level > 0 and not node.module:
                    module_names = [alias.name for alias in node.names]
            for module_name in module_names:
                resolved = _project_file_for_import(
                    current,
                    module_name,
                    level,
                    layout,
                    project_root,
                )
                if resolved is None:
                    continue
                rel = resolved.relative_to(project_root).as_posix()
                if rel in chains:
                    continue
                chains[rel] = f"{chains[current_rel]} -> {rel}"
                queue.append(resolved)
    return chains


def _project_file_for_import(
    file_path: Path,
    module_name: str,
    level: int,
    layout: ProjectImportLayout,
    project_root: Path,
) -> Path | None:
    if level > 0:
        absolute = resolve_import_from_module(file_path, module_name or None, level, layout=layout)
    else:
        absolute = module_name or None
    if not absolute:
        return None
    for base in layout.import_search_bases:
        resolved = resolve_import_at_base(base, absolute)
        if resolved is None:
            continue
        candidate = Path(resolved)
        if candidate.is_dir():
            init_file = candidate / "__init__.py"
            candidate = init_file if init_file.is_file() else candidate
        if not candidate.is_file():
            continue
        try:
            candidate.resolve().relative_to(project_root)
        except ValueError:
            continue
        return candidate.resolve()
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
