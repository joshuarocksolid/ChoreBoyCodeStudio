from __future__ import annotations

from typing import Any, Mapping

from app.core import constants
from app.intelligence.diagnostics_service import analyze_python_file
from app.plugins.runtime_serializers import serialize_code_diagnostics


def handle_diagnostics_query(_provider_key: str, request: Mapping[str, Any]) -> list[dict[str, Any]]:
    known_runtime_modules_payload = request.get("known_runtime_modules", [])
    known_runtime_modules = (
        frozenset(
            item
            for item in known_runtime_modules_payload
            if isinstance(item, str) and item.strip()
        )
        if isinstance(known_runtime_modules_payload, list)
        else None
    )
    diagnostics = analyze_python_file(
        _require_string(request, "file_path"),
        project_root=_optional_string(request, "project_root"),
        source=_optional_string(request, "source"),
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=bool(request.get("allow_runtime_import_probe", False)),
        selected_linter=_optional_string(request, "selected_linter") or constants.LINTER_PROVIDER_DEFAULT,
        lint_rule_overrides=_mapping_value(request, "lint_rule_overrides"),
    )
    return serialize_code_diagnostics(diagnostics)


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return None
