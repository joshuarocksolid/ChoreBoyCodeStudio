"""Component library manifest persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class ComponentManifestEntry:
    """Serialized manifest entry for one component."""

    name: str
    file_name: str
    root_class_name: str
    root_object_name: str


def load_component_manifest(components_dir: Path) -> dict[str, ComponentManifestEntry]:
    """Load component manifest entries keyed by component name."""
    manifest_path = components_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_entries = payload.get("components")
    if not isinstance(raw_entries, list):
        return {}
    entries: dict[str, ComponentManifestEntry] = {}
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        entry = _parse_manifest_entry(raw)
        if entry is None:
            continue
        entries[entry.name] = entry
    return entries


def save_component_manifest(components_dir: Path, entries: dict[str, ComponentManifestEntry]) -> None:
    """Persist manifest entries in deterministic order."""
    components_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = components_dir / MANIFEST_FILENAME
    serialized_entries = []
    for name in sorted(entries):
        entry = entries[name]
        serialized_entries.append(
            {
                "name": entry.name,
                "file_name": entry.file_name,
                "root_class_name": entry.root_class_name,
                "root_object_name": entry.root_object_name,
            }
        )
    payload = {
        "version": 1,
        "components": serialized_entries,
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_manifest_entry(payload: dict[str, Any]) -> ComponentManifestEntry | None:
    name = payload.get("name")
    file_name = payload.get("file_name")
    root_class_name = payload.get("root_class_name")
    root_object_name = payload.get("root_object_name")
    if not all(isinstance(value, str) and value.strip() for value in (name, file_name, root_class_name, root_object_name)):
        return None
    return ComponentManifestEntry(
        name=name.strip(),
        file_name=file_name.strip(),
        root_class_name=root_class_name.strip(),
        root_object_name=root_object_name.strip(),
    )
