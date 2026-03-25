"""Project-local dependency manifest for terminal-free package management."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional

from app.core import constants
from app.persistence.atomic_write import atomic_write_text

DEPENDENCY_MANIFEST_FILENAME = "dependencies.json"
DEPENDENCY_MANIFEST_SCHEMA_VERSION = 1

CLASSIFICATION_PURE_PYTHON = "pure_python"
CLASSIFICATION_NATIVE_EXTENSION = "native_extension"
CLASSIFICATION_RUNTIME = "runtime"

STATUS_ACTIVE = "active"
STATUS_REMOVED = "removed"

SOURCE_WHEEL = "wheel"
SOURCE_ZIP = "zip"
SOURCE_FOLDER = "folder"
SOURCE_RUNTIME = "runtime"


@dataclass
class DependencyEntry:
    """One tracked dependency in the project manifest."""

    name: str
    version: str
    source: str  # wheel | zip | folder | runtime
    classification: str  # pure_python | native_extension | runtime
    status: str = STATUS_ACTIVE  # active | removed
    added_at: str = ""
    vendor_path: str = ""  # relative path under vendor/
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyEntry":
        return cls(
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            source=str(data.get("source", "")),
            classification=str(data.get("classification", "")),
            status=str(data.get("status", STATUS_ACTIVE)),
            added_at=str(data.get("added_at", "")),
            vendor_path=str(data.get("vendor_path", "")),
            notes=str(data.get("notes", "")),
        )


@dataclass
class DependencyManifest:
    """Typed representation of cbcs/dependencies.json."""

    schema_version: int = DEPENDENCY_MANIFEST_SCHEMA_VERSION
    entries: list[DependencyEntry] = field(default_factory=list)

    def active_entries(self) -> list[DependencyEntry]:
        return [e for e in self.entries if e.status == STATUS_ACTIVE]

    def removed_entries(self) -> list[DependencyEntry]:
        return [e for e in self.entries if e.status == STATUS_REMOVED]

    def find_by_name(self, name: str) -> Optional[DependencyEntry]:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def add_entry(self, entry: DependencyEntry) -> None:
        existing = self.find_by_name(entry.name)
        if existing is not None:
            self.entries.remove(existing)
        if not entry.added_at:
            entry.added_at = datetime.now(timezone.utc).isoformat()
        self.entries.append(entry)

    def remove_entry(self, name: str) -> bool:
        entry = self.find_by_name(name)
        if entry is None:
            return False
        entry.status = STATUS_REMOVED
        return True

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyManifest":
        return cls(
            schema_version=int(data.get("schema_version", DEPENDENCY_MANIFEST_SCHEMA_VERSION)),
            entries=[DependencyEntry.from_dict(e) for e in data.get("entries", [])],
        )


def dependency_manifest_path(project_root: str) -> Path:
    """Return the canonical path to cbcs/dependencies.json."""
    return Path(project_root).expanduser().resolve() / constants.PROJECT_META_DIRNAME / DEPENDENCY_MANIFEST_FILENAME


def load_dependency_manifest(project_root: str) -> DependencyManifest:
    """Load the dependency manifest or return an empty one if missing."""
    manifest_path = dependency_manifest_path(project_root)
    if not manifest_path.exists():
        return DependencyManifest()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return DependencyManifest.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return DependencyManifest()


def save_dependency_manifest(project_root: str, manifest: DependencyManifest) -> Path:
    """Persist the dependency manifest atomically."""
    manifest_path = dependency_manifest_path(project_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n"
    return atomic_write_text(manifest_path, content)
