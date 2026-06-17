"""Quick-fix planning and application for diagnostics.

Import-related fixes here intentionally remain narrow, explicit quick fixes.
They are not the general organize-imports engine and they are not a substitute
for future structural cleanup in the trusted-semantics lane.
"""

from __future__ import annotations

from dataclasses import dataclass
import difflib
from pathlib import Path
import re

from app.core.models import ProjectMetadata
from app.intelligence.diagnostics_service import CodeDiagnostic
from app.intelligence.import_diagnostics import PY200_DETAIL_UNRESOLVED_MODULE
from app.persistence.atomic_write import atomic_write_text
from app.project.import_layout import (
    ProjectImportLayout,
    discover_canonical_project_modules,
    resolve_import_at_base,
    resolve_project_import_layout,
    suggest_missing_source_root,
)


@dataclass(frozen=True)
class QuickFix:
    """One safe quick-fix operation."""

    title: str
    file_path: str
    line_number: int
    action_kind: str
    target_path: str | None = None
    project_root: str | None = None
    match_text: str | None = None
    replacement_text: str | None = None
    expected_line_text: str | None = None


@dataclass(frozen=True)
class QuickFixApplyResult:
    """Outcome from applying one or more quick fixes."""

    changed_lines: int
    updated_metadata: ProjectMetadata | None = None


def plan_safe_fixes_for_file(
    file_path: str,
    diagnostics: list[CodeDiagnostic],
    *,
    project_root: str | None = None,
    project_metadata: ProjectMetadata | None = None,
) -> list[QuickFix]:
    """Return safe quick fixes for known diagnostics."""
    normalized_path = str(Path(file_path).expanduser().resolve())
    normalized_project_root = None if project_root is None else str(Path(project_root).expanduser().resolve())
    source_lines = _read_source_lines(Path(normalized_path))
    layout = None
    if normalized_project_root is not None:
        layout = resolve_project_import_layout(normalized_project_root, project_metadata)
    fixes: list[QuickFix] = []
    seen_keys: set[tuple[str, int, str, str, str]] = set()
    for diagnostic in diagnostics:
        if diagnostic.file_path != normalized_path:
            continue
        expected_line = _line_text_at(source_lines, diagnostic.line_number)
        if diagnostic.code in {"PY220", "PY221"}:
            # Keep unused/duplicate import removal line-scoped for now. Broader
            # import cleanup belongs to the structural semantics roadmap, not
            # this quick-fix lane.
            title_prefix = "Remove unused import" if diagnostic.code == "PY220" else "Remove duplicate import"
            fix = QuickFix(
                title=f"{title_prefix} at line {diagnostic.line_number}",
                file_path=normalized_path,
                line_number=diagnostic.line_number,
                action_kind="remove_line",
                project_root=normalized_project_root,
                expected_line_text=expected_line,
            )
        elif diagnostic.code == "PY200" and normalized_project_root is not None and layout is not None:
            fix = _plan_py200_quick_fix(
                diagnostic,
                layout=layout,
                normalized_path=normalized_path,
                normalized_project_root=normalized_project_root,
                expected_line=expected_line,
            )
            if fix is None:
                continue
        else:
            continue
        key = (
            fix.file_path,
            fix.line_number,
            fix.action_kind,
            fix.target_path or "",
            f"{fix.match_text or ''}->{fix.replacement_text or ''}",
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        fixes.append(fix)
    return sorted(fixes, key=lambda fix: fix.line_number)


def apply_quick_fixes(
    fixes: list[QuickFix],
    *,
    project_metadata: ProjectMetadata | None = None,
) -> QuickFixApplyResult:
    """Apply quick fixes and return affected line count plus optional metadata updates."""
    if not fixes:
        return QuickFixApplyResult(changed_lines=0)
    remove_line_fixes_by_file: dict[str, list[QuickFix]] = {}
    create_module_fixes: list[QuickFix] = []
    source_root_fixes: list[QuickFix] = []
    for fix in fixes:
        if fix.action_kind == "remove_line":
            remove_line_fixes_by_file.setdefault(fix.file_path, []).append(fix)
        elif fix.action_kind == "replace_import_module":
            remove_line_fixes_by_file.setdefault(fix.file_path, []).append(fix)
        elif fix.action_kind == "create_module_file":
            create_module_fixes.append(fix)
        elif fix.action_kind == "add_source_root":
            source_root_fixes.append(fix)

    snapshots: dict[Path, str | None] = {}
    snapshot_order: list[Path] = []
    created_directories: list[Path] = []
    updated_metadata: ProjectMetadata | None = None
    try:
        changed_operations = 0
        for file_path, file_fixes in remove_line_fixes_by_file.items():
            changed_operations += _apply_file_fixes(
                file_path,
                file_fixes,
                snapshots=snapshots,
                snapshot_order=snapshot_order,
            )

        seen_targets: set[str] = set()
        for fix in create_module_fixes:
            if not fix.target_path or fix.target_path in seen_targets:
                continue
            seen_targets.add(fix.target_path)
            changed_operations += _apply_create_module_fix(
                fix.target_path,
                fix.project_root,
                snapshots=snapshots,
                snapshot_order=snapshot_order,
                created_directories=created_directories,
            )

        seen_roots: set[str] = set()
        for fix in source_root_fixes:
            applied, metadata = _apply_source_root_fix(
                fix,
                metadata_if_absent=project_metadata,
            )
            if applied <= 0:
                continue
            changed_operations += applied
            if metadata is not None:
                updated_metadata = metadata
            source_root = str(fix.replacement_text or "").strip()
            if source_root:
                seen_roots.add(source_root)

        return QuickFixApplyResult(changed_lines=changed_operations, updated_metadata=updated_metadata)
    except OSError:
        _rollback_quick_fix_changes(snapshots, snapshot_order, created_directories)
        raise


def _apply_file_fixes(
    file_path: str,
    fixes: list[QuickFix],
    *,
    snapshots: dict[Path, str | None],
    snapshot_order: list[Path],
) -> int:
    path = Path(file_path).expanduser().resolve()
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    changed = 0
    for fix in sorted(fixes, key=lambda item: item.line_number, reverse=True):
        if fix.action_kind not in {"remove_line", "replace_import_module"}:
            continue
        line_index = fix.line_number - 1
        if line_index < 0 or line_index >= len(lines):
            continue
        if fix.expected_line_text is not None and lines[line_index].rstrip("\n\r") != fix.expected_line_text:
            continue
        if fix.action_kind == "remove_line":
            line = lines[line_index].lstrip()
            if not (line.startswith("import ") or line.startswith("from ")):
                continue
            lines.pop(line_index)
            changed += 1
            continue
        replacement = _replace_import_module_in_line(
            lines[line_index],
            match_text=fix.match_text,
            replacement_text=fix.replacement_text,
        )
        if replacement != lines[line_index]:
            lines[line_index] = replacement
            changed += 1
    if changed:
        _record_file_snapshot(path, snapshots=snapshots, snapshot_order=snapshot_order)
        atomic_write_text(path, "".join(lines))
    return changed


def _apply_create_module_fix(
    target_path: str,
    project_root: str | None,
    *,
    snapshots: dict[Path, str | None],
    snapshot_order: list[Path],
    created_directories: list[Path],
) -> int:
    target = Path(target_path).expanduser().resolve()
    if target.exists():
        return 0
    _ensure_directory_exists(target.parent, created_directories=created_directories)
    _ensure_package_inits(
        target.parent,
        stop_dir=None if project_root is None else Path(project_root).expanduser().resolve(),
        snapshots=snapshots,
        snapshot_order=snapshot_order,
        created_directories=created_directories,
    )
    _record_file_snapshot(target, snapshots=snapshots, snapshot_order=snapshot_order)
    atomic_write_text(target, '"""Auto-created module from quick-fix."""\n')
    return 1


def _ensure_package_inits(
    package_dir: Path,
    *,
    stop_dir: Path | None,
    snapshots: dict[Path, str | None],
    snapshot_order: list[Path],
    created_directories: list[Path],
) -> None:
    current = package_dir
    while current.exists():
        if stop_dir is not None and current == stop_dir:
            break
        init_path = current / "__init__.py"
        if not init_path.exists():
            _record_file_snapshot(init_path, snapshots=snapshots, snapshot_order=snapshot_order)
            atomic_write_text(init_path, "")
        parent = current.parent
        if parent == current:
            break
        if parent.name in {"", "/", "."}:
            break
        _ensure_directory_exists(parent, created_directories=created_directories)
        current = parent


def _plan_py200_quick_fix(
    diagnostic: CodeDiagnostic,
    *,
    layout: ProjectImportLayout,
    normalized_path: str,
    normalized_project_root: str,
    expected_line: str | None,
) -> QuickFix | None:
    unresolved_module = _unresolved_module_from_diagnostic(diagnostic)
    if unresolved_module is None:
        return None
    missing_root = suggest_missing_source_root(layout, unresolved_module)
    if missing_root is not None:
        return QuickFix(
            title=f"Add '{missing_root}' as a source root",
            file_path=normalized_path,
            line_number=diagnostic.line_number,
            action_kind="add_source_root",
            project_root=normalized_project_root,
            replacement_text=missing_root,
            expected_line_text=expected_line,
        )
    suggested_module = _suggest_module_replacement(layout, unresolved_module)
    if suggested_module is not None and suggested_module != unresolved_module:
        return QuickFix(
            title=f"Replace import '{unresolved_module}' with '{suggested_module}'",
            file_path=normalized_path,
            line_number=diagnostic.line_number,
            action_kind="replace_import_module",
            project_root=normalized_project_root,
            match_text=unresolved_module,
            replacement_text=suggested_module,
            expected_line_text=expected_line,
        )
    target_path = _module_target_path(layout, unresolved_module)
    return QuickFix(
        title=f"Create missing module '{unresolved_module}'",
        file_path=normalized_path,
        line_number=diagnostic.line_number,
        action_kind="create_module_file",
        target_path=target_path,
        project_root=normalized_project_root,
    )


def _unresolved_module_from_diagnostic(diagnostic: CodeDiagnostic) -> str | None:
    if diagnostic.detail is None:
        return None
    module_name = diagnostic.detail.get(PY200_DETAIL_UNRESOLVED_MODULE, "").strip()
    if not module_name:
        return None
    return module_name


def _apply_source_root_fix(
    fix: QuickFix,
    *,
    metadata_if_absent: ProjectMetadata | None,
) -> tuple[int, ProjectMetadata | None]:
    from app.bootstrap.paths import project_manifest_path
    from app.project.project_manifest import append_project_source_root

    if fix.project_root is None:
        return 0, None
    source_root = str(fix.replacement_text or "").strip()
    if not source_root:
        return 0, None
    manifest_path = project_manifest_path(fix.project_root)
    updated_metadata = append_project_source_root(
        manifest_path,
        source_root,
        metadata_if_absent=metadata_if_absent,
    )
    return 1, updated_metadata


def _module_target_path(layout: ProjectImportLayout, module_name: str) -> str:
    module_parts = [part for part in module_name.split(".") if part]
    for base in layout.import_search_bases:
        if base == layout.vendor_root:
            continue
        resolved = resolve_import_at_base(base, module_name)
        if resolved is not None and resolved.endswith(".py"):
            return resolved
        candidate = (base / Path(*module_parts)).with_suffix(".py")
        if candidate.parent.exists() or base == layout.project_root:
            return str(candidate.resolve())
    return str((layout.project_root / Path(*module_parts)).with_suffix(".py"))


def _suggest_module_replacement(layout: ProjectImportLayout, unresolved_module: str) -> str | None:
    available_modules = sorted(discover_canonical_project_modules(layout))
    if not available_modules:
        return None
    closest_matches = difflib.get_close_matches(unresolved_module, available_modules, n=1, cutoff=0.75)
    if not closest_matches:
        return None
    return closest_matches[0]


def _replace_import_module_in_line(
    line: str,
    *,
    match_text: str | None,
    replacement_text: str | None,
) -> str:
    if not match_text or not replacement_text:
        return line
    stripped = line.lstrip()
    if not (stripped.startswith("import ") or stripped.startswith("from ")):
        return line
    updated, count = re.subn(rf"\b{re.escape(match_text)}\b", replacement_text, line, count=1)
    if count == 0:
        return line
    return updated


def _read_source_lines(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return source.splitlines()


def _line_text_at(lines: list[str], line_number: int) -> str | None:
    line_index = line_number - 1
    if line_index < 0 or line_index >= len(lines):
        return None
    return lines[line_index]


def _record_file_snapshot(
    path: Path,
    *,
    snapshots: dict[Path, str | None],
    snapshot_order: list[Path],
) -> None:
    resolved = path.expanduser().resolve()
    if resolved in snapshots:
        return
    if resolved.exists():
        snapshots[resolved] = resolved.read_text(encoding="utf-8")
    else:
        snapshots[resolved] = None
    snapshot_order.append(resolved)


def _ensure_directory_exists(path: Path, *, created_directories: list[Path]) -> None:
    resolved = path.expanduser().resolve()
    if resolved.exists():
        return
    parent = resolved.parent
    if parent != resolved and not parent.exists():
        _ensure_directory_exists(parent, created_directories=created_directories)
    resolved.mkdir(exist_ok=True)
    created_directories.append(resolved)


def _rollback_quick_fix_changes(
    snapshots: dict[Path, str | None],
    snapshot_order: list[Path],
    created_directories: list[Path],
) -> None:
    for path in reversed(snapshot_order):
        original_content = snapshots.get(path)
        try:
            if original_content is None:
                if path.exists():
                    path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, original_content)
        except OSError:
            continue
    for directory in reversed(created_directories):
        try:
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            continue
