"""Rename-symbol refactor planning and apply helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.intelligence.reference_service import ReferenceHit, extract_symbol_under_cursor, find_references


@dataclass(frozen=True)
class RenamePlan:
    """Planned rename payload for one symbol operation."""

    old_symbol: str
    new_symbol: str
    hits: list[ReferenceHit]

    @property
    def touched_files(self) -> list[str]:
        return sorted({hit.file_path for hit in self.hits})


@dataclass(frozen=True)
class RenameApplyResult:
    """Apply result metadata for rename operation."""

    changed_files: list[str]
    changed_occurrences: int


def plan_rename_symbol(
    *,
    project_root: str,
    current_file_path: str,
    source_text: str,
    cursor_position: int,
    new_symbol: str,
) -> RenamePlan | None:
    """Build rename plan for symbol under cursor."""
    old_symbol = extract_symbol_under_cursor(source_text, cursor_position)
    if not old_symbol or old_symbol == new_symbol:
        return None
    if not new_symbol.isidentifier():
        return None

    references = find_references(
        project_root=project_root,
        current_file_path=current_file_path,
        source_text=source_text,
        cursor_position=cursor_position,
    )
    if not references.hits:
        return None
    return RenamePlan(old_symbol=old_symbol, new_symbol=new_symbol, hits=references.hits)


def apply_rename_plan(plan: RenamePlan) -> RenameApplyResult:
    """Apply planned rename edits across files with rollback on failure."""
    originals: dict[str, str] = {}
    updated_files: list[str] = []
    updates_by_file: dict[str, list[ReferenceHit]] = {}
    for hit in plan.hits:
        updates_by_file.setdefault(hit.file_path, []).append(hit)

    try:
        for file_path, hits in updates_by_file.items():
            path = Path(file_path).expanduser().resolve()
            source = path.read_text(encoding="utf-8")
            originals[file_path] = source
            updated_source = _apply_hits_to_source(source, hits=hits, old_symbol=plan.old_symbol, new_symbol=plan.new_symbol)
            if updated_source == source:
                continue
            path.write_text(updated_source, encoding="utf-8")
            updated_files.append(file_path)
    except OSError:
        for file_path, payload in originals.items():
            Path(file_path).write_text(payload, encoding="utf-8")
        raise

    return RenameApplyResult(changed_files=sorted(updated_files), changed_occurrences=len(plan.hits))


def _apply_hits_to_source(source: str, *, hits: list[ReferenceHit], old_symbol: str, new_symbol: str) -> str:
    lines = source.splitlines(keepends=True)
    sorted_hits = sorted(hits, key=lambda hit: (hit.line_number, hit.column_number), reverse=True)
    for hit in sorted_hits:
        line_index = hit.line_number - 1
        if line_index < 0 or line_index >= len(lines):
            continue
        line = lines[line_index]
        start = hit.column_number
        end = start + len(old_symbol)
        if start < 0 or end > len(line):
            continue
        if line[start:end] != old_symbol:
            continue
        lines[line_index] = f"{line[:start]}{new_symbol}{line[end:]}"
    return "".join(lines)
