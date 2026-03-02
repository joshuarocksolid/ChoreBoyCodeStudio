"""Quick-fix planning and application for diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.diagnostics_service import CodeDiagnostic


@dataclass(frozen=True)
class QuickFix:
    """One safe quick-fix operation."""

    title: str
    file_path: str
    line_number: int
    action_kind: str
    target_path: str | None = None
    project_root: str | None = None


def plan_safe_fixes_for_file(
    file_path: str,
    diagnostics: list[CodeDiagnostic],
    *,
    project_root: str | None = None,
) -> list[QuickFix]:
    """Return safe quick fixes for known diagnostics."""
    normalized_path = str(Path(file_path).expanduser().resolve())
    normalized_project_root = None if project_root is None else str(Path(project_root).expanduser().resolve())
    fixes: list[QuickFix] = []
    seen_keys: set[tuple[str, int, str, str | None]] = set()
    for diagnostic in diagnostics:
        if diagnostic.file_path != normalized_path:
            continue
        if diagnostic.code == "PY220":
            fix = QuickFix(
                title=f"Remove unused import at line {diagnostic.line_number}",
                file_path=normalized_path,
                line_number=diagnostic.line_number,
                action_kind="remove_line",
                project_root=normalized_project_root,
            )
        elif diagnostic.code == "PY200" and normalized_project_root is not None:
            unresolved_module = _extract_unresolved_module_name(diagnostic.message)
            if unresolved_module is None:
                continue
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
        key = (fix.file_path, fix.line_number, fix.action_kind, fix.target_path or "")
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
        elif fix.action_kind == "create_module_file":
            create_module_fixes.append(fix)

    changed_operations = 0
    for file_path, file_fixes in remove_line_fixes_by_file.items():
        changed_operations += _apply_file_fixes(file_path, file_fixes)

    seen_targets: set[str] = set()
    for fix in create_module_fixes:
        if not fix.target_path or fix.target_path in seen_targets:
            continue
        seen_targets.add(fix.target_path)
        changed_operations += _apply_create_module_fix(fix.target_path, fix.project_root)
    return changed_operations


def _apply_file_fixes(file_path: str, fixes: list[QuickFix]) -> int:
    path = Path(file_path).expanduser().resolve()
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    changed = 0
    for fix in sorted(fixes, key=lambda item: item.line_number, reverse=True):
        if fix.action_kind != "remove_line":
            continue
        line_index = fix.line_number - 1
        if line_index < 0 or line_index >= len(lines):
            continue
        line = lines[line_index].lstrip()
        if not (line.startswith("import ") or line.startswith("from ")):
            continue
        lines.pop(line_index)
        changed += 1
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def _apply_create_module_fix(target_path: str, project_root: str | None) -> int:
    target = Path(target_path).expanduser().resolve()
    if target.exists():
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    _ensure_package_inits(target.parent, stop_dir=None if project_root is None else Path(project_root).expanduser().resolve())
    target.write_text('"""Auto-created module from quick-fix."""\n', encoding="utf-8")
    return 1


def _ensure_package_inits(package_dir: Path, *, stop_dir: Path | None) -> None:
    current = package_dir
    while current.exists():
        if stop_dir is not None and current == stop_dir:
            break
        init_path = current / "__init__.py"
        if not init_path.exists():
            init_path.write_text("", encoding="utf-8")
        parent = current.parent
        if parent == current:
            break
        if parent.name in {"", "/", "."}:
            break
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
