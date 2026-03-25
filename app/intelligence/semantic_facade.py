"""Facade over trusted semantic engines and degradation policy."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.bootstrap.paths import PathInput
from app.intelligence.completion_models import CompletionItem
from app.intelligence.jedi_engine import JediEngine
from app.intelligence.refactor_engine import RopeRefactorEngine
from app.intelligence.semantic_models import (
    SemanticDefinitionResult,
    SemanticHoverResult,
    SemanticReferenceResult,
    SemanticRenamePlan,
    SemanticSignatureResult,
    unsupported_metadata,
)


class SemanticFacade:
    """Coordinates read-only semantics and trusted refactor planning."""

    def __init__(self, *, cache_db_path: str, state_root: Optional[PathInput] = None) -> None:
        self._cache_db_path = str(Path(cache_db_path).expanduser().resolve())
        self._state_root = state_root
        self._jedi_engine = JediEngine(state_root=state_root)
        self._refactor_engine = RopeRefactorEngine()

    @property
    def cache_db_path(self) -> str:
        return self._cache_db_path

    def lookup_definition(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticDefinitionResult:
        result = self._jedi_engine.lookup_definition(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        if result.found:
            return result
        return SemanticDefinitionResult(
            symbol_name=result.symbol_name,
            locations=[],
            metadata=unsupported_metadata(
                "jedi",
                latency_ms=result.metadata.latency_ms,
                unsupported_reason="dynamic_or_unresolved",
            ),
        )

    def find_references(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticReferenceResult:
        result = self._jedi_engine.find_references(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        if result.found or not result.symbol_name:
            return result
        return SemanticReferenceResult(
            symbol_name=result.symbol_name,
            hits=[],
            metadata=unsupported_metadata(
                "jedi",
                latency_ms=result.metadata.latency_ms,
                unsupported_reason="dynamic_or_unresolved",
            ),
        )

    def resolve_hover_info(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticHoverResult | None:
        result = self._jedi_engine.resolve_hover_info(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        if result is not None:
            return result
        symbol_name = _extract_symbol_under_cursor(source_text, cursor_position)
        if not symbol_name:
            return None
        return SemanticHoverResult(
            symbol_name=symbol_name,
            symbol_kind="symbol",
            file_path=None,
            line_number=None,
            doc_summary="",
            metadata=unsupported_metadata("jedi", unsupported_reason="dynamic_or_unresolved"),
        )

    def resolve_signature_help(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticSignatureResult | None:
        result = self._jedi_engine.resolve_signature_help(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        if result is not None:
            return result
        return None

    def complete(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        trigger_is_manual: bool,
        min_prefix_chars: int,
        max_results: int,
    ) -> list[CompletionItem]:
        prefix = _extract_symbol_under_cursor(source_text, cursor_position)
        if not trigger_is_manual and len(prefix) < max(1, int(min_prefix_chars)):
            return []
        return self._jedi_engine.complete(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
            max_results=max_results,
        )

    def plan_rename(
        self,
        *,
        project_root: str,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        new_symbol: str,
    ) -> SemanticRenamePlan | None:
        old_symbol = _extract_symbol_under_cursor(source_text, cursor_position)
        if not old_symbol or old_symbol == new_symbol:
            return None
        if not new_symbol.isidentifier():
            return None

        references = self.find_references(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        if not references.found:
            raise ValueError("No semantic references found; symbol may be unresolved or dynamic.")

        plan = self._refactor_engine.plan_rename(
            project_root=project_root,
            current_file_path=current_file_path,
            cursor_position=cursor_position,
            new_symbol=new_symbol,
            reference_hits=references.hits,
        )
        if plan is None:
            raise ValueError("Semantic rename could not prove a safe rename plan.")
        if plan.old_symbol == old_symbol:
            return plan
        return SemanticRenamePlan(
            old_symbol=old_symbol,
            new_symbol=plan.new_symbol,
            hits=plan.hits,
            preview_patches=plan.preview_patches,
            metadata=plan.metadata,
        )

    def apply_rename(self, plan: SemanticRenamePlan):
        return self._refactor_engine.apply_rename(plan)


def _extract_symbol_under_cursor(source_text: str, cursor_position: int) -> str:
    safe_cursor = max(0, min(cursor_position, len(source_text)))
    left = safe_cursor
    while left > 0 and _is_symbol_character(source_text[left - 1]):
        left -= 1
    right = safe_cursor
    while right < len(source_text) and _is_symbol_character(source_text[right]):
        right += 1
    symbol = source_text[left:right].strip()
    return symbol if symbol.isidentifier() else ""


def _is_symbol_character(character: str) -> bool:
    return character.isalnum() or character == "_"
