"""Rope-backed semantic rename planning and apply helpers."""
from __future__ import annotations

import difflib
from pathlib import Path
import time
from typing import Any, Optional, cast

from app.persistence.atomic_write import atomic_write_text
from app.intelligence.refactor_runtime import initialize_refactor_runtime
from app.intelligence.semantic_models import (
    SemanticOperationMetadata,
    SemanticReferenceHit,
    SemanticRenameApplyResult,
    SemanticRenamePatch,
    SemanticRenamePlan,
    exact_metadata,
)
from app.intelligence.semantic_utils import changed_line_numbers, relative_display_path


class RopeRefactorEngine:
    """Semantic refactor engine powered by vendored Rope."""

    def plan_rename(
        self,
        *,
        project_root: str,
        current_file_path: str,
        cursor_position: int,
        new_symbol: str,
        reference_hits: Optional[list[SemanticReferenceHit]] = None,
    ) -> SemanticRenamePlan | None:
        started_at = time.perf_counter()
        status = initialize_refactor_runtime()
        if not status.is_available:
            raise RuntimeError(status.message)

        from rope.base.project import Project
        from rope.refactor.rename import Rename

        root = Path(project_root).expanduser().resolve()
        current_path = Path(current_file_path).expanduser().resolve()
        try:
            resource_path = current_path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"Rename target must be inside project root: {current_file_path}") from exc

        project = Project(str(root), ropefolder=cast(Any, None))
        try:
            resource = project.get_file(resource_path)
            rename = Rename(project, resource, cursor_position)
            changes = rename.get_changes(new_symbol)
            preview_patches: list[SemanticRenamePatch] = []
            for change in getattr(changes, "changes", []):
                resource_obj = getattr(change, "resource", None)
                new_contents = getattr(change, "new_contents", None)
                if resource_obj is None or new_contents is None:
                    continue
                absolute_path = str((root / resource_obj.path).resolve())
                before_text = Path(absolute_path).read_text(encoding="utf-8")
                after_text = str(new_contents)
                if before_text == after_text:
                    continue
                relative_path = relative_display_path(str(root), absolute_path)
                diff_text = "\n".join(
                    difflib.unified_diff(
                        before_text.splitlines(),
                        after_text.splitlines(),
                        fromfile=relative_path,
                        tofile=relative_path,
                        lineterm="",
                    )
                )
                preview_patches.append(
                    SemanticRenamePatch(
                        file_path=absolute_path,
                        relative_path=relative_path,
                        diff_text=diff_text,
                        updated_content=after_text,
                        changed_line_numbers=changed_line_numbers(before_text, after_text),
                    )
                )
        finally:
            project.close()

        if not preview_patches:
            return None

        metadata = exact_metadata("rope", latency_ms=_elapsed_ms(started_at), source="semantic")
        return SemanticRenamePlan(
            old_symbol=_extract_old_symbol(reference_hits),
            new_symbol=new_symbol,
            hits=list(reference_hits or []),
            preview_patches=preview_patches,
            metadata=metadata,
        )

    def apply_rename(self, plan: SemanticRenamePlan) -> SemanticRenameApplyResult:
        """Apply patch contents with rollback on failure."""
        originals: dict[str, str] = {}
        updated_files: list[str] = []
        try:
            for patch in plan.preview_patches:
                target = Path(patch.file_path).expanduser().resolve()
                originals[patch.file_path] = target.read_text(encoding="utf-8")
                atomic_write_text(target, patch.updated_content)
                updated_files.append(patch.file_path)
        except OSError:
            for file_path, payload in originals.items():
                atomic_write_text(file_path, payload)
            raise
        return SemanticRenameApplyResult(
            changed_files=sorted(updated_files),
            changed_occurrences=len(plan.hits) if plan.hits else len(updated_files),
        )


def _extract_old_symbol(reference_hits: Optional[list[SemanticReferenceHit]]) -> str:
    if not reference_hits:
        return ""
    return reference_hits[0].symbol_name


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000.0
