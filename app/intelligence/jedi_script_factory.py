"""Jedi Script construction for semantic queries."""
from __future__ import annotations

from typing import Any, Optional

from app.bootstrap.paths import PathInput
from app.intelligence.jedi_project_cache import get_project
from app.intelligence.jedi_runtime import initialize_jedi_runtime


def create_script(
    *,
    state_root: Optional[PathInput],
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    project_root: str | None,
    current_file_path: str,
    source_text: str,
) -> Any:
    """Build a Jedi Script for the given source buffer and project context."""
    status = initialize_jedi_runtime(state_root)
    if not status.is_available:
        raise RuntimeError(status.message)

    import jedi

    project = None if not project_root else get_project(project_cache, project_root)
    return jedi.Script(code=source_text, path=current_file_path, project=project)
