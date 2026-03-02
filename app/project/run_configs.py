"""Run-configuration parsing and serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core import constants


@dataclass(frozen=True)
class RunConfiguration:
    """Normalized named run configuration."""

    name: str
    entry_file: str
    mode: str
    argv: list[str]
    working_directory: str | None = None
    env_overrides: dict[str, str] = field(default_factory=dict)
    safe_mode: bool | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "entry_file": self.entry_file,
            "mode": self.mode,
            "argv": list(self.argv),
        }
        if self.working_directory is not None:
            payload["working_directory"] = self.working_directory
        if self.env_overrides:
            payload["env_overrides"] = dict(self.env_overrides)
        if self.safe_mode is not None:
            payload["safe_mode"] = self.safe_mode
        return payload


def parse_run_config(raw_payload: Mapping[str, Any]) -> RunConfiguration:
    """Validate one run-config payload into normalized model."""
    name = raw_payload.get("name", "")
    entry_file = raw_payload.get("entry_file", "")
    mode = raw_payload.get("mode", constants.RUN_MODE_PYTHON_SCRIPT)
    argv = raw_payload.get("argv", [])
    working_directory = raw_payload.get("working_directory")
    env_overrides = raw_payload.get("env_overrides", {})
    safe_mode = raw_payload.get("safe_mode")

    if not isinstance(name, str) or not name.strip():
        raise ValueError("run config name must be a non-empty string")
    if not isinstance(entry_file, str) or not entry_file.strip():
        raise ValueError("run config entry_file must be a non-empty string")
    if mode not in {
        constants.RUN_MODE_PYTHON_SCRIPT,
        constants.RUN_MODE_QT_APP,
        constants.RUN_MODE_FREECAD_HEADLESS,
        constants.RUN_MODE_PYTHON_DEBUG,
    }:
        raise ValueError("run config mode is unsupported")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
        raise ValueError("run config argv must be a string list")
    if working_directory is not None and (not isinstance(working_directory, str) or not working_directory.strip()):
        raise ValueError("run config working_directory must be a non-empty string when provided")
    if not isinstance(env_overrides, dict):
        raise ValueError("run config env_overrides must be an object")
    normalized_env_overrides: dict[str, str] = {}
    for key, value in env_overrides.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("run config env_overrides must contain string key/value pairs")
        normalized_env_overrides[key] = value
    if safe_mode is not None and not isinstance(safe_mode, bool):
        raise ValueError("run config safe_mode must be a boolean when provided")

    return RunConfiguration(
        name=name.strip(),
        entry_file=entry_file.strip(),
        mode=mode,
        argv=[item for item in argv if item.strip()],
        working_directory=None if working_directory is None else working_directory.strip(),
        env_overrides=normalized_env_overrides,
        safe_mode=safe_mode,
    )


def parse_run_configs(raw_payloads: list[dict[str, Any]]) -> list[RunConfiguration]:
    """Parse and normalize all valid run configs, skipping invalid entries."""
    parsed: list[RunConfiguration] = []
    seen_names: set[str] = set()
    for payload in raw_payloads:
        try:
            config = parse_run_config(payload)
        except ValueError:
            continue
        if config.name in seen_names:
            continue
        seen_names.add(config.name)
        parsed.append(config)
    return parsed


def upsert_run_config(existing: list[RunConfiguration], updated: RunConfiguration) -> list[RunConfiguration]:
    """Insert or replace run config by name."""
    replaced = False
    output: list[RunConfiguration] = []
    for config in existing:
        if config.name == updated.name:
            output.append(updated)
            replaced = True
            continue
        output.append(config)
    if not replaced:
        output.append(updated)
    return output


def parse_env_overrides_text(raw_text: str) -> dict[str, str]:
    """Parse comma-separated KEY=VALUE entries into env overrides dict."""
    parsed: dict[str, str] = {}
    for segment in raw_text.split(","):
        item = segment.strip()
        if not item:
            continue
        key, separator, value = item.partition("=")
        if not separator:
            raise ValueError("env overrides must be comma-separated KEY=VALUE entries")
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("env override key must be non-empty")
        parsed[normalized_key] = value.strip()
    return parsed


def env_overrides_to_text(env_overrides: Mapping[str, str]) -> str:
    """Serialize env overrides for settings prompt defaults."""
    return ", ".join(f"{key}={value}" for key, value in sorted(env_overrides.items()))
