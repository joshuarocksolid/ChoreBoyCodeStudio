"""Project-local packaging configuration helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from app.bootstrap.paths import PathInput, project_package_config_path
from app.core.models import ProjectMetadata
from app.packaging.layout import sanitize_project_name
from app.packaging.models import DEFAULT_PACKAGE_VERSION, PACKAGE_CONFIG_SCHEMA_VERSION, ProjectPackageConfig
from app.persistence.atomic_write import atomic_write_text

_PACKAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PACKAGE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?$")


def build_default_package_config(*, project_metadata: ProjectMetadata) -> ProjectPackageConfig:
    """Return default packaging metadata for a project that lacks `cbcs/package.json`."""
    default_package_id = sanitize_project_name(project_metadata.name)
    if not default_package_id:
        default_package_id = project_metadata.project_id.lower()
    return ProjectPackageConfig(
        schema_version=PACKAGE_CONFIG_SCHEMA_VERSION,
        package_id=default_package_id,
        display_name=project_metadata.name,
        version=DEFAULT_PACKAGE_VERSION,
        description="",
        entry_file=project_metadata.default_entry,
        icon_path="",
    )


def load_project_package_config(config_path: PathInput) -> ProjectPackageConfig:
    """Load and validate a project packaging config file."""
    path = Path(config_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_project_package_config(payload, config_path=path)


def save_project_package_config(config_path: PathInput, config: ProjectPackageConfig) -> None:
    """Persist a validated project packaging config to disk."""
    path = Path(config_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n")


def load_or_create_project_package_config(
    *,
    project_root: PathInput,
    project_metadata: ProjectMetadata,
) -> ProjectPackageConfig:
    """Load an existing package config or materialize canonical defaults."""
    path = project_package_config_path(project_root)
    if path.exists() and path.is_file():
        return load_project_package_config(path)
    config = build_default_package_config(project_metadata=project_metadata)
    save_project_package_config(path, config)
    return config


def resolve_project_package_config(
    *,
    project_root: PathInput,
    project_metadata: ProjectMetadata,
) -> ProjectPackageConfig:
    """Load an existing package config or return defaults without writing to disk."""
    path = project_package_config_path(project_root)
    if path.exists() and path.is_file():
        return load_project_package_config(path)
    return build_default_package_config(project_metadata=project_metadata)


def parse_project_package_config(
    payload: Mapping[str, Any],
    *,
    config_path: Path | None = None,
) -> ProjectPackageConfig:
    """Validate raw JSON payload into a normalized package config."""
    if not isinstance(payload, Mapping):
        raise ValueError(_with_path("Package config must be a JSON object.", config_path))

    schema_version = payload.get("schema_version", PACKAGE_CONFIG_SCHEMA_VERSION)
    if not isinstance(schema_version, int):
        raise ValueError(_with_path("schema_version must be an integer.", config_path))
    if schema_version != PACKAGE_CONFIG_SCHEMA_VERSION:
        raise ValueError(
            _with_path(
                f"Unsupported schema_version: {schema_version}. Expected {PACKAGE_CONFIG_SCHEMA_VERSION}.",
                config_path,
            )
        )

    package_id = payload.get("package_id")
    if not isinstance(package_id, str) or not _PACKAGE_ID_RE.match(package_id.strip()):
        raise ValueError(
            _with_path(
                "package_id must contain only lowercase letters, digits, dots, hyphens, or underscores.",
                config_path,
            )
        )
    display_name = payload.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError(_with_path("display_name must be a non-empty string.", config_path))
    version = payload.get("version", DEFAULT_PACKAGE_VERSION)
    if not isinstance(version, str) or not _PACKAGE_VERSION_RE.match(version.strip()):
        raise ValueError(
            _with_path(
                "version must use a stable dotted release format such as 1.0.0 or 1.0.0-beta.",
                config_path,
            )
        )
    description = payload.get("description", "")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise ValueError(_with_path("description must be a string.", config_path))
    entry_file = payload.get("entry_file", "")
    if entry_file is None:
        entry_file = ""
    if not isinstance(entry_file, str):
        raise ValueError(_with_path("entry_file must be a string.", config_path))
    icon_path = payload.get("icon_path", "")
    if icon_path is None:
        icon_path = ""
    if not isinstance(icon_path, str):
        raise ValueError(_with_path("icon_path must be a string.", config_path))

    return ProjectPackageConfig(
        schema_version=schema_version,
        package_id=package_id.strip(),
        display_name=display_name.strip(),
        version=version.strip(),
        description=description.strip(),
        entry_file=entry_file.strip(),
        icon_path=icon_path.strip(),
    )


def _with_path(message: str, config_path: Path | None) -> str:
    if config_path is None:
        return message
    return f"{message} ({config_path})"
