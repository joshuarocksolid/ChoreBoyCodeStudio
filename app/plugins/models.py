from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PluginEngineConstraints:
    min_app_version: str | None = None
    max_app_version: str | None = None
    min_api_version: int | None = None
    max_api_version: int | None = None


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    api_version: int
    runtime_entrypoint: str | None = None
    activation_events: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    contributes: dict[str, Any] = field(default_factory=dict)
    engine: PluginEngineConstraints = field(default_factory=PluginEngineConstraints)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "api_version": self.api_version,
            "activation_events": list(self.activation_events),
            "capabilities": list(self.capabilities),
            "contributes": dict(self.contributes),
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
class DiscoveredPlugin:
    plugin_id: str
    version: str
    install_path: str
    manifest_path: str
    manifest: PluginManifest | None = None
    compatibility: PluginCompatibility | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PluginRegistryEntry:
    plugin_id: str
    version: str
    install_path: str
    enabled: bool = True
    installed_at: str = ""
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.plugin_id,
            "version": self.version,
            "install_path": self.install_path,
            "enabled": self.enabled,
            "installed_at": self.installed_at,
        }
        if self.last_error:
            payload["last_error"] = self.last_error
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
