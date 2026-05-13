"""Helpers for loading and validating canonical project metadata manifests."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, NoReturn, Optional, Sequence
import uuid

from app.bootstrap.paths import PathInput, project_manifest_path
from app.core.errors import ProjectManifestValidationError
from app.core.models import ProjectMetadata

PROJECT_METADATA_SCHEMA_VERSION = 1
PROJECT_ID_PREFIX = "proj_"
_UNKNOWN_LEGACY_PROJECT_ID = f"{PROJECT_ID_PREFIX}legacy_unknown"


def deterministic_project_id_for_root(project_root: PathInput) -> str:
    """Return a stable project id derived from the resolved project root path.

    Matches the strategy used by local history when no manifest is present so
    editor metadata and history stay aligned before ``cbcs/project.json`` exists.
    """
    root = str(Path(project_root).expanduser().resolve())
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]
    return f"{PROJECT_ID_PREFIX}root_{digest}"


def build_synthetic_project_metadata(
    project_root: PathInput,
    *,
    default_entry: str,
    template: str = "imported_external",
) -> ProjectMetadata:
    """Build in-memory project metadata when ``cbcs/project.json`` is not on disk yet."""
    resolved = Path(project_root).expanduser().resolve()
    project_name = resolved.name.strip() or "Imported Project"
    payload = build_default_project_manifest_payload(
        project_name=project_name,
        project_id=deterministic_project_id_for_root(resolved),
        default_entry=default_entry,
        working_directory=".",
        template=template,
    )
    return parse_project_manifest(payload, manifest_path=project_manifest_path(resolved))


def materialize_project_manifest(manifest_path: PathInput, metadata: ProjectMetadata) -> None:
    """Write ``cbcs/project.json``, creating ``cbcs`` if needed (alias for :func:`save_project_manifest`)."""
    save_project_manifest(manifest_path, metadata)


def build_default_project_manifest_payload(
    *,
    project_name: str,
    project_id: Optional[str] = None,
    default_entry: str = "main.py",
    default_argv: Optional[list[str]] = None,
    working_directory: str = ".",
    template: str = "utility_script",
    run_configs: Optional[list[dict[str, Any]]] = None,
    env_overrides: Optional[Mapping[str, str]] = None,
    project_notes: str = "",
    exclude_patterns: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build a canonical manifest payload for new/imported projects."""
    if not _is_non_empty_string(project_name):
        raise ValueError("project_name must be a non-empty string.")
    normalized_project_id = generate_project_id() if project_id is None else _validate_project_id(project_id)
    if not _is_non_empty_string(default_entry):
        raise ValueError("default_entry must be a non-empty string.")
    if default_argv is not None and (
        not isinstance(default_argv, list) or any(not isinstance(value, str) for value in default_argv)
    ):
        raise ValueError("default_argv must be a list of strings.")
    if not _is_non_empty_string(working_directory):
        raise ValueError("working_directory must be a non-empty string.")
    if not _is_non_empty_string(template):
        raise ValueError("template must be a non-empty string.")
    if not isinstance(project_notes, str):
        raise ValueError("project_notes must be a string.")

    normalized_run_configs: list[dict[str, Any]] = []
    for index, run_config in enumerate(run_configs or []):
        if not isinstance(run_config, dict):
            raise ValueError(f"run_configs[{index}] must be an object.")
        normalized_run_configs.append(dict(run_config))

    normalized_env_overrides: dict[str, str] = {}
    if env_overrides is not None:
        for key, value in env_overrides.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("env_overrides must contain only string keys and values.")
            normalized_env_overrides[key] = value

    normalized_exclude_patterns: list[str] = []
    if exclude_patterns is not None:
        if not isinstance(exclude_patterns, list):
            raise ValueError("exclude_patterns must be a list of strings.")
        for item in exclude_patterns:
            if not isinstance(item, str):
                raise ValueError("exclude_patterns entries must be strings.")
            if item.strip():
                normalized_exclude_patterns.append(item.strip())

    metadata = ProjectMetadata(
        schema_version=PROJECT_METADATA_SCHEMA_VERSION,
        project_id=normalized_project_id,
        name=project_name.strip(),
        default_entry=default_entry.strip(),
        default_argv=[] if default_argv is None else list(default_argv),
        working_directory=working_directory.strip(),
        template=template.strip(),
        run_configs=normalized_run_configs,
        env_overrides=normalized_env_overrides,
        project_notes=project_notes,
        exclude_patterns=normalized_exclude_patterns,
    )
    return metadata.to_dict()


def load_project_manifest(manifest_path: PathInput) -> ProjectMetadata:
    """Load `<project>/cbcs/project.json` and return structured metadata."""
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


def save_project_manifest(manifest_path: PathInput, metadata: ProjectMetadata) -> None:
    """Persist canonical project metadata payload to disk."""
    from app.persistence.atomic_write import atomic_write_text

    path = Path(manifest_path).expanduser().resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        _raise_validation_error(f"Unable to write manifest file: {exc}", manifest_path=path)


def set_project_default_entry(
    manifest_path: PathInput,
    *,
    default_entry: str,
    metadata_if_absent: Optional[ProjectMetadata] = None,
) -> ProjectMetadata:
    """Update `default_entry` and persist the updated manifest metadata.

    When ``cbcs/project.json`` does not exist yet, pass ``metadata_if_absent`` (typically
    the in-memory metadata from :class:`~app.core.models.LoadedProject`) to materialize the file.
    """
    normalized_entry = default_entry.strip()
    if not normalized_entry:
        raise ValueError("default_entry must be a non-empty string.")
    path = Path(manifest_path).expanduser().resolve()
    if path.is_file():
        metadata = load_project_manifest(manifest_path)
    elif metadata_if_absent is not None:
        metadata = metadata_if_absent
    else:
        _raise_validation_error("Manifest file not found.", manifest_path=path)
    updated_metadata = replace(metadata, default_entry=normalized_entry)
    save_project_manifest(manifest_path, updated_metadata)
    return updated_metadata


def set_project_default_argv(
    manifest_path: PathInput,
    *,
    default_argv: Sequence[str],
    metadata_if_absent: Optional[ProjectMetadata] = None,
) -> ProjectMetadata:
    """Update ``default_argv`` and persist the updated manifest metadata.

    Materializes ``cbcs/project.json`` from ``metadata_if_absent`` when the manifest
    file does not yet exist on disk, mirroring :func:`set_project_default_entry`.
    """
    normalized_argv = [str(token) for token in default_argv if str(token).strip() != ""]
    path = Path(manifest_path).expanduser().resolve()
    if path.is_file():
        metadata = load_project_manifest(manifest_path)
    elif metadata_if_absent is not None:
        metadata = metadata_if_absent
    else:
        _raise_validation_error("Manifest file not found.", manifest_path=path)
    updated_metadata = replace(metadata, default_argv=normalized_argv)
    save_project_manifest(manifest_path, updated_metadata)
    return updated_metadata


def ensure_project_id(manifest_path: PathInput) -> ProjectMetadata:
    """Backfill a persistent project id when legacy manifests omit it."""
    path = Path(manifest_path).expanduser().resolve()
    metadata = load_project_manifest(path)
    if manifest_declares_project_id(path):
        return metadata

    updated_metadata = replace(metadata, project_id=generate_project_id())
    try:
        save_project_manifest(path, updated_metadata)
    except ProjectManifestValidationError:
        return metadata
    return updated_metadata


def generate_project_id() -> str:
    """Return a new persistent project identifier."""
    return f"{PROJECT_ID_PREFIX}{uuid.uuid4().hex}"


def manifest_declares_project_id(manifest_path: PathInput) -> bool:
    """Return True when the manifest explicitly stores a project id."""
    path = Path(manifest_path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and _is_valid_project_id(payload.get("project_id"))


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

    raw_project_id = payload.get("project_id")
    if raw_project_id is None:
        project_id = _legacy_project_id_for_manifest(resolved_path)
    else:
        project_id = _validate_project_id(raw_project_id, manifest_path=resolved_path)

    default_entry = _read_optional_non_empty_string(
        payload,
        "default_entry",
        default="main.py",
        manifest_path=resolved_path,
    )
    default_argv = payload.get("default_argv", [])
    if default_argv is None:
        default_argv = []
    if not isinstance(default_argv, list):
        _raise_validation_error("default_argv must be a list.", field="default_argv", manifest_path=resolved_path)
    normalized_default_argv: list[str] = []
    for index, raw_argv in enumerate(default_argv):
        if not isinstance(raw_argv, str):
            _raise_validation_error(
                "default_argv entries must be strings.",
                field=f"default_argv[{index}]",
                manifest_path=resolved_path,
            )
        normalized_default_argv.append(raw_argv)

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

    exclude_patterns_raw = payload.get("exclude_patterns", [])
    if exclude_patterns_raw is None:
        exclude_patterns_raw = []
    if not isinstance(exclude_patterns_raw, list):
        _raise_validation_error(
            "exclude_patterns must be a list.", field="exclude_patterns", manifest_path=resolved_path
        )
    normalized_exclude_patterns: list[str] = []
    for index, item in enumerate(exclude_patterns_raw):
        if not isinstance(item, str):
            _raise_validation_error(
                "exclude_patterns entries must be strings.",
                field=f"exclude_patterns[{index}]",
                manifest_path=resolved_path,
            )
        if item.strip():
            normalized_exclude_patterns.append(item.strip())

    return ProjectMetadata(
        schema_version=schema_version,
        project_id=project_id,
        name=name,
        default_entry=default_entry,
        default_argv=normalized_default_argv,
        working_directory=working_directory,
        template=template,
        run_configs=normalized_run_configs,
        env_overrides=normalized_env_overrides,
        project_notes=project_notes,
        exclude_patterns=normalized_exclude_patterns,
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


def _is_valid_project_id(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    if not normalized.startswith(PROJECT_ID_PREFIX):
        return False
    suffix = normalized[len(PROJECT_ID_PREFIX):]
    if not suffix:
        return False
    return all(character.islower() or character.isdigit() or character == "_" for character in suffix)


def _validate_project_id(value: Any, *, manifest_path: Optional[Path] = None) -> str:
    if not _is_valid_project_id(value):
        _raise_validation_error("project_id must be a non-empty identifier starting with proj_.", field="project_id", manifest_path=manifest_path)
    return value.strip()


def _legacy_project_id_for_manifest(manifest_path: Optional[Path]) -> str:
    if manifest_path is None:
        return _UNKNOWN_LEGACY_PROJECT_ID
    project_root = manifest_path.parent.parent
    digest = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:16]
    return f"{PROJECT_ID_PREFIX}path_{digest}"


def _raise_validation_error(
    message: str,
    *,
    field: Optional[str] = None,
    manifest_path: Optional[Path] = None,
) -> NoReturn:
    raise ProjectManifestValidationError(message, field=field, manifest_path=manifest_path)
