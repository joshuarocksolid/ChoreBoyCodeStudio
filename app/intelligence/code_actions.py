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


def plan_safe_fixes_for_file(file_path: str, diagnostics: list[CodeDiagnostic]) -> list[QuickFix]:
    """Return safe quick fixes for known diagnostics."""
    normalized_path = str(Path(file_path).expanduser().resolve())
    fixes: list[QuickFix] = []
    seen_keys: set[tuple[str, int, str]] = set()
    for diagnostic in diagnostics:
        if diagnostic.file_path != normalized_path:
            continue
        if diagnostic.code != "PY220":
            continue
        fix = QuickFix(
            title=f"Remove unused import at line {diagnostic.line_number}",
            file_path=normalized_path,
            line_number=diagnostic.line_number,
            action_kind="remove_line",
        )
        key = (fix.file_path, fix.line_number, fix.action_kind)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        fixes.append(fix)
    return sorted(fixes, key=lambda fix: fix.line_number)


def apply_quick_fixes(fixes: list[QuickFix]) -> int:
    """Apply quick fixes and return number of affected lines."""
    if not fixes:
        return 0
    fixes_by_file: dict[str, list[QuickFix]] = {}
    for fix in fixes:
        fixes_by_file.setdefault(fix.file_path, []).append(fix)

    changed_lines = 0
    for file_path, file_fixes in fixes_by_file.items():
        changed_lines += _apply_file_fixes(file_path, file_fixes)
    return changed_lines


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
