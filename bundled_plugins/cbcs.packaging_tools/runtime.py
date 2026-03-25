from __future__ import annotations

from typing import Any, Mapping

from app.core.models import ProjectMetadata
from app.packaging.config import parse_project_package_config
from app.packaging.packager import package_project
from app.plugins.runtime_serializers import serialize_package_result


def handle_packaging_job(
    _provider_key: str,
    request: Mapping[str, Any],
    emit_event,
    is_cancelled,
) -> dict[str, Any]:
    _ = is_cancelled
    project_root = _require_string(request, "project_root")
    emit_event("job_started", {"project_root": project_root})
    result = package_project(
        project_root=project_root,
        project_name=_require_string(request, "project_name"),
        entry_file=_require_string(request, "entry_file"),
        output_dir=_require_string(request, "output_dir"),
        profile=_optional_string(request, "profile") or "installable",
        package_config=_parse_project_package_config(request.get("package_config")),
        project_metadata=_parse_project_metadata(request.get("project_metadata")),
        known_runtime_modules=_parse_known_runtime_modules(request.get("known_runtime_modules")),
    )
    emit_event(
        "job_finished",
        {"success": result.success, "artifact_root": result.artifact_root},
    )
    return serialize_package_result(result)


def _parse_project_package_config(raw_value: Any):
    if not isinstance(raw_value, dict):
        return None
    return parse_project_package_config(raw_value)


def _parse_project_metadata(raw_value: Any) -> ProjectMetadata | None:
    if not isinstance(raw_value, dict):
        return None
    name = raw_value.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    schema_version = raw_value.get("schema_version", 1)
    if not isinstance(schema_version, int) or schema_version <= 0:
        schema_version = 1
    default_argv = raw_value.get("default_argv", [])
    run_configs = raw_value.get("run_configs", [])
    exclude_patterns = raw_value.get("exclude_patterns", [])
    env_overrides = raw_value.get("env_overrides", {})
    return ProjectMetadata(
        schema_version=schema_version,
        name=name,
        project_id=_optional_string(raw_value, "project_id") or "proj_legacy_unknown",
        default_entry=_optional_string(raw_value, "default_entry") or "main.py",
        default_argv=[item for item in default_argv if isinstance(item, str)] if isinstance(default_argv, list) else [],
        working_directory=_optional_string(raw_value, "working_directory") or ".",
        template=_optional_string(raw_value, "template") or "utility_script",
        run_configs=list(run_configs) if isinstance(run_configs, list) else [],
        env_overrides=dict(env_overrides) if isinstance(env_overrides, dict) else {},
        project_notes=_optional_string(raw_value, "project_notes") or "",
        exclude_patterns=[item for item in exclude_patterns if isinstance(item, str)] if isinstance(exclude_patterns, list) else [],
    )


def _parse_known_runtime_modules(raw_value: Any) -> frozenset[str] | None:
    if not isinstance(raw_value, list):
        return None
    return frozenset(item for item in raw_value if isinstance(item, str) and item.strip())


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
