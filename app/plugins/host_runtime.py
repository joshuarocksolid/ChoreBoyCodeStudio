from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Any, Callable

from app.core import constants
from app.plugins.discovery import discover_installed_plugins
from app.plugins.models import DiscoveredPlugin, PluginManifest, PluginWorkflowProvider
from app.plugins.registry_store import load_plugin_registry
from app.plugins.trust_store import is_runtime_plugin_trusted
from app.plugins.workflow_catalog import provider_key

RuntimeCommandHandler = Callable[[dict[str, Any]], Any]
RuntimeJobEventEmitter = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class _RuntimeCommandBinding:
    command_id: str
    handler_name: str
    manifest: PluginManifest
    install_path: Path
    source_kind: str


@dataclass(frozen=True)
class _RuntimeProviderBinding:
    provider_key: str
    provider: PluginWorkflowProvider
    manifest: PluginManifest
    install_path: Path
    source_kind: str


def load_plugin_runtime_module(
    plugin_id: str,
    install_path: Path,
    runtime_entrypoint: str | None,
    *,
    module_cache: dict[tuple[str, str], object],
) -> object:
    if runtime_entrypoint is None:
        raise RuntimeError(f"Plugin '{plugin_id}' has no runtime entrypoint.")
    cache_key = (plugin_id, str(install_path))
    cached = module_cache.get(cache_key)
    if cached is not None:
        return cached
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
    module_cache[cache_key] = module
    return module


class RuntimePluginIndex:
    def __init__(
        self,
        *,
        state_root: str | None = None,
        app_version: str = constants.APP_VERSION,
        api_version: int = constants.PLUGIN_API_VERSION,
    ) -> None:
        self._state_root = state_root
        self._command_bindings: dict[str, _RuntimeCommandBinding] = {}
        self._provider_bindings: dict[str, _RuntimeProviderBinding] = {}
        self._module_cache: dict[tuple[str, str], object] = {}
        self._build_index(app_version=app_version, api_version=api_version)

    @property
    def command_count(self) -> int:
        return len(self._command_bindings)

    @property
    def provider_count(self) -> int:
        return len(self._provider_bindings)

    def invoke_command(
        self,
        command_id: str,
        payload: dict[str, Any],
        *,
        activation_event: str | None = None,
    ) -> Any:
        binding = self._command_bindings.get(command_id)
        if binding is None:
            raise RuntimeError(f"Command not found: {command_id}")
        requested_event = activation_event or f"on_command:{command_id}"
        if not _activation_matches(
            binding.manifest.activation_events,
            requested_event,
            fallbacks=(f"on_command:{command_id}", "on_command"),
        ):
            raise RuntimeError(
                f"Command '{command_id}' is not active for event '{requested_event}'."
            )
        module = self._load_runtime_module(
            plugin_id=binding.manifest.plugin_id,
            install_path=binding.install_path,
            runtime_entrypoint=binding.manifest.runtime_entrypoint,
        )
        runtime_callable = getattr(module, binding.handler_name, None)
        if not callable(runtime_callable):
            raise RuntimeError(
                f"Runtime handler '{binding.handler_name}' not found for command '{command_id}'."
            )
        return runtime_callable(command_id, payload)

    def invoke_query(
        self,
        provider_id: str,
        request: dict[str, Any],
        *,
        activation_event: str | None = None,
    ) -> Any:
        binding = self._provider_bindings.get(provider_id)
        if binding is None:
            raise RuntimeError(f"Workflow provider not found: {provider_id}")
        if binding.provider.lane != constants.WORKFLOW_PROVIDER_LANE_QUERY:
            raise RuntimeError(f"Workflow provider is not query-capable: {provider_id}")
        requested_event = activation_event or binding.provider.default_activation_event
        if not _activation_matches(
            binding.manifest.activation_events,
            requested_event,
            fallbacks=(binding.provider.default_activation_event, "on_query"),
        ):
            raise RuntimeError(
                f"Workflow provider '{provider_id}' is not active for event '{requested_event}'."
            )
        module = self._load_runtime_module(
            plugin_id=binding.manifest.plugin_id,
            install_path=binding.install_path,
            runtime_entrypoint=binding.manifest.runtime_entrypoint,
        )
        handler_name = binding.provider.query_handler or "handle_query"
        runtime_callable = getattr(module, handler_name, None)
        if not callable(runtime_callable):
            raise RuntimeError(
                f"Query handler '{handler_name}' not found for provider '{provider_id}'."
            )
        return runtime_callable(provider_id, request)

    def run_job(
        self,
        provider_id: str,
        request: dict[str, Any],
        *,
        emit_event: RuntimeJobEventEmitter,
        is_cancelled: Callable[[], bool],
        activation_event: str | None = None,
    ) -> Any:
        binding = self._provider_bindings.get(provider_id)
        if binding is None:
            raise RuntimeError(f"Workflow provider not found: {provider_id}")
        if binding.provider.lane != constants.WORKFLOW_PROVIDER_LANE_JOB:
            raise RuntimeError(f"Workflow provider is not job-capable: {provider_id}")
        requested_event = activation_event or binding.provider.default_activation_event
        if not _activation_matches(
            binding.manifest.activation_events,
            requested_event,
            fallbacks=(binding.provider.default_activation_event, "on_job"),
        ):
            raise RuntimeError(
                f"Workflow provider '{provider_id}' is not active for event '{requested_event}'."
            )
        module = self._load_runtime_module(
            plugin_id=binding.manifest.plugin_id,
            install_path=binding.install_path,
            runtime_entrypoint=binding.manifest.runtime_entrypoint,
        )
        handler_name = binding.provider.start_handler or "handle_job"
        runtime_callable = getattr(module, handler_name, None)
        if not callable(runtime_callable):
            raise RuntimeError(
                f"Job handler '{handler_name}' not found for provider '{provider_id}'."
            )
        return runtime_callable(provider_id, request, emit_event, is_cancelled)

    def _build_index(self, *, app_version: str, api_version: int) -> None:
        registry = load_plugin_registry(self._state_root)
        enabled_map = {
            (entry.plugin_id, entry.version): entry.enabled
            for entry in registry.entries
        }
        discovered = discover_installed_plugins(
            state_root=self._state_root,
            current_app_version=app_version,
            current_api_version=api_version,
            include_bundled=True,
        )
        for plugin in discovered:
            if plugin.manifest is None:
                continue
            if plugin.compatibility is not None and not plugin.compatibility.is_compatible:
                continue
            if not enabled_map.get((plugin.plugin_id, plugin.version), True):
                continue
            if plugin.manifest.runtime_entrypoint is None:
                continue
            if not _is_runtime_plugin_effectively_trusted(
                plugin,
                state_root=self._state_root,
            ):
                continue
            self._index_runtime_commands(plugin)
            self._index_workflow_providers(plugin)

    def _index_runtime_commands(self, plugin: DiscoveredPlugin) -> None:
        manifest = plugin.manifest
        if manifest is None:
            return
        for command in manifest.command_contributions:
            if not command.runtime:
                continue
            handler_name = command.runtime_handler or "handle_command"
            self._command_bindings[command.command_id] = _RuntimeCommandBinding(
                command_id=command.command_id,
                handler_name=handler_name,
                manifest=manifest,
                install_path=Path(plugin.install_path).expanduser().resolve(),
                source_kind=plugin.source_kind,
            )

    def _index_workflow_providers(self, plugin: DiscoveredPlugin) -> None:
        manifest = plugin.manifest
        if manifest is None:
            return
        for provider in manifest.workflow_providers:
            key = provider_key(plugin.plugin_id, provider.provider_id)
            self._provider_bindings[key] = _RuntimeProviderBinding(
                provider_key=key,
                provider=provider,
                manifest=manifest,
                install_path=Path(plugin.install_path).expanduser().resolve(),
                source_kind=plugin.source_kind,
            )

    def _load_runtime_module(
        self,
        *,
        plugin_id: str,
        install_path: Path,
        runtime_entrypoint: str | None,
    ) -> object:
        return load_plugin_runtime_module(
            plugin_id,
            install_path,
            runtime_entrypoint,
            module_cache=self._module_cache,
        )


def load_runtime_index(
    *,
    state_root: str | None = None,
    app_version: str = constants.APP_VERSION,
    api_version: int = constants.PLUGIN_API_VERSION,
) -> RuntimePluginIndex:
    return RuntimePluginIndex(
        state_root=state_root,
        app_version=app_version,
        api_version=api_version,
    )


def load_runtime_command_handlers(
    *,
    state_root: str | None = None,
    app_version: str = constants.APP_VERSION,
    api_version: int = constants.PLUGIN_API_VERSION,
) -> dict[str, RuntimeCommandHandler]:
    runtime_index = load_runtime_index(
        state_root=state_root,
        app_version=app_version,
        api_version=api_version,
    )
    handlers: dict[str, RuntimeCommandHandler] = {}
    for command_id in list(runtime_index._command_bindings):
        handlers[command_id] = (
            lambda payload, cid=command_id, index=runtime_index: index.invoke_command(cid, payload)
        )
    return handlers


def _load_runtime_module(
    *,
    plugin_id: str,
    install_path: Path,
    runtime_entrypoint: str,
) -> object:
    return load_plugin_runtime_module(
        plugin_id,
        install_path,
        runtime_entrypoint,
        module_cache={},
    )


def _is_runtime_plugin_effectively_trusted(
    discovered_plugin: DiscoveredPlugin,
    *,
    state_root: str | None,
) -> bool:
    if discovered_plugin.source_kind == constants.PLUGIN_SOURCE_BUNDLED:
        return True
    return is_runtime_plugin_trusted(
        discovered_plugin.plugin_id,
        discovered_plugin.version,
        state_root=state_root,
    )


def _activation_matches(
    activation_events: list[str],
    requested_event: str | None,
    *,
    fallbacks: tuple[str, ...] = (),
) -> bool:
    if not activation_events:
        return True
    candidates = []
    if requested_event is not None:
        candidates.append(requested_event)
    candidates.extend(fallbacks)
    for candidate in candidates:
        if candidate and candidate in activation_events:
            return True
    return False


