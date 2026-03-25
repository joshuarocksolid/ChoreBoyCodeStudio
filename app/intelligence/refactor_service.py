"""Rename-symbol refactor planning and apply helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core import constants
from app.intelligence.reference_service import ReferenceHit, extract_symbol_under_cursor
from app.intelligence.semantic_facade import SemanticFacade
from app.intelligence.semantic_models import SemanticOperationMetadata, SemanticRenamePatch

_FACADE_BY_PROJECT_ROOT: dict[str, SemanticFacade] = {}


@dataclass(frozen=True)
class RenamePlan:
    """Planned rename payload for one symbol operation."""

    old_symbol: str
    new_symbol: str
    hits: list[ReferenceHit]
    preview_patches: list[SemanticRenamePatch]
    metadata: SemanticOperationMetadata | None = None

    @property
    def touched_files(self) -> list[str]:
        if self.preview_patches:
            return [patch.file_path for patch in self.preview_patches]
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

    semantic_plan = _facade(project_root).plan_rename(
        project_root=project_root,
        current_file_path=current_file_path,
        source_text=source_text,
        cursor_position=cursor_position,
        new_symbol=new_symbol,
    )
    if semantic_plan is None:
        return None
    return RenamePlan(
        old_symbol=semantic_plan.old_symbol or old_symbol,
        new_symbol=semantic_plan.new_symbol,
        hits=[
            ReferenceHit(
                symbol_name=hit.symbol_name,
                file_path=hit.file_path,
                line_number=hit.line_number,
                column_number=hit.column_number,
                line_text=hit.line_text,
                is_definition=hit.is_definition,
            )
            for hit in semantic_plan.hits
        ],
        preview_patches=list(semantic_plan.preview_patches),
        metadata=semantic_plan.metadata,
    )


def apply_rename_plan(plan: RenamePlan) -> RenameApplyResult:
    """Apply planned rename edits across files with rollback on failure."""
    originals: dict[str, str] = {}
    updated_files: list[str] = []
    try:
        for patch in plan.preview_patches:
            path = Path(patch.file_path).expanduser().resolve()
            originals[patch.file_path] = path.read_text(encoding="utf-8")
            path.write_text(patch.updated_content, encoding="utf-8")
            updated_files.append(patch.file_path)
    except OSError:
        for file_path, payload in originals.items():
            Path(file_path).write_text(payload, encoding="utf-8")
        raise

    return RenameApplyResult(changed_files=sorted(updated_files), changed_occurrences=len(plan.hits))


def _facade(project_root: str) -> SemanticFacade:
    normalized_root = str(Path(project_root).expanduser().resolve())
    cached = _FACADE_BY_PROJECT_ROOT.get(normalized_root)
    if cached is None:
        cache_db_path = str(
            (
                Path(normalized_root)
                / constants.PROJECT_META_DIRNAME
                / constants.PROJECT_CACHE_DIRNAME
                / "semantic.sqlite3"
            ).resolve()
        )
        cached = SemanticFacade(cache_db_path=cache_db_path)
        _FACADE_BY_PROJECT_ROOT[normalized_root] = cached
    return cached
