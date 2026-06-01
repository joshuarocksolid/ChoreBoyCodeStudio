"""Shared helpers for project tree signatures and exclude resolution."""

from __future__ import annotations

from typing import Callable

from app.core import constants
from app.core.models import LoadedProject
from app.project.file_excludes import compute_effective_excludes

# Run/debug sessions write log and manifest files under cbcs/runs/ and cbcs/logs/
# every time the user starts a session. Those churn must NOT trigger the project
# reload cascade, so they are excluded from the structure signature used by polling.
PROJECT_TREE_SIGNATURE_IGNORED_PREFIXES: tuple[str, ...] = (
    f"{constants.PROJECT_META_DIRNAME}/{constants.PROJECT_RUNS_DIRNAME}/",
    f"{constants.PROJECT_META_DIRNAME}/{constants.PROJECT_LOGS_DIRNAME}/",
)


def filter_tree_signature_entries(relative_paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        path
        for path in relative_paths
        if not any(path.startswith(prefix) for prefix in PROJECT_TREE_SIGNATURE_IGNORED_PREFIXES)
    )


def effective_excludes_for(
    loaded_project: LoadedProject,
    *,
    load_effective_exclude_patterns: Callable[[str], list[str]],
) -> list[str]:
    return compute_effective_excludes(
        load_effective_exclude_patterns(loaded_project.project_root),
        loaded_project.metadata.exclude_patterns,
    )
