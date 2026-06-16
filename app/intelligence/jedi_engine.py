"""Jedi-backed semantic read-only operations for Python."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from app.bootstrap.paths import PathInput
from app.intelligence.completion_models import CompletionItem
from app.intelligence.jedi_definitions import (
    find_references as find_references_impl,
    lookup_definition as lookup_definition_impl,
    resolve_hover_info as resolve_hover_info_impl,
    resolve_signature_help as resolve_signature_help_impl,
)
from app.intelligence.jedi_mappers import (
    completion_detail,
    completion_documentation,
    completion_kind_from_name,
    completion_signature,
)
from app.intelligence.jedi_project_cache import invalidate_project_cache as invalidate_project_cache_impl
from app.intelligence.jedi_runtime import initialize_jedi_runtime
from app.intelligence.jedi_script_factory import create_script
from app.intelligence.semantic_models import SemanticDefinitionResult, SemanticHoverResult, SemanticReferenceResult, SemanticSignatureResult
from app.intelligence.semantic_utils import offset_to_line_column


class JediEngine:
    """Read-only semantic engine powered by vendored Jedi."""

    def __init__(self, *, state_root: Optional[PathInput] = None) -> None:
        self._state_root = state_root
        self._lock = threading.RLock()
        self._project_cache: dict[tuple[str, tuple[str, ...]], Any] = {}

    def is_available(self) -> bool:
        """Return whether the Jedi runtime is importable."""
        return initialize_jedi_runtime(self._state_root).is_available

    def lookup_definition(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticDefinitionResult:
        return lookup_definition_impl(**self._query_context(), project_root=project_root, current_file_path=current_file_path, source_text=source_text, cursor_position=cursor_position)

    def find_references(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticReferenceResult:
        return find_references_impl(**self._query_context(), project_root=project_root, current_file_path=current_file_path, source_text=source_text, cursor_position=cursor_position)

    def resolve_hover_info(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticHoverResult | None:
        return resolve_hover_info_impl(**self._query_context(), project_root=project_root, current_file_path=current_file_path, source_text=source_text, cursor_position=cursor_position)

    def resolve_signature_help(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticSignatureResult | None:
        return resolve_signature_help_impl(**self._query_context(), project_root=project_root, current_file_path=current_file_path, source_text=source_text, cursor_position=cursor_position)

    def complete(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        max_results: int,
    ) -> list[CompletionItem]:
        completions = self._completions_at_cursor(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        items: list[CompletionItem] = []
        for completion in completions[: max(1, int(max_results))]:
            completion_name = str(getattr(completion, "name", ""))
            if not completion_name:
                continue
            symbol_kind = str(getattr(completion, "type", "symbol"))
            module_path = getattr(completion, "module_path", None)
            items.append(
                CompletionItem(
                    label=completion_name,
                    insert_text=completion_name,
                    kind=completion_kind_from_name(completion),
                    detail=completion_detail(completion),
                    source_file_path=None if module_path is None else str(Path(module_path).resolve()),
                    engine="jedi",
                    source="semantic",
                    confidence="exact",
                    semantic_kind=symbol_kind,
                    resolve_provider="jedi",
                    resolvable_fields=("documentation", "signature", "return_type", "detail"),
                )
            )
        return items

    def resolve_completion_item(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        item: CompletionItem,
        max_results: int = 150,
    ) -> CompletionItem:
        """Enrich one selected completion item with expensive Jedi metadata."""
        if item.source != "semantic":
            return item
        completions = self._completions_at_cursor(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
        for completion in completions[: max(1, int(max_results))]:
            completion_name = str(getattr(completion, "name", ""))
            if completion_name != item.label:
                continue
            module_path = getattr(completion, "module_path", None)
            return CompletionItem(
                label=item.label,
                insert_text=item.insert_text,
                kind=item.kind,
                detail=completion_detail(completion),
                documentation=completion_documentation(completion),
                signature=completion_signature(completion),
                return_type=item.return_type,
                source_file_path=None if module_path is None else str(Path(module_path).resolve()),
                engine=item.engine,
                source=item.source,
                confidence=item.confidence,
                semantic_kind=item.semantic_kind,
                replacement_start=item.replacement_start,
                replacement_end=item.replacement_end,
                trigger_kind=item.trigger_kind,
                trigger_character=item.trigger_character,
                side_effect_risk=item.side_effect_risk,
                item_id=item.item_id,
                context_fingerprint=item.context_fingerprint,
                resolve_provider=item.resolve_provider,
                resolvable_fields=item.resolvable_fields,
            )
        return item

    def invalidate_project_cache(self, project_root: str | None = None) -> None:
        """Clear cached Jedi project(s) so the next query rebuilds paths."""
        invalidate_project_cache_impl(self._project_cache, project_root)

    def _query_context(self) -> dict[str, Any]:
        return {
            "state_root": self._state_root,
            "project_cache": self._project_cache,
            "lock": self._lock,
        }

    def _completions_at_cursor(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> list[Any]:
        with self._lock:
            script = create_script(
                state_root=self._state_root,
                project_cache=self._project_cache,
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
            )
            line_number, column_number = offset_to_line_column(source_text, cursor_position)
            return list(script.complete(line_number, column_number))
