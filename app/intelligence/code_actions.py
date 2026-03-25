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

from app.core import constants
from app.intelligence.diagnostics_service import CodeDiagnostic
from app.persistence.atomic_write import atomic_write_text


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


def plan_safe_fixes_for_file(
    file_path: str,
    diagnostics: list[CodeDiagnostic],
    *,
    project_root: str | None = None,
) -> list[QuickFix]:
    """Return safe quick fixes for known diagnostics."""
    normalized_path = str(Path(file_path).expanduser().resolve())
    normalized_project_root = None if project_root is None else str(Path(project_root).expanduser().resolve())
    source_lines = _read_source_lines(Path(normalized_path))
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
        elif diagnostic.code == "PY200" and normalized_project_root is not None:
            unresolved_module = _extract_unresolved_module_name(diagnostic.message)
            if unresolved_module is None:
                continue
            suggested_module = _suggest_module_replacement(normalized_project_root, unresolved_module)
            if suggested_module is not None and suggested_module != unresolved_module:
                fix = QuickFix(
                    title=f"Replace import '{unresolved_module}' with '{suggested_module}'",
                    file_path=normalized_path,
                    line_number=diagnostic.line_number,
                    action_kind="replace_import_module",
                    project_root=normalized_project_root,
                    match_text=unresolved_module,
                    replacement_text=suggested_module,
                    expected_line_text=expected_line,
                )
            else:
                target_path = _module_target_path(normalized_project_root, unresolved_module)
                fix = QuickFix(
                    title=f"Create missing module '{unresolved_module}'",
                    file_path=normalized_path,
                    line_number=diagnostic.line_number,
                    action_kind="create_module_file",
                    target_path=target_path,
                    project_root=normalized_project_root,
                )
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


def apply_quick_fixes(fixes: list[QuickFix]) -> int:
    """Apply quick fixes and return number of affected lines."""
    if not fixes:
        return 0
    remove_line_fixes_by_file: dict[str, list[QuickFix]] = {}
    create_module_fixes: list[QuickFix] = []
    for fix in fixes:
        if fix.action_kind == "remove_line":
            remove_line_fixes_by_file.setdefault(fix.file_path, []).append(fix)
        elif fix.action_kind == "replace_import_module":
            remove_line_fixes_by_file.setdefault(fix.file_path, []).append(fix)
        elif fix.action_kind == "create_module_file":
            create_module_fixes.append(fix)

    snapshots: dict[Path, str | None] = {}
    snapshot_order: list[Path] = []
    created_directories: list[Path] = []
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
        return changed_operations
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


def _extract_unresolved_module_name(message: str) -> str | None:
    prefix = "Unresolved import:"
    if not message.startswith(prefix):
        return None
    module_name = message[len(prefix) :].strip()
    if not module_name:
        return None
    return module_name


def _module_target_path(project_root: str, module_name: str) -> str:
    module_parts = [part for part in module_name.split(".") if part]
    path = Path(project_root).expanduser().resolve()
    return str((path / Path(*module_parts)).with_suffix(".py"))


def _suggest_module_replacement(project_root: str, unresolved_module: str) -> str | None:
    available_modules = sorted(_discover_project_modules(project_root))
    if not available_modules:
        return None
    closest_matches = difflib.get_close_matches(unresolved_module, available_modules, n=1, cutoff=0.75)
    if not closest_matches:
        return None
    return closest_matches[0]


def _discover_project_modules(project_root: str) -> set[str]:
    root = Path(project_root).expanduser().resolve()
    discovered: set[str] = set()
    for file_path in root.rglob("*.py"):
        if constants.PROJECT_META_DIRNAME in file_path.parts:
            continue
        relative = file_path.relative_to(root)
        if relative.name == "__init__.py":
            module_name = ".".join(relative.parts[:-1])
        else:
            module_name = ".".join(relative.with_suffix("").parts)
        if module_name:
            discovered.add(module_name)
    return discovered


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
