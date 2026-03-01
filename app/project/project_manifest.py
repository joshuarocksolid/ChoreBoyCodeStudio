"""Helpers for loading and validating canonical project metadata manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from app.bootstrap.paths import PathInput
from app.core.errors import ProjectManifestValidationError
from app.core.models import ProjectMetadata

PROJECT_METADATA_SCHEMA_VERSION = 1
ALLOWED_DEFAULT_MODES = frozenset({"python_script", "qt_app", "freecad_headless"})


def load_project_manifest(manifest_path: PathInput) -> ProjectMetadata:
    """Load `<project>/.cbcs/project.json` and return structured metadata."""
    path = Path(manifest_path).expanduser().resolve()
    try:
        raw_payload = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _raise_validation_error("Manifest file not found.", manifest_path=path)
    except OSError as exc:
        _raise_validation_error(f"Unable to read manifest file: {exc}", manifest_path=path)

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        _raise_validation_error(
            f"Invalid JSON in manifest: {exc.msg} (line {exc.lineno}, column {exc.colno}).",
            manifest_path=path,
        )

    return parse_project_manifest(payload, manifest_path=path)


def parse_project_manifest(payload: Mapping[str, Any], manifest_path: Optional[PathInput] = None) -> ProjectMetadata:
    """Validate a manifest payload and normalize it into `ProjectMetadata`."""
    resolved_path = None if manifest_path is None else Path(manifest_path).expanduser().resolve()
    if not isinstance(payload, dict):
        _raise_validation_error("Manifest payload must be a JSON object.", manifest_path=resolved_path)

    schema_version = _require_field(payload, "schema_version", manifest_path=resolved_path)
    if not _is_int(schema_version):
        _raise_validation_error("schema_version must be an integer.", field="schema_version", manifest_path=resolved_path)
    if schema_version != PROJECT_METADATA_SCHEMA_VERSION:
        _raise_validation_error(
            f"Unsupported schema_version: {schema_version}. Expected {PROJECT_METADATA_SCHEMA_VERSION}.",
            field="schema_version",
            manifest_path=resolved_path,
        )

    name = _require_field(payload, "name", manifest_path=resolved_path)
    if not _is_non_empty_string(name):
        _raise_validation_error("name must be a non-empty string.", field="name", manifest_path=resolved_path)

    default_entry = _read_optional_non_empty_string(
        payload,
        "default_entry",
        default="run.py",
        manifest_path=resolved_path,
    )
    default_mode = _read_optional_non_empty_string(
        payload,
        "default_mode",
        default="python_script",
        manifest_path=resolved_path,
    )
    if default_mode not in ALLOWED_DEFAULT_MODES:
        _raise_validation_error(
            f"Unsupported default_mode: {default_mode}. Allowed values: {sorted(ALLOWED_DEFAULT_MODES)}.",
            field="default_mode",
            manifest_path=resolved_path,
        )

    working_directory = _read_optional_non_empty_string(
        payload,
        "working_directory",
        default=".",
        manifest_path=resolved_path,
    )
    template = _read_optional_non_empty_string(
        payload,
        "template",
        default="utility_script",
        manifest_path=resolved_path,
    )

    safe_mode = payload.get("safe_mode", True)
    if not isinstance(safe_mode, bool):
        _raise_validation_error("safe_mode must be a boolean.", field="safe_mode", manifest_path=resolved_path)

    run_configs = payload.get("run_configs", [])
    if not isinstance(run_configs, list):
        _raise_validation_error("run_configs must be a list.", field="run_configs", manifest_path=resolved_path)

    normalized_run_configs: list[dict[str, Any]] = []
    for index, run_config in enumerate(run_configs):
        if not isinstance(run_config, dict):
            _raise_validation_error(
                "run_configs entries must be objects.",
                field=f"run_configs[{index}]",
                manifest_path=resolved_path,
            )
        normalized_run_configs.append(dict(run_config))

    env_overrides = payload.get("env_overrides", {})
    if env_overrides is None:
        env_overrides = {}
    if not isinstance(env_overrides, dict):
        _raise_validation_error("env_overrides must be an object.", field="env_overrides", manifest_path=resolved_path)

    normalized_env_overrides: dict[str, str] = {}
    for key, value in env_overrides.items():
        if not isinstance(key, str):
            _raise_validation_error(
                "env_overrides keys must be strings.",
                field="env_overrides",
                manifest_path=resolved_path,
            )
        if not isinstance(value, str):
            _raise_validation_error(
                f"env_overrides[{key}] must be a string.",
                field=f"env_overrides[{key}]",
                manifest_path=resolved_path,
            )
        normalized_env_overrides[key] = value

    project_notes = payload.get("project_notes", "")
    if project_notes is None:
        project_notes = ""
    if not isinstance(project_notes, str):
        _raise_validation_error("project_notes must be a string.", field="project_notes", manifest_path=resolved_path)

    return ProjectMetadata(
        schema_version=schema_version,
        name=name,
        default_entry=default_entry,
        default_mode=default_mode,
        working_directory=working_directory,
        template=template,
        safe_mode=safe_mode,
        run_configs=normalized_run_configs,
        env_overrides=normalized_env_overrides,
        project_notes=project_notes,
    )


def _require_field(payload: Mapping[str, Any], field_name: str, manifest_path: Optional[Path]) -> Any:
    if field_name not in payload:
        _raise_validation_error(f"Missing required field: {field_name}.", field=field_name, manifest_path=manifest_path)
    return payload[field_name]


def _read_optional_non_empty_string(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    default: str,
    manifest_path: Optional[Path],
) -> str:
    value = payload.get(field_name, default)
    if not _is_non_empty_string(value):
        _raise_validation_error(f"{field_name} must be a non-empty string.", field=field_name, manifest_path=manifest_path)
    return value


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _raise_validation_error(
    message: str,
    *,
    field: Optional[str] = None,
    manifest_path: Optional[Path] = None,
) -> None:
    raise ProjectManifestValidationError(message, field=field, manifest_path=manifest_path)
