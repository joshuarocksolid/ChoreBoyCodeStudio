"""Minimal `.editorconfig` reader for indentation-related settings."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from pathlib import Path


@dataclass(frozen=True)
class EditorConfigIndentation:
    """Indentation settings resolved from `.editorconfig`."""

    indent_style: str
    indent_size: int
    tab_width: int


def resolve_editorconfig_indentation(file_path: str, *, project_root: str | None = None) -> EditorConfigIndentation | None:
    """Resolve nearest `.editorconfig` indentation values for target file."""
    target = Path(file_path).expanduser().resolve()
    if not target.exists():
        return None
    search_stop = None if project_root is None else Path(project_root).expanduser().resolve()
    editorconfig_path = _find_nearest_editorconfig(target.parent, stop_dir=search_stop)
    if editorconfig_path is None:
        return None
    entries = _parse_editorconfig(editorconfig_path)
    if not entries:
        return None

    relative_target = target.name
    if search_stop is not None:
        try:
            relative_target = target.relative_to(search_stop).as_posix()
        except ValueError:
            relative_target = target.name

    resolved: dict[str, str] = {}
    for pattern, values in entries:
        if pattern != "*" and not fnmatch.fnmatch(relative_target, pattern):
            continue
        resolved.update(values)

    indent_style = resolved.get("indent_style")
    indent_size_raw = resolved.get("indent_size")
    tab_width_raw = resolved.get("tab_width")
    if indent_style not in {"tabs", "spaces"}:
        return None
    if indent_size_raw is None:
        return None
    try:
        indent_size = int(indent_size_raw)
    except ValueError:
        return None
    if tab_width_raw is None:
        tab_width = indent_size
    else:
        try:
            tab_width = int(tab_width_raw)
        except ValueError:
            tab_width = indent_size
    return EditorConfigIndentation(indent_style=indent_style, indent_size=max(1, indent_size), tab_width=max(1, tab_width))


def _find_nearest_editorconfig(start_dir: Path, *, stop_dir: Path | None) -> Path | None:
    current = start_dir
    while True:
        candidate = current / ".editorconfig"
        if candidate.is_file():
            return candidate
        if stop_dir is not None and current == stop_dir:
            return None
        if current.parent == current:
            return None
        current = current.parent


def _parse_editorconfig(editorconfig_path: Path) -> list[tuple[str, dict[str, str]]]:
    entries: list[tuple[str, dict[str, str]]] = [("*", {})]
    current_pattern = "*"
    try:
        lines = editorconfig_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_pattern = line[1:-1].strip() or "*"
            entries.append((current_pattern, {}))
            continue
        if "=" not in line:
            continue
        key, value = [part.strip().lower() for part in line.split("=", maxsplit=1)]
        if key not in {"indent_style", "indent_size", "tab_width"}:
            continue
        entries[-1][1][key] = value
    return entries
