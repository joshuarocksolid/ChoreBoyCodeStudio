from __future__ import annotations

from typing import Any, Mapping

from app.plugins.runtime_serializers import serialize_python_text_transform_result
from app.python_tools.black_adapter import format_python_text
from app.python_tools.isort_adapter import organize_imports_text


def handle_formatter_query(_provider_key: str, request: Mapping[str, Any]) -> dict[str, Any]:
    result = format_python_text(
        _require_string(request, "source_text"),
        file_path=_require_string(request, "file_path"),
        project_root=_require_string(request, "project_root"),
    )
    return serialize_python_text_transform_result(result)


def handle_import_query(_provider_key: str, request: Mapping[str, Any]) -> dict[str, Any]:
    result = organize_imports_text(
        _require_string(request, "source_text"),
        file_path=_require_string(request, "file_path"),
        project_root=_require_string(request, "project_root"),
    )
    return serialize_python_text_transform_result(result)


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value
