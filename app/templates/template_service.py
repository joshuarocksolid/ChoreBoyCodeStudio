"""Built-in template discovery and project materialization."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from app.bootstrap.paths import resolve_app_root
from app.core import constants
from app.core.errors import AppValidationError
from app.project.project_manifest import build_default_project_manifest_payload

TEMPLATE_METADATA_FILENAME = "template.json"
LEGACY_HIDDEN_METADATA_DIRS = (
    ".cbcs",
    ".choreboy_code_studio",
    ".choreboy_code_studio_state",
)


@dataclass(frozen=True)
class TemplateMetadata:
    """Metadata describing one built-in project template."""

    template_id: str
    display_name: str
    description: str
    template_version: int
    source_path: str


class TemplateService:
    """Discovers and materializes built-in project templates."""

    def __init__(self, templates_root: str | None = None) -> None:
        root = Path(templates_root).expanduser().resolve() if templates_root else resolve_app_root() / "templates"
        self._templates_root = root

    @property
    def templates_root(self) -> Path:
        return self._templates_root

    def list_templates(self) -> list[TemplateMetadata]:
        """List discovered templates sorted by template id."""
        if not self._templates_root.exists():
            return []

        templates: list[TemplateMetadata] = []
        for template_dir in sorted(path for path in self._templates_root.iterdir() if path.is_dir()):
            metadata_path = template_dir / TEMPLATE_METADATA_FILENAME
            if not metadata_path.exists():
                continue
            templates.append(self._load_template_metadata(metadata_path, template_dir))
        return templates

    def materialize_template(
        self,
        *,
        template_id: str,
        destination_path: str | Path,
        project_name: str,
    ) -> Path:
        """Copy template files into destination and inject project metadata."""
        template = self._find_template(template_id)
        destination = Path(destination_path).expanduser().resolve()
        if destination.exists():
            if any(destination.iterdir()):
                raise AppValidationError(f"Destination is not empty: {destination}")
        else:
            destination.mkdir(parents=True, exist_ok=False)

        source_path = Path(template.source_path)
        shutil.copytree(
            source_path,
            destination,
            dirs_exist_ok=True,
            ignore=self._ignore_legacy_hidden_metadata_dirs,
        )
        self._inject_project_manifest(
            destination=destination,
            project_name=project_name,
            template_id=template.template_id,
        )
        return destination

    @staticmethod
    def _ignore_legacy_hidden_metadata_dirs(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in LEGACY_HIDDEN_METADATA_DIRS}

    def _find_template(self, template_id: str) -> TemplateMetadata:
        for template in self.list_templates():
            if template.template_id == template_id:
                return template
        raise AppValidationError(f"Unknown template_id: {template_id}")

    def _load_template_metadata(self, metadata_path: Path, template_dir: Path) -> TemplateMetadata:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AppValidationError(f"Invalid template metadata format: {metadata_path}")

        return TemplateMetadata(
            template_id=_require_non_empty_string(payload, "template_id"),
            display_name=_require_non_empty_string(payload, "display_name"),
            description=_require_non_empty_string(payload, "description"),
            template_version=_require_int(payload, "template_version"),
            source_path=str(template_dir.resolve()),
        )

    def _inject_project_manifest(self, *, destination: Path, project_name: str, template_id: str) -> None:
        if not project_name.strip():
            raise AppValidationError("project_name must be a non-empty string.")
        manifest_path = destination / constants.PROJECT_META_DIRNAME / constants.PROJECT_MANIFEST_FILENAME
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = build_default_project_manifest_payload(
                project_name=project_name.strip(),
                default_entry="main.py",
                working_directory=".",
                template=template_id,
            )
        except ValueError as exc:
            raise AppValidationError(str(exc)) from exc
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_non_empty_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise AppValidationError(f"{field_name} must be a non-empty string.")
    return value


def _require_int(payload: dict[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise AppValidationError(f"{field_name} must be an integer.")
    return value
