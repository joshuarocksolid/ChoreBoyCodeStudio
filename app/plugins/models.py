from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core import constants

@dataclass(frozen=True)
class PluginEngineConstraints:
    min_app_version: str | None = None
    max_app_version: str | None = None
    min_api_version: int | None = None
    max_api_version: int | None = None


@dataclass(frozen=True)
class PluginCommandContribution:
    command_id: str
    title: str
    menu_id: str = "shell.menu.tools"
    shortcut: str | None = None
    status_tip: str | None = None
    tool_tip: str | None = None
    message: str | None = None
    runtime: bool = False
    runtime_payload: dict[str, Any] = field(default_factory=dict)
    runtime_handler: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.command_id,
            "title": self.title,
        }
        if self.menu_id != "shell.menu.tools":
            payload["menu_id"] = self.menu_id
        if self.shortcut is not None:
            payload["shortcut"] = self.shortcut
        if self.status_tip is not None:
            payload["status_tip"] = self.status_tip
        if self.tool_tip is not None:
            payload["tool_tip"] = self.tool_tip
        if self.message is not None:
            payload["message"] = self.message
        if self.runtime:
            payload["runtime"] = True
        if self.runtime_payload:
            payload["runtime_payload"] = dict(self.runtime_payload)
        if self.runtime_handler is not None:
            payload["runtime_handler"] = self.runtime_handler
        return payload


@dataclass(frozen=True)
class PluginWorkflowProvider:
    provider_id: str
    kind: str
    lane: str
    title: str
    priority: int = 100
    languages: tuple[str, ...] = field(default_factory=tuple)
    file_extensions: tuple[str, ...] = field(default_factory=tuple)
    query_handler: str | None = None
    start_handler: str | None = None
    cancel_handler: str | None = None
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    permissions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def default_activation_event(self) -> str:
        return f"on_provider:{self.kind}"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.provider_id,
            "kind": self.kind,
            "lane": self.lane,
            "title": self.title,
        }
        if self.priority != 100:
            payload["priority"] = self.priority
        if self.languages:
            payload["languages"] = list(self.languages)
        if self.file_extensions:
            payload["file_extensions"] = list(self.file_extensions)
        if self.query_handler:
            payload["query_handler"] = self.query_handler
        if self.start_handler:
            payload["start_handler"] = self.start_handler
        if self.cancel_handler:
            payload["cancel_handler"] = self.cancel_handler
        if self.capabilities:
            payload["capabilities"] = list(self.capabilities)
        if self.permissions:
            payload["permissions"] = list(self.permissions)
        return payload


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    api_version: int
    runtime_entrypoint: str | None = None
    activation_events: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    command_contributions: list[PluginCommandContribution] = field(default_factory=list)
    workflow_providers: list[PluginWorkflowProvider] = field(default_factory=list)
    contributes: dict[str, Any] = field(default_factory=dict)
    engine: PluginEngineConstraints = field(default_factory=PluginEngineConstraints)

    def to_dict(self) -> dict[str, Any]:
        contributes_payload = dict(self.contributes)
        if self.command_contributions:
            contributes_payload["commands"] = [
                command.to_dict() for command in self.command_contributions
            ]
        if self.workflow_providers:
            contributes_payload["workflow_providers"] = [
                provider.to_dict() for provider in self.workflow_providers
            ]
        payload: dict[str, Any] = {
            "id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "api_version": self.api_version,
            "activation_events": list(self.activation_events),
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "contributes": contributes_payload,
        }
        if self.runtime_entrypoint:
            payload["runtime"] = {"entrypoint": self.runtime_entrypoint}
        engine_payload: dict[str, Any] = {}
        if self.engine.min_app_version is not None:
            engine_payload["min_app_version"] = self.engine.min_app_version
        if self.engine.max_app_version is not None:
            engine_payload["max_app_version"] = self.engine.max_app_version
        if self.engine.min_api_version is not None:
            engine_payload["min_api_version"] = self.engine.min_api_version
        if self.engine.max_api_version is not None:
            engine_payload["max_api_version"] = self.engine.max_api_version
        if engine_payload:
            payload["engine_constraints"] = engine_payload
        return payload


@dataclass(frozen=True)
class PluginCompatibility:
    is_compatible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiscoveredWorkflowProvider:
    plugin_id: str
    plugin_version: str
    source_kind: str
    install_path: str
    provider: PluginWorkflowProvider
    manifest: PluginManifest
    provider_key: str

    @property
    def is_bundled(self) -> bool:
        return self.source_kind == constants.PLUGIN_SOURCE_BUNDLED


@dataclass(frozen=True)
class DiscoveredPlugin:
    plugin_id: str
    version: str
    install_path: str
    manifest_path: str
    source_kind: str = constants.PLUGIN_SOURCE_INSTALLED
    manifest: PluginManifest | None = None
    compatibility: PluginCompatibility | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_bundled(self) -> bool:
        return self.source_kind == constants.PLUGIN_SOURCE_BUNDLED


@dataclass(frozen=True)
class PluginRegistryEntry:
    plugin_id: str
    version: str
    install_path: str
    source_kind: str = constants.PLUGIN_SOURCE_INSTALLED
    enabled: bool = True
    installed_at: str = ""
    last_error: str | None = None
    failure_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.plugin_id,
            "version": self.version,
            "install_path": self.install_path,
            "source_kind": self.source_kind,
            "enabled": self.enabled,
            "installed_at": self.installed_at,
        }
        if self.last_error:
            payload["last_error"] = self.last_error
        payload["failure_count"] = self.failure_count
        return payload


@dataclass(frozen=True)
class PluginRegistry:
    schema_version: int
    entries: list[PluginRegistryEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_dict() for entry in self.entries],
        }
