"""Jedi Script construction for semantic queries."""
from __future__ import annotations

import time
from typing import Any, Optional

from app.bootstrap.paths import PathInput
from app.intelligence.completion_metrics import log_completion_phase, note_phase
from app.intelligence.jedi_project_cache import get_project
from app.intelligence.jedi_runtime import initialize_jedi_runtime


def create_script(
    *,
    state_root: Optional[PathInput],
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    timings: dict[str, float] | None = None,
) -> Any:
    """Build a Jedi Script for the given source buffer and project context."""
    started_at = time.perf_counter()
    status = initialize_jedi_runtime(state_root)
    runtime_ms = note_phase(timings, "jedi_runtime", started_at)
    log_completion_phase("jedi_runtime", runtime_ms)
    if not status.is_available:
        raise RuntimeError(status.message)

    import jedi

    started_at = time.perf_counter()
    project = None if not project_root else get_project(project_cache, project_root)
    project_ms = note_phase(timings, "jedi_project", started_at)
    log_completion_phase("jedi_project", project_ms)
    started_at = time.perf_counter()
    script = jedi.Script(code=source_text, path=current_file_path, project=project)
    script_ms = note_phase(timings, "jedi_script", started_at)
    log_completion_phase("jedi_script", script_ms)
    return script
