"""Help-only example project materialization service.

This service is intentionally separate from the New Project template system so
that the example project is only exposed through the Help menu and never
appears in the template picker.
"""

from __future__ import annotations

from pathlib import Path

from app.bootstrap.paths import resolve_app_root
from app.templates.template_service import TemplateService

EXAMPLE_PROJECTS_DIRNAME = "example_projects"
SHOWCASE_TEMPLATE_ID = "crud_showcase"


class ExampleProjectService:
    """Discovers and materializes bundled example projects."""

    def __init__(self, examples_root: str | Path | None = None) -> None:
        root = (
            Path(examples_root).expanduser().resolve()
            if examples_root
            else resolve_app_root() / EXAMPLE_PROJECTS_DIRNAME
        )
        self._delegate = TemplateService(templates_root=str(root))

    def materialize_showcase(
        self,
        destination_path: str | Path,
        project_name: str,
    ) -> Path:
        """Copy the CRUD showcase example into *destination_path* and inject project metadata."""
        return self._delegate.materialize_template(
            template_id=SHOWCASE_TEMPLATE_ID,
            destination_path=destination_path,
            project_name=project_name,
        )
