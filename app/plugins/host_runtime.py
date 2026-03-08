from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable

from app.core import constants
from app.plugins.discovery import evaluate_manifest_compatibility
from app.plugins.manifest import load_plugin_manifest
from app.plugins.registry_store import load_plugin_registry


RuntimeCommandHandler = Callable[[dict[str, Any]], Any]


def load_runtime_command_handlers(
    *,
    state_root: str | None = None,
    app_version: str = constants.APP_VERSION,
    api_version: int = constants.PLUGIN_API_VERSION,
) -> dict[str, RuntimeCommandHandler]:
    registry = load_plugin_registry(state_root)
    handlers: dict[str, RuntimeCommandHandler] = {}
    for entry in registry.entries:
        if not entry.enabled:
            continue
        install_path = Path(entry.install_path).expanduser().resolve()
        manifest_path = install_path / constants.PLUGIN_MANIFEST_FILENAME
        if not manifest_path.exists():
            continue
        try:
            manifest = load_plugin_manifest(manifest_path)
        except Exception:
            continue
        compatibility = evaluate_manifest_compatibility(
            manifest,
            current_app_version=app_version,
            current_api_version=api_version,
        )
        if not compatibility.is_compatible:
            continue
        if not manifest.runtime_entrypoint:
            continue
        try:
            module = _load_runtime_module(
                plugin_id=manifest.plugin_id,
                install_path=install_path,
                runtime_entrypoint=manifest.runtime_entrypoint,
            )
        except Exception:
            continue
        contributes = manifest.contributes.get("commands", [])
        if not isinstance(contributes, list):
            continue
        for command_payload in contributes:
            if not isinstance(command_payload, dict):
                continue
            command_id = command_payload.get("id")
            runtime_flag = command_payload.get("runtime", True)
            runtime_handler_name = command_payload.get("runtime_handler", "handle_command")
            if not isinstance(command_id, str) or not command_id.strip():
                continue
            if runtime_flag is False:
                continue
            if not isinstance(runtime_handler_name, str) or not runtime_handler_name.strip():
                continue
            handler_function = getattr(module, runtime_handler_name.strip(), None)
            if not callable(handler_function):
                continue
            normalized_command_id = command_id.strip()
            handlers[normalized_command_id] = _build_handler(
                handler_function,
                normalized_command_id,
            )
    return handlers


def _load_runtime_module(
    *,
    plugin_id: str,
    install_path: Path,
    runtime_entrypoint: str,
) -> object:
    resolved_install_path = install_path.resolve()
    entrypoint_path = (resolved_install_path / runtime_entrypoint).resolve()
    try:
        entrypoint_path.relative_to(resolved_install_path)
    except ValueError as exc:
        raise RuntimeError(
            f"Runtime entrypoint escapes plugin install path: {runtime_entrypoint}"
        ) from exc
    if not entrypoint_path.exists() or not entrypoint_path.is_file():
        raise RuntimeError(f"Runtime entrypoint not found: {runtime_entrypoint}")
    module_name = f"cbcs_plugin_{plugin_id.replace('.', '_').replace('-', '_')}"
    module_spec = importlib.util.spec_from_file_location(module_name, entrypoint_path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Unable to load runtime module for plugin: {plugin_id}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _build_handler(runtime_callable: Callable[..., Any], command_id: str) -> RuntimeCommandHandler:
    def _handler(payload: dict[str, Any]) -> Any:
        try:
            return runtime_callable(command_id, payload)
        except TypeError:
            return runtime_callable(payload)

    return _handler
