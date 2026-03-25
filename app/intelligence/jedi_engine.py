"""Jedi-backed semantic read-only operations for Python."""
from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any, Optional

from app.bootstrap.paths import PathInput
from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.intelligence.jedi_runtime import initialize_jedi_runtime
from app.intelligence.semantic_models import (
    SemanticDefinitionResult,
    SemanticHoverResult,
    SemanticLocation,
    SemanticReferenceHit,
    SemanticReferenceResult,
    SemanticSignatureResult,
    exact_metadata,
)
from app.intelligence.semantic_utils import first_doc_line, line_text_at, offset_to_line_column


class JediEngine:
    """Read-only semantic engine powered by vendored Jedi."""

    def __init__(self, *, state_root: Optional[PathInput] = None) -> None:
        self._state_root = state_root
        self._lock = threading.RLock()
        self._project_cache: dict[str, Any] = {}

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
        started_at = time.perf_counter()
        symbol_name = _extract_symbol_under_cursor(source_text, cursor_position)
        if not symbol_name:
            return SemanticDefinitionResult(symbol_name="", locations=[], metadata=exact_metadata("jedi"))

        with self._lock:
            script = self._script(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
            )
            line_number, column_number = offset_to_line_column(source_text, cursor_position)
            names = self._ordered_definition_names(
                script=script,
                line_number=line_number,
                column_number=column_number,
                current_file_path=current_file_path,
            )

        metadata = exact_metadata("jedi", latency_ms=_elapsed_ms(started_at))
        locations = [
            _location_from_name(name)
            for name in names
            if getattr(name, "module_path", None) is not None
        ]
        return SemanticDefinitionResult(symbol_name=symbol_name, locations=locations, metadata=metadata)

    def find_references(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticReferenceResult:
        started_at = time.perf_counter()
        symbol_name = _extract_symbol_under_cursor(source_text, cursor_position)
        if not symbol_name:
            return SemanticReferenceResult(symbol_name="", hits=[], metadata=exact_metadata("jedi"))

        with self._lock:
            script = self._script(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
            )
            line_number, column_number = offset_to_line_column(source_text, cursor_position)
            names = list(script.get_references(line_number, column_number))

        hits_by_key: dict[tuple[str, int, int], SemanticReferenceHit] = {}
        file_source_by_path: dict[str, str] = {}
        for name in names:
            module_path = getattr(name, "module_path", None)
            if module_path is None:
                continue
            resolved_file_path = str(Path(module_path).resolve())
            resolved_line_number = int(getattr(name, "line", 0) or 0)
            resolved_column_number = int(getattr(name, "column", 0) or 0)
            if resolved_line_number <= 0:
                continue
            if resolved_file_path == str(Path(current_file_path).expanduser().resolve()):
                line_text = line_text_at(source_text, resolved_line_number)
            else:
                file_source = file_source_by_path.get(resolved_file_path)
                if file_source is None:
                    try:
                        file_source = Path(resolved_file_path).read_text(encoding="utf-8")
                    except OSError:
                        file_source = ""
                    file_source_by_path[resolved_file_path] = file_source
                line_text = line_text_at(file_source, resolved_line_number)
            key = (resolved_file_path, resolved_line_number, resolved_column_number)
            hits_by_key[key] = SemanticReferenceHit(
                symbol_name=symbol_name,
                file_path=resolved_file_path,
                line_number=resolved_line_number,
                column_number=resolved_column_number,
                line_text=line_text.strip(),
                is_definition=bool(name.is_definition()),
            )

        hits = sorted(
            hits_by_key.values(),
            key=lambda item: (item.file_path, item.line_number, item.column_number),
        )
        metadata = exact_metadata("jedi", latency_ms=_elapsed_ms(started_at))
        return SemanticReferenceResult(symbol_name=symbol_name, hits=hits, metadata=metadata)

    def resolve_hover_info(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticHoverResult | None:
        started_at = time.perf_counter()
        symbol_name = _extract_symbol_under_cursor(source_text, cursor_position)
        if not symbol_name:
            return None

        with self._lock:
            script = self._script(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
            )
            line_number, column_number = offset_to_line_column(source_text, cursor_position)
            names = self._ordered_definition_names(
                script=script,
                line_number=line_number,
                column_number=column_number,
                current_file_path=current_file_path,
            )

        if not names:
            return None
        first_name = names[0]
        module_path = getattr(first_name, "module_path", None)
        resolved_file_path = None if module_path is None else str(Path(module_path).resolve())
        resolved_line_number = getattr(first_name, "line", None)
        doc_text = _name_docstring(first_name)
        return SemanticHoverResult(
            symbol_name=str(getattr(first_name, "name", symbol_name)),
            symbol_kind=str(getattr(first_name, "type", "symbol")),
            file_path=resolved_file_path,
            line_number=None if resolved_line_number is None else int(resolved_line_number),
            doc_summary=_doc_summary_from_jedi_payload(doc_text),
            metadata=exact_metadata("jedi", latency_ms=_elapsed_ms(started_at)),
        )

    def resolve_signature_help(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
    ) -> SemanticSignatureResult | None:
        started_at = time.perf_counter()
        with self._lock:
            script = self._script(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
            )
            line_number, column_number = offset_to_line_column(source_text, cursor_position)
            signatures = list(script.get_signatures(line_number, column_number))

        if not signatures:
            return None
        signature = signatures[0]
        return SemanticSignatureResult(
            callable_name=str(getattr(signature, "name", "")),
            signature_text=str(signature.to_string()),
            argument_index=int(getattr(signature, "index", 0)),
            doc_summary=_doc_summary_from_jedi_payload(signature.docstring()),
            metadata=exact_metadata("jedi", latency_ms=_elapsed_ms(started_at)),
        )

    def complete(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
        cursor_position: int,
        max_results: int,
    ) -> list[CompletionItem]:
        with self._lock:
            script = self._script(
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
            )
            line_number, column_number = offset_to_line_column(source_text, cursor_position)
            completions = list(script.complete(line_number, column_number))

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
                    kind=_completion_kind_from_name(completion),
                    detail=_completion_detail(completion),
                    source_file_path=None if module_path is None else str(Path(module_path).resolve()),
                    engine="jedi",
                    source="semantic",
                    confidence="exact",
                    semantic_kind=symbol_kind,
                )
            )
        return items

    def _script(
        self,
        *,
        project_root: str | None,
        current_file_path: str,
        source_text: str,
    ):
        status = initialize_jedi_runtime(self._state_root)
        if not status.is_available:
            raise RuntimeError(status.message)

        import jedi

        project = None if not project_root else self._project(project_root)
        return jedi.Script(code=source_text, path=current_file_path, project=project)

    def _project(self, project_root: str):
        normalized_root = str(Path(project_root).expanduser().resolve())
        cached = self._project_cache.get(normalized_root)
        if cached is not None:
            return cached

        import jedi

        root = Path(normalized_root)
        added_sys_path = []
        vendor_dir = root / "vendor"
        if vendor_dir.exists():
            added_sys_path.append(str(vendor_dir.resolve()))
        project = jedi.Project(
            normalized_root,
            added_sys_path=tuple(added_sys_path),
            load_unsafe_extensions=False,
            smart_sys_path=True,
        )
        self._project_cache[normalized_root] = project
        return project

    def _ordered_definition_names(
        self,
        *,
        script,
        line_number: int,
        column_number: int,
        current_file_path: str,
    ) -> list[Any]:
        names: list[Any] = []
        names.extend(script.infer(line_number, column_number))
        names.extend(
            script.goto(
                line_number,
                column_number,
                follow_imports=True,
                follow_builtin_imports=True,
            )
        )

        current_file = str(Path(current_file_path).expanduser().resolve())
        deduped: dict[tuple[str, int, int, str], Any] = {}
        for name in names:
            module_path = getattr(name, "module_path", None)
            resolved_file_path = "" if module_path is None else str(Path(module_path).resolve())
            key = (
                resolved_file_path,
                int(getattr(name, "line", 0) or 0),
                int(getattr(name, "column", 0) or 0),
                str(getattr(name, "name", "")),
            )
            deduped[key] = name
        return sorted(
            deduped.values(),
            key=lambda item: (
                _name_file_path(item) != current_file,
                _name_file_path(item),
                int(getattr(item, "line", 0) or 0),
                int(getattr(item, "column", 0) or 0),
            ),
        )


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


def _location_from_name(name: Any) -> SemanticLocation:
    module_path = getattr(name, "module_path", None)
    resolved_file_path = "" if module_path is None else str(Path(module_path).resolve())
    doc_text = _name_docstring(name)
    return SemanticLocation(
        name=str(getattr(name, "name", "")),
        file_path=resolved_file_path,
        line_number=int(getattr(name, "line", 0) or 0),
        column_number=None if getattr(name, "column", None) is None else int(name.column),
        symbol_kind=str(getattr(name, "type", "symbol")),
        signature_text=_signature_from_docstring(doc_text),
        doc_excerpt=first_doc_line(doc_text),
    )


def _name_docstring(name: Any) -> str:
    docstring_method = getattr(name, "docstring", None)
    if callable(docstring_method):
        try:
            return str(docstring_method())
        except Exception:
            return ""
    return ""


def _signature_from_docstring(doc_text: str) -> str:
    first_line = doc_text.strip().splitlines()[0] if doc_text.strip() else ""
    return first_line


def _doc_summary_from_jedi_payload(doc_text: str) -> str:
    lines = [line.strip() for line in doc_text.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) > 1 and "(" in lines[0] and ")" in lines[0]:
        return lines[1]
    return first_doc_line(doc_text)


def _completion_kind_from_name(completion: Any) -> CompletionKind:
    completion_type = str(getattr(completion, "type", "symbol"))
    if completion_type == "keyword":
        return CompletionKind.KEYWORD
    if completion_type == "module":
        return CompletionKind.MODULE
    if str(getattr(completion, "module_name", "")) == "builtins":
        return CompletionKind.BUILTIN
    return CompletionKind.SYMBOL


def _completion_detail(completion: Any) -> str:
    completion_type = str(getattr(completion, "type", "symbol"))
    module_name = str(getattr(completion, "module_name", "") or "")
    if module_name:
        return f"{completion_type} • semantic • {module_name}"
    return f"{completion_type} • semantic"


def _name_file_path(name: Any) -> str:
    module_path = getattr(name, "module_path", None)
    if module_path is None:
        return ""
    return str(Path(module_path).resolve())


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000.0
