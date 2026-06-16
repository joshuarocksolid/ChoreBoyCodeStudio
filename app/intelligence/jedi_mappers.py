"""Map Jedi name/completion objects to semantic and completion models."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.intelligence.completion_models import CompletionKind
from app.intelligence.semantic_models import SemanticLocation
from app.intelligence.semantic_utils import first_doc_line


def location_from_name(name: Any) -> SemanticLocation:
    module_path = getattr(name, "module_path", None)
    resolved_file_path = "" if module_path is None else str(Path(module_path).resolve())
    doc_text = name_docstring(name)
    return SemanticLocation(
        name=str(getattr(name, "name", "")),
        file_path=resolved_file_path,
        line_number=int(getattr(name, "line", 0) or 0),
        column_number=None if getattr(name, "column", None) is None else int(name.column),
        symbol_kind=str(getattr(name, "type", "symbol")),
        signature_text=signature_from_docstring(doc_text),
        doc_excerpt=first_doc_line(doc_text),
    )


def name_docstring(name: Any) -> str:
    docstring_method = getattr(name, "docstring", None)
    if callable(docstring_method):
        try:
            return str(docstring_method())
        except Exception:
            return ""
    return ""


def signature_from_docstring(doc_text: str) -> str:
    first_line = doc_text.strip().splitlines()[0] if doc_text.strip() else ""
    return first_line


def doc_summary_from_jedi_payload(doc_text: str) -> str:
    lines = [line.strip() for line in doc_text.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) > 1 and "(" in lines[0] and ")" in lines[0]:
        return lines[1]
    return first_doc_line(doc_text)


def completion_kind_from_name(completion: Any) -> CompletionKind:
    completion_type = str(getattr(completion, "type", "symbol"))
    if completion_type == "keyword":
        return CompletionKind.KEYWORD
    if completion_type == "module":
        return CompletionKind.MODULE
    if completion_type == "function":
        return CompletionKind.FUNCTION
    if completion_type == "class":
        return CompletionKind.CLASS
    if completion_type == "property":
        return CompletionKind.PROPERTY
    if completion_type == "instance":
        return CompletionKind.ATTRIBUTE
    if completion_type == "param":
        return CompletionKind.ATTRIBUTE
    if str(getattr(completion, "module_name", "")) == "builtins":
        return CompletionKind.BUILTIN
    return CompletionKind.SYMBOL


def completion_detail(completion: Any) -> str:
    completion_type = str(getattr(completion, "type", "symbol"))
    module_name = str(getattr(completion, "module_name", "") or "")
    if module_name:
        return f"{completion_type} • semantic • {module_name}"
    return f"{completion_type} • semantic"


def completion_documentation(completion: Any) -> str:
    docstring = getattr(completion, "docstring", None)
    if not callable(docstring):
        return ""
    try:
        return str(docstring(raw=False) or "")
    except TypeError:
        try:
            return str(docstring() or "")
        except Exception:
            return ""
    except Exception:
        return ""


def completion_signature(completion: Any) -> str:
    name_with_symbols = getattr(completion, "name_with_symbols", "")
    if name_with_symbols:
        return str(name_with_symbols)
    description = getattr(completion, "description", "")
    return str(description or "")


def name_file_path(name: Any) -> str:
    module_path = getattr(name, "module_path", None)
    if module_path is None:
        return ""
    return str(Path(module_path).resolve())
