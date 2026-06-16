"""Definition, reference, hover, and signature lookup via Jedi."""
from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any, Optional

from app.bootstrap.paths import PathInput
from app.intelligence.jedi_mappers import (
    doc_summary_from_jedi_payload,
    location_from_name,
    name_docstring,
    name_file_path,
)
from app.intelligence.jedi_script_factory import create_script
from app.intelligence.semantic_models import (
    SemanticDefinitionResult,
    SemanticHoverResult,
    SemanticReferenceHit,
    SemanticReferenceResult,
    SemanticSignatureResult,
    exact_metadata,
)
from app.intelligence.semantic_utils import (
    extract_symbol_under_cursor,
    line_text_at,
    offset_to_line_column,
)


def ordered_definition_names(
    *,
    script: Any,
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
            name_file_path(item) != current_file,
            name_file_path(item),
            int(getattr(item, "line", 0) or 0),
            int(getattr(item, "column", 0) or 0),
        ),
    )


def lookup_definition(
    *,
    state_root: Optional[PathInput],
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    lock: threading.RLock,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    cursor_position: int,
) -> SemanticDefinitionResult:
    started_at = time.perf_counter()
    symbol_name = extract_symbol_under_cursor(source_text, cursor_position)
    if not symbol_name:
        return SemanticDefinitionResult(symbol_name="", locations=[], metadata=exact_metadata("jedi"))

    with lock:
        script = create_script(
            state_root=state_root,
            project_cache=project_cache,
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
        )
        line_number, column_number = offset_to_line_column(source_text, cursor_position)
        names = ordered_definition_names(
            script=script,
            line_number=line_number,
            column_number=column_number,
            current_file_path=current_file_path,
        )

    metadata = exact_metadata("jedi", latency_ms=_elapsed_ms(started_at))
    locations = [
        location_from_name(name)
        for name in names
        if getattr(name, "module_path", None) is not None
    ]
    return SemanticDefinitionResult(symbol_name=symbol_name, locations=locations, metadata=metadata)


def find_references(
    *,
    state_root: Optional[PathInput],
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    lock: threading.RLock,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    cursor_position: int,
) -> SemanticReferenceResult:
    started_at = time.perf_counter()
    symbol_name = extract_symbol_under_cursor(source_text, cursor_position)
    if not symbol_name:
        return SemanticReferenceResult(symbol_name="", hits=[], metadata=exact_metadata("jedi"))

    with lock:
        script = create_script(
            state_root=state_root,
            project_cache=project_cache,
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
    *,
    state_root: Optional[PathInput],
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    lock: threading.RLock,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    cursor_position: int,
) -> SemanticHoverResult | None:
    started_at = time.perf_counter()
    symbol_name = extract_symbol_under_cursor(source_text, cursor_position)
    if not symbol_name:
        return None

    with lock:
        script = create_script(
            state_root=state_root,
            project_cache=project_cache,
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
        )
        line_number, column_number = offset_to_line_column(source_text, cursor_position)
        names = ordered_definition_names(
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
    doc_text = name_docstring(first_name)
    return SemanticHoverResult(
        symbol_name=str(getattr(first_name, "name", symbol_name)),
        symbol_kind=str(getattr(first_name, "type", "symbol")),
        file_path=resolved_file_path,
        line_number=None if resolved_line_number is None else int(resolved_line_number),
        doc_summary=doc_summary_from_jedi_payload(doc_text),
        metadata=exact_metadata("jedi", latency_ms=_elapsed_ms(started_at)),
    )


def resolve_signature_help(
    *,
    state_root: Optional[PathInput],
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    lock: threading.RLock,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    cursor_position: int,
) -> SemanticSignatureResult | None:
    started_at = time.perf_counter()
    with lock:
        script = create_script(
            state_root=state_root,
            project_cache=project_cache,
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
        doc_summary=doc_summary_from_jedi_payload(signature.docstring()),
        metadata=exact_metadata("jedi", latency_ms=_elapsed_ms(started_at)),
    )


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000.0
