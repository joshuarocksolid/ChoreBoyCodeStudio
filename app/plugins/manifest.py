from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping, NoReturn

from app.core import constants
from app.core.errors import PluginManifestValidationError
from app.plugins.models import PluginEngineConstraints, PluginManifest, PluginWorkflowProvider

PLUGIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PLUGIN_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def parse_plugin_manifest(payload: Mapping[str, Any], *, manifest_path: Path | None = None) -> PluginManifest:
    if not isinstance(payload, dict):
        _raise_error("Plugin manifest payload must be a JSON object.", manifest_path=manifest_path)

    plugin_id = _require_plugin_id(payload, manifest_path=manifest_path)
    name = _require_non_empty_string(payload, "name", manifest_path=manifest_path)
    version = _require_plugin_version(payload, manifest_path=manifest_path)
    api_version = _require_positive_int(payload, "api_version", manifest_path=manifest_path)

    runtime_payload = payload.get("runtime", {})
    runtime_entrypoint: str | None = None
    if runtime_payload is not None:
        if not isinstance(runtime_payload, dict):
            _raise_error("runtime must be an object.", field="runtime", manifest_path=manifest_path)
        entrypoint = runtime_payload.get("entrypoint")
        if entrypoint is not None:
            if not isinstance(entrypoint, str) or not entrypoint.strip():
                _raise_error(
                    "runtime.entrypoint must be a non-empty string.",
                    field="runtime.entrypoint",
                    manifest_path=manifest_path,
                )
            runtime_entrypoint = _validate_runtime_entrypoint(entrypoint.strip(), manifest_path=manifest_path)

    activation_events = _parse_string_list(
        payload.get("activation_events", []),
        field="activation_events",
        manifest_path=manifest_path,
    )
    capabilities = _parse_string_list(
        payload.get("capabilities", []),
        field="capabilities",
        manifest_path=manifest_path,
    )
    permissions = _parse_string_list(
        payload.get("permissions", []),
        field="permissions",
        manifest_path=manifest_path,
    )

    contributes = payload.get("contributes", {})
    if contributes is None:
        contributes = {}
    if not isinstance(contributes, dict):
        _raise_error("contributes must be an object.", field="contributes", manifest_path=manifest_path)
    workflow_providers = _parse_workflow_providers(
        contributes.get("workflow_providers", []),
        manifest_path=manifest_path,
    )
    if workflow_providers and runtime_entrypoint is None:
        _raise_error(
            "runtime.entrypoint is required when contributes.workflow_providers are declared.",
            field="runtime.entrypoint",
            manifest_path=manifest_path,
        )
    normalized_contributes = dict(contributes)
    if workflow_providers:
        normalized_contributes["workflow_providers"] = [provider.to_dict() for provider in workflow_providers]

    engine_payload = payload.get("engine_constraints", {})
    if engine_payload is None:
        engine_payload = {}
    if not isinstance(engine_payload, dict):
        _raise_error(
            "engine_constraints must be an object.",
            field="engine_constraints",
            manifest_path=manifest_path,
        )

    min_app_version = _optional_non_empty_string(
        engine_payload,
        "min_app_version",
        manifest_path=manifest_path,
    )
    max_app_version = _optional_non_empty_string(
        engine_payload,
        "max_app_version",
        manifest_path=manifest_path,
    )
    min_api_version = _optional_positive_int(
        engine_payload,
        "min_api_version",
        manifest_path=manifest_path,
    )
    max_api_version = _optional_positive_int(
        engine_payload,
        "max_api_version",
        manifest_path=manifest_path,
    )

    return PluginManifest(
        plugin_id=plugin_id,
        name=name,
        version=version,
        api_version=api_version,
        runtime_entrypoint=runtime_entrypoint,
        activation_events=activation_events,
        capabilities=capabilities,
        permissions=permissions,
        workflow_providers=workflow_providers,
        contributes=normalized_contributes,
        engine=PluginEngineConstraints(
            min_app_version=min_app_version,
            max_app_version=max_app_version,
            min_api_version=min_api_version,
            max_api_version=max_api_version,
        ),
    )


def load_plugin_manifest(path: str | Path) -> PluginManifest:
    manifest_path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _raise_error("Plugin manifest file not found.", manifest_path=manifest_path)
    except json.JSONDecodeError as exc:
        _raise_error(
            f"Invalid JSON in plugin manifest: {exc.msg} (line {exc.lineno}, column {exc.colno}).",
            manifest_path=manifest_path,
        )
    except OSError as exc:
        _raise_error(f"Unable to read plugin manifest: {exc}", manifest_path=manifest_path)
    return parse_plugin_manifest(payload, manifest_path=manifest_path)


def _parse_string_list(
    raw_value: object,
    *,
    field: str,
    manifest_path: Path | None,
) -> list[str]:
    if not isinstance(raw_value, list):
        _raise_error(f"{field} must be a list of strings.", field=field, manifest_path=manifest_path)
    values: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            _raise_error(
                f"{field}[{index}] must be a non-empty string.",
                field=field,
                manifest_path=manifest_path,
            )
        stripped = item.strip()
        if stripped not in values:
            values.append(stripped)
    return values


def _parse_workflow_providers(
    raw_value: object,
    *,
    manifest_path: Path | None,
) -> list[PluginWorkflowProvider]:
    if raw_value in (None, {}):
        return []
    if not isinstance(raw_value, list):
        _raise_error(
            "contributes.workflow_providers must be a list of objects.",
            field="contributes.workflow_providers",
            manifest_path=manifest_path,
        )
    providers: list[PluginWorkflowProvider] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_value):
        if not isinstance(item, dict):
            _raise_error(
                f"contributes.workflow_providers[{index}] must be an object.",
                field="contributes.workflow_providers",
                manifest_path=manifest_path,
            )
        provider_id = _require_non_empty_string(
            item,
            "id",
            manifest_path=manifest_path,
        )
        if provider_id in seen_ids:
            _raise_error(
                f"Duplicate workflow provider id: {provider_id}",
                field="contributes.workflow_providers",
                manifest_path=manifest_path,
            )
        seen_ids.add(provider_id)
        if not PLUGIN_ID_PATTERN.fullmatch(provider_id):
            _raise_error(
                "workflow provider id must use only letters, numbers, dots, underscores, or hyphens.",
                field="contributes.workflow_providers",
                manifest_path=manifest_path,
            )
        kind = _require_non_empty_string(item, "kind", manifest_path=manifest_path)
        if kind not in constants.WORKFLOW_PROVIDER_KINDS:
            _raise_error(
                f"Unsupported workflow provider kind: {kind}",
                field="contributes.workflow_providers",
                manifest_path=manifest_path,
            )
        lane = _require_non_empty_string(item, "lane", manifest_path=manifest_path)
        if lane not in (
            constants.WORKFLOW_PROVIDER_LANE_QUERY,
            constants.WORKFLOW_PROVIDER_LANE_JOB,
        ):
            _raise_error(
                f"Unsupported workflow provider lane: {lane}",
                field="contributes.workflow_providers",
                manifest_path=manifest_path,
            )
        title = _require_non_empty_string(item, "title", manifest_path=manifest_path)
        priority = _optional_positive_int(item, "priority", manifest_path=manifest_path)
        query_handler = _optional_non_empty_string(item, "query_handler", manifest_path=manifest_path)
        start_handler = _optional_non_empty_string(item, "start_handler", manifest_path=manifest_path)
        cancel_handler = _optional_non_empty_string(item, "cancel_handler", manifest_path=manifest_path)
        if lane == constants.WORKFLOW_PROVIDER_LANE_QUERY and query_handler is None:
            _raise_error(
                "Query workflow providers require query_handler.",
                field="contributes.workflow_providers",
                manifest_path=manifest_path,
            )
        if lane == constants.WORKFLOW_PROVIDER_LANE_JOB and start_handler is None:
            _raise_error(
                "Job workflow providers require start_handler.",
                field="contributes.workflow_providers",
                manifest_path=manifest_path,
            )
        languages = tuple(
            _parse_string_list(
                item.get("languages", []),
                field="contributes.workflow_providers.languages",
                manifest_path=manifest_path,
            )
        )
        file_extensions = tuple(_parse_file_extensions(item.get("file_extensions", []), manifest_path=manifest_path))
        capabilities = tuple(
            _parse_string_list(
                item.get("capabilities", []),
                field="contributes.workflow_providers.capabilities",
                manifest_path=manifest_path,
            )
        )
        permissions = tuple(
            _parse_string_list(
                item.get("permissions", []),
                field="contributes.workflow_providers.permissions",
                manifest_path=manifest_path,
            )
        )
        providers.append(
            PluginWorkflowProvider(
                provider_id=provider_id,
                kind=kind,
                lane=lane,
                title=title,
                priority=priority if priority is not None else 100,
                languages=languages,
                file_extensions=file_extensions,
                query_handler=query_handler,
                start_handler=start_handler,
                cancel_handler=cancel_handler,
                capabilities=capabilities,
                permissions=permissions,
            )
        )
    return providers


def _parse_file_extensions(raw_value: object, *, manifest_path: Path | None) -> list[str]:
    if not isinstance(raw_value, list):
        _raise_error(
            "file_extensions must be a list of strings.",
            field="contributes.workflow_providers.file_extensions",
            manifest_path=manifest_path,
        )
    extensions: list[str] = []
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            _raise_error(
                f"file_extensions[{index}] must be a non-empty string.",
                field="contributes.workflow_providers.file_extensions",
                manifest_path=manifest_path,
            )
        normalized = item.strip().lower()
        if not normalized.startswith(".") or normalized == ".":
            _raise_error(
                f"file_extensions[{index}] must start with '.'.",
                field="contributes.workflow_providers.file_extensions",
                manifest_path=manifest_path,
            )
        if normalized not in extensions:
            extensions.append(normalized)
    return extensions


def _require_non_empty_string(
    payload: Mapping[str, Any],
    field: str,
    *,
    manifest_path: Path | None,
) -> str:
    if field not in payload:
        _raise_error(f"Missing required field: {field}.", field=field, manifest_path=manifest_path)
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        _raise_error(f"{field} must be a non-empty string.", field=field, manifest_path=manifest_path)
    return value.strip()


def _optional_non_empty_string(
    payload: Mapping[str, Any],
    field: str,
    *,
    manifest_path: Path | None,
) -> str | None:
    if field not in payload:
        return None
    value = payload[field]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _raise_error(f"{field} must be a non-empty string.", field=field, manifest_path=manifest_path)
    return value.strip()


def _require_plugin_id(
    payload: Mapping[str, Any],
    *,
    manifest_path: Path | None,
) -> str:
    plugin_id = _require_non_empty_string(payload, "id", manifest_path=manifest_path)
    if not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
        _raise_error(
            "id must use only letters, numbers, dots, underscores, or hyphens.",
            field="id",
            manifest_path=manifest_path,
        )
    return plugin_id


def _require_plugin_version(
    payload: Mapping[str, Any],
    *,
    manifest_path: Path | None,
) -> str:
    version = _require_non_empty_string(payload, "version", manifest_path=manifest_path)
    if not PLUGIN_VERSION_PATTERN.fullmatch(version):
        _raise_error(
            "version must use only letters, numbers, dots, underscores, plus, or hyphens.",
            field="version",
            manifest_path=manifest_path,
        )
    return version


def _require_positive_int(
    payload: Mapping[str, Any],
    field: str,
    *,
    manifest_path: Path | None,
) -> int:
    if field not in payload:
        _raise_error(f"Missing required field: {field}.", field=field, manifest_path=manifest_path)
    value = payload[field]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _raise_error(f"{field} must be a positive integer.", field=field, manifest_path=manifest_path)
    return value


def _validate_runtime_entrypoint(
    entrypoint: str,
    *,
    manifest_path: Path | None,
) -> str:
    if "\\" in entrypoint:
        _raise_error(
            "runtime.entrypoint must use forward slashes and cannot contain backslashes.",
            field="runtime.entrypoint",
            manifest_path=manifest_path,
        )
    candidate = Path(entrypoint)
    if candidate.is_absolute():
        _raise_error(
            "runtime.entrypoint must be a relative path inside the plugin package.",
            field="runtime.entrypoint",
            manifest_path=manifest_path,
        )
    if any(part in {"..", "."} for part in candidate.parts):
        _raise_error(
            "runtime.entrypoint cannot contain '.' or '..' path segments.",
            field="runtime.entrypoint",
            manifest_path=manifest_path,
        )
    if not candidate.parts:
        _raise_error(
            "runtime.entrypoint must not be empty.",
            field="runtime.entrypoint",
            manifest_path=manifest_path,
        )
    return candidate.as_posix()


def _optional_positive_int(
    payload: Mapping[str, Any],
    field: str,
    *,
    manifest_path: Path | None,
) -> int | None:
    if field not in payload:
        return None
    value = payload[field]
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _raise_error(f"{field} must be a positive integer.", field=field, manifest_path=manifest_path)
    return value


def _raise_error(
    message: str,
    *,
    field: str | None = None,
    manifest_path: Path | None = None,
) -> NoReturn:
    raise PluginManifestValidationError(message, field=field, manifest_path=manifest_path)
