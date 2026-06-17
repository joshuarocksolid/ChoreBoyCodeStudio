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


_SUMMARY_PLACEHOLDER = "Complete the fields below to preview the run."
_SUMMARY_SEPARATOR = " \u00b7 "


def format_command_summary_strip(
    *,
    entry_file: str,
    argv_tokens: Sequence[str] | None,
    working_directory: str | None,
    project_root: str | None,
    env_overrides: Mapping[str, str],
    argv_error: str | None = None,
) -> tuple[str, str, str]:
    """Build a one-line run summary, multiline detail tooltip, and preview state.

    Returns ``(summary_text, detail_tooltip, state)`` where ``state`` is one of
    ``ready``, ``incomplete``, or ``error``.
    """

    entry = (entry_file or "").strip()
    if not entry or argv_error is not None:
        state = "error" if argv_error is not None else "incomplete"
        return _SUMMARY_PLACEHOLDER, "", state

    argv_display = join_argv_for_display(argv_tokens or [])
    parts = [entry]
    if argv_display:
        parts.append(argv_display)

    cwd_text = (working_directory or "").strip()
    if cwd_text:
        parts.append(f"cwd: {cwd_text}")
    else:
        parts.append("cwd: project root")

    env_count = len(env_overrides)
    if env_count == 1:
        parts.append("env: 1 var")
    elif env_count > 1:
        parts.append(f"env: {env_count} vars")

    summary = _SUMMARY_SEPARATOR.join(parts)
    detail = "\n".join(
        format_command_preview_lines(
            entry_file=entry,
            argv_tokens=argv_tokens or [],
            working_directory=working_directory,
            project_root=project_root,
            env_overrides=env_overrides,
        )
    )
    return summary, detail, "ready"


def format_overrides_collapsed_summary(
    *,
    working_directory: str | None,
    project_root: str | None,
    env_overrides: Mapping[str, str],
) -> str:
    """One-line summary for the collapsed overrides disclosure row."""

    cwd_text = (working_directory or "").strip()
    if cwd_text:
        cwd_part = cwd_text
    elif project_root:
        cwd_part = "project root"
    else:
        cwd_part = "project root"

    env_count = len(env_overrides)
    if env_count == 0:
        env_part = "no env overrides"
    elif env_count == 1:
        env_part = "1 env var"
    else:
        env_part = f"{env_count} env vars"

    return f"{cwd_part}{_SUMMARY_SEPARATOR}{env_part}"


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
    env_text: str = "",
    env_overrides: Mapping[str, str] | None = None,
) -> tuple[bool, str | None]:
    """Return whether Run/Save actions should be enabled and an optional error message."""

    if not (entry_file or "").strip():
        return False, "Entry file is required."

    _argv_tokens, argv_error = try_parse_argv_text(argv_text)
    if argv_error is not None:
        return False, argv_error

    if env_overrides is not None:
        return True, None

    _env_mapping, env_error = try_parse_env_text(env_text)
    if env_error is not None:
        return False, env_error

    return True, None


def collect_run_invocation_fields(
    *,
    entry_file: str,
    argv_text: str,
    env_overrides: Mapping[str, str],
    working_directory: str | None,
) -> tuple[dict[str, object] | None, str | None]:
    """Validate run fields for live preview and submit; returns field dict or error message."""

    if not (entry_file or "").strip():
        return None, "Entry file is required."

    argv_tokens, argv_error = try_parse_argv_text(argv_text)
    if argv_error is not None:
        return None, argv_error

    can_submit, submit_error = can_submit_run_invocation(
        entry_file=entry_file,
        argv_text=argv_text,
        env_overrides=env_overrides,
    )
    if not can_submit:
        return None, submit_error

    return {
        "entry_file": entry_file.strip(),
        "argv_tokens": argv_tokens or [],
        "argv_text": argv_text.strip(),
        "working_directory": (working_directory or "").strip() or None,
        "env_overrides": dict(env_overrides),
    }, None


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
