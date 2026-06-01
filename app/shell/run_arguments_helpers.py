"""Pure helpers for run-with-arguments UI (preview text, path normalization, validation)."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from app.core.errors import AppValidationError
from app.project.run_configs import env_overrides_to_text, parse_env_overrides_text
from app.shell.run_config_controller import tokenize_argv_text


def normalize_entry_path_for_project(
    entry_path: str,
    *,
    project_root: str | None,
) -> str:
    """Return a project-relative path when ``entry_path`` lies under ``project_root``."""

    text = (entry_path or "").strip()
    if not text or project_root is None:
        return text
    try:
        resolved_entry = Path(text).expanduser().resolve()
        resolved_root = Path(project_root).expanduser().resolve()
        return resolved_entry.relative_to(resolved_root).as_posix()
    except ValueError:
        return text


def format_command_preview_lines(
    *,
    entry_file: str,
    argv_tokens: Sequence[str],
    working_directory: str | None,
    project_root: str | None,
    env_overrides: Mapping[str, str],
) -> list[str]:
    """Build human-readable summary lines for the run preview block."""

    entry_display = (entry_file or "").strip() or "(not set)"
    lines = [f"Entry:  {entry_display}"]

    if argv_tokens:
        argv_display = ", ".join(repr(token) for token in argv_tokens)
        lines.append(f"Args:   {argv_display}")
    else:
        lines.append("Args:   (none)")

    cwd_text = (working_directory or "").strip()
    if cwd_text:
        lines.append(f"Cwd:    {cwd_text}")
    elif project_root:
        lines.append(f"Cwd:    {project_root}  (project root)")
    else:
        lines.append("Cwd:    (project root)")

    if env_overrides:
        env_display = ", ".join(f"{key}={value}" for key, value in sorted(env_overrides.items()))
        lines.append(f"Env:    {env_display}")

    return lines


def try_parse_argv_text(argv_text: str) -> tuple[list[str] | None, str | None]:
    """Parse argv text; return ``(tokens, None)`` or ``(None, error_message)``."""

    text = argv_text or ""
    if not text.strip():
        return [], None
    try:
        return tokenize_argv_text(text), None
    except AppValidationError as exc:
        return None, str(exc)


def try_parse_env_text(env_text: str) -> tuple[dict[str, str] | None, str | None]:
    """Parse env overrides text; return ``(mapping, None)`` or ``(None, error_message)``."""

    text = env_text or ""
    if not text.strip():
        return {}, None
    try:
        return parse_env_overrides_text(text), None
    except ValueError as exc:
        return None, f"Invalid environment overrides: {exc}"


def can_submit_run_invocation(
    *,
    entry_file: str,
    argv_text: str,
    env_text: str,
) -> tuple[bool, str | None]:
    """Return whether Run/Save actions should be enabled and an optional error message."""

    if not (entry_file or "").strip():
        return False, "Entry file is required."

    _argv_tokens, argv_error = try_parse_argv_text(argv_text)
    if argv_error is not None:
        return False, argv_error

    _env_mapping, env_error = try_parse_env_text(env_text)
    if env_error is not None:
        return False, env_error

    return True, None


def join_argv_for_display(argv: Sequence[str]) -> str:
    """Best-effort reverse of :func:`tokenize_argv_text` for display.

    Tokens containing whitespace are quoted with double quotes; embedded double quotes are
    escaped. Round-trip-equivalent for typical argv values; not a full shell escape.
    """

    parts: list[str] = []
    for token in argv:
        text = str(token)
        if not text:
            parts.append('""')
            continue
        needs_quoting = any(ch.isspace() for ch in text) or '"' in text or "'" in text
        if needs_quoting:
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{escaped}"')
        else:
            parts.append(text)
    return " ".join(parts)
