"""Run-configuration parsing and serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.core import constants


@dataclass(frozen=True)
class RunConfiguration:
    """Normalized named run configuration."""

    name: str
    entry_file: str
    mode: str
    argv: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entry_file": self.entry_file,
            "mode": self.mode,
            "argv": list(self.argv),
        }


def parse_run_config(raw_payload: Mapping[str, Any]) -> RunConfiguration:
    """Validate one run-config payload into normalized model."""
    name = raw_payload.get("name", "")
    entry_file = raw_payload.get("entry_file", "")
    mode = raw_payload.get("mode", constants.RUN_MODE_PYTHON_SCRIPT)
    argv = raw_payload.get("argv", [])

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

    return RunConfiguration(
        name=name.strip(),
        entry_file=entry_file.strip(),
        mode=mode,
        argv=[item for item in argv if item.strip()],
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
