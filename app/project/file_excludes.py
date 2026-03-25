"""Centralized file/folder exclusion logic for project tree, Quick Open, and search."""

from __future__ import annotations

import fnmatch
from typing import Any, Mapping, Sequence

from app.core import constants


DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    "__pycache__",
    ".git",
    ".hg",
    "node_modules",
    ".venv",
    "venv",
]


def parse_global_exclude_patterns(settings_payload: Mapping[str, Any]) -> list[str]:
    raw = settings_payload.get(constants.UI_FILE_EXCLUDES_SETTINGS_KEY, {})
    if not isinstance(raw, dict):
        return list(DEFAULT_EXCLUDE_PATTERNS)
    patterns_raw = raw.get(constants.UI_FILE_EXCLUDES_PATTERNS_KEY, None)
    if patterns_raw is None:
        return list(DEFAULT_EXCLUDE_PATTERNS)
    if not isinstance(patterns_raw, list):
        return list(DEFAULT_EXCLUDE_PATTERNS)
    patterns: list[str] = []
    for item in patterns_raw:
        if isinstance(item, str) and item.strip():
            patterns.append(item.strip())
    return patterns if patterns else list(DEFAULT_EXCLUDE_PATTERNS)


def compute_effective_excludes(
    global_patterns: Sequence[str],
    project_patterns: Sequence[str],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for pattern in list(global_patterns) + list(project_patterns):
        stripped = pattern.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            result.append(stripped)
    return result


def should_exclude_entry(
    name: str,
    relative_path: str,
    is_directory: bool,
    patterns: Sequence[str],
) -> bool:
    for pattern in patterns:
        if "/" in pattern:
            if fnmatch.fnmatch(relative_path, pattern):
                return True
        else:
            if fnmatch.fnmatch(name, pattern):
                return True
    return False


def should_exclude_name(name: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        if "/" not in pattern and fnmatch.fnmatch(name, pattern):
            return True
    return False
