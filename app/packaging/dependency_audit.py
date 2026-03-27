"""Static dependency audit tailored to ChoreBoy packaging constraints."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from app.core import constants
from app.core.models import RuntimeIssue
from app.intelligence.diagnostics_service import _STDLIB_FALLBACK
from app.intelligence.import_resolver import resolve_project_import
from app.intelligence.runtime_import_probe import is_runtime_module_importable
from app.packaging.layout import should_exclude_relative_path
from app.packaging.models import DependencyAuditRecord, DependencyAuditReport
from app.support.runtime_explainer import HELP_TOPIC_PACKAGING

_COMPILED_EXTENSION_SUFFIXES = (".so", ".pyd", ".dll", ".dylib")
_SUBPROCESS_CALL_NAMES = {"Popen", "call", "check_call", "check_output", "run"}


def run_dependency_audit(
    *,
    project_root: str,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
) -> DependencyAuditReport:
    """Audit first-party project imports against project, vendor, and runtime availability."""
    root = Path(project_root).expanduser().resolve()
    records: list[DependencyAuditRecord] = []
    issues: list[RuntimeIssue] = []
    issue_keys: set[tuple[str, str, str]] = set()
    classification_counts: Counter[str] = Counter()

    for file_path in sorted(root.rglob("*.py")):
        rel_path = file_path.relative_to(root)
        if rel_path.parts and rel_path.parts[0] == "vendor":
            continue
        if constants.PROJECT_META_DIRNAME in rel_path.parts:
            continue
        if should_exclude_relative_path(rel_path):
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
                        _classify_relative_import(
                            module_name=relative_module,
                            level=node.level,
                            file_path=file_path,
                            line_number=line_number,
                            project_root=project_root,
                        )
                    )
                else:
                    for alias in node.names:
                        records.append(
                            _classify_relative_import(
                                module_name=alias.name,
                                level=node.level,
                                file_path=file_path,
                                line_number=line_number,
                                project_root=project_root,
                            )
                        )
            elif node.module:
                records.append(
                    _classify_import(
                        module_name=node.module,
                        file_path=file_path,
                        line_number=line_number,
                        project_root=project_root,
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
    known_runtime_modules: frozenset[str] | None,
    allow_runtime_import_probe: bool,
) -> DependencyAuditRecord:
    top_level = module_name.split(".")[0].strip()
    rel_file = file_path.relative_to(project_root).as_posix()

    if top_level in _STDLIB_FALLBACK:
        return DependencyAuditRecord(
            source_file=rel_file,
            line_number=line_number,
            module_name=module_name,
            classification="stdlib",
            detail="Python standard library import.",
        )

    resolution = resolve_project_import(
        str(project_root),
        module_name,
        known_runtime_modules=frozenset(),
        allow_runtime_import_probe=False,
    )
    if resolution.is_resolved and resolution.resolved_path:
        resolved_path = Path(resolution.resolved_path).resolve()
        classification = "vendored" if "vendor" in resolved_path.parts else "first_party"
        detail = (
            "Vendored dependency included under project vendor/."
            if classification == "vendored"
            else "Project-local module resolved from source tree."
        )
        if classification == "vendored" and _has_compiled_extension_candidate(project_root / "vendor", top_level):
            classification = "vendored_native"
            detail = "Vendored dependency appears to ship a compiled extension."
        return DependencyAuditRecord(
            source_file=rel_file,
            line_number=line_number,
            module_name=module_name,
            classification=classification,
            resolved_path=str(resolved_path),
            detail=detail,
        )

    if known_runtime_modules and top_level in known_runtime_modules:
        return DependencyAuditRecord(
            source_file=rel_file,
            line_number=line_number,
            module_name=module_name,
            classification="runtime",
            detail="Resolved from cached AppRun runtime module inventory.",
        )

    if allow_runtime_import_probe and top_level and is_runtime_module_importable(top_level):
        return DependencyAuditRecord(
            source_file=rel_file,
            line_number=line_number,
            module_name=module_name,
            classification="runtime",
            detail="Resolved by direct AppRun import probe.",
        )

    if _has_compiled_extension_candidate(project_root / "vendor", top_level):
        return DependencyAuditRecord(
            source_file=rel_file,
            line_number=line_number,
            module_name=module_name,
            classification="vendored_native",
            detail="Vendored native extension detected without an approved in-process loader declaration.",
        )

    return DependencyAuditRecord(
        source_file=rel_file,
        line_number=line_number,
        module_name=module_name,
        classification="missing",
        detail="Import is not resolved from project files, vendor/, or the AppRun runtime.",
    )


def _classify_relative_import(
    *,
    module_name: str,
    level: int,
    file_path: Path,
    line_number: int,
    project_root: Path,
) -> DependencyAuditRecord:
    rel_file = file_path.relative_to(project_root).as_posix()
    base_dir = file_path.parent
    for _index in range(max(level - 1, 0)):
        base_dir = base_dir.parent
    resolved_path = _resolve_module_candidates(base_dir, module_name)
    if resolved_path is not None:
        return DependencyAuditRecord(
            source_file=rel_file,
            line_number=line_number,
            module_name=f".{module_name}",
            classification="first_party_relative",
            resolved_path=str(resolved_path),
            detail="Relative import resolved inside the project source tree.",
        )
    return DependencyAuditRecord(
        source_file=rel_file,
        line_number=line_number,
        module_name=f".{module_name}",
        classification="missing_relative",
        detail="Relative import target could not be resolved from the current package path.",
    )


def _resolve_module_candidates(base_dir: Path, module_name: str) -> Path | None:
    module_parts = [part for part in module_name.split(".") if part.strip()]
    candidate = base_dir.joinpath(*module_parts) if module_parts else base_dir
    module_file = candidate.with_suffix(".py")
    package_init = candidate / "__init__.py"
    if module_file.exists():
        return module_file.resolve()
    if package_init.exists():
        return package_init.resolve()
    if candidate.is_dir():
        return candidate.resolve()
    return None


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


def _has_compiled_extension_candidate(base: Path, top_level: str) -> bool:
    if not top_level or not base.exists():
        return False
    for suffix in _COMPILED_EXTENSION_SUFFIXES:
        if any(base.glob(f"{top_level}*{suffix}")):
            return True
        if (base / top_level).exists() and any((base / top_level).glob(f"*{suffix}")):
            return True
    return False


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


def check_manifest_consistency(*, project_root: str) -> list[RuntimeIssue]:
    """Check that cbcs/dependencies.json entries are consistent with vendor/ state."""
    from app.project.dependency_manifest import STATUS_ACTIVE, load_dependency_manifest

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
