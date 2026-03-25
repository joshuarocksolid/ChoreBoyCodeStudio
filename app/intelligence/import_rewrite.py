"""Python import rewrite helpers for file moves and renames.

This module intentionally stays narrow:
- deterministic move/rename rewrite previews only
- no general organize-imports behavior
- no claim of semantic proof beyond the current text rewrite contract

Longer term, the trusted-semantics/refactor lane should replace this regex path
with structural import rewrites. The Black/isort organize-imports flow lives in
`app.python_tools`, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.core import constants
from app.persistence.atomic_write import atomic_write_text


@dataclass(frozen=True)
class ImportRewritePreview:
    """Preview information for one file import rewrite."""

    file_path: str
    changed_line_numbers: list[int]
    updated_content: str


def plan_import_rewrites(project_root: str, old_relative_path: str, new_relative_path: str) -> list[ImportRewritePreview]:
    """Plan deterministic import rewrites for Python files impacted by a move/rename."""
    old_module = _module_name_from_relative_path(old_relative_path)
    new_module = _module_name_from_relative_path(new_relative_path)
    if old_module is None or new_module is None or old_module == new_module:
        return []

    root = Path(project_root).expanduser().resolve()
    previews: list[ImportRewritePreview] = []
    for file_path in sorted(root.rglob("*.py")):
        if constants.PROJECT_META_DIRNAME in file_path.parts:
            continue
        original_text = file_path.read_text(encoding="utf-8")
        rewritten_text, changed_lines = _rewrite_import_lines(original_text, old_module, new_module)
        if rewritten_text == original_text:
            continue
        previews.append(
            ImportRewritePreview(
                file_path=str(file_path.resolve()),
                changed_line_numbers=changed_lines,
                updated_content=rewritten_text,
            )
        )
    return previews


def apply_import_rewrites(previews: list[ImportRewritePreview]) -> list[str]:
    """Apply planned rewrites with rollback on write failures."""
    original_payloads: dict[str, str] = {}
    updated_paths: list[str] = []
    try:
        for preview in previews:
            target = Path(preview.file_path).expanduser().resolve()
            original_payloads[preview.file_path] = target.read_text(encoding="utf-8")
            atomic_write_text(target, preview.updated_content)
            updated_paths.append(preview.file_path)
    except OSError:
        for file_path, payload in original_payloads.items():
            atomic_write_text(file_path, payload)
        raise
    return updated_paths


def _module_name_from_relative_path(relative_path: str) -> str | None:
    normalized = relative_path.replace("\\", "/")
    if not normalized.endswith(".py"):
        return None
    no_suffix = normalized[:-3]
    if no_suffix.endswith("/__init__"):
        no_suffix = no_suffix[: -len("/__init__")]
    parts = [part for part in no_suffix.split("/") if part]
    if not parts:
        return None
    return ".".join(parts)


def _rewrite_import_lines(content: str, old_module: str, new_module: str) -> tuple[str, list[int]]:
    changed_lines: list[int] = []
    rewritten_lines: list[str] = []
    pattern = re.compile(rf"\b{re.escape(old_module)}(?=\.|\b)")
    for line_number, line in enumerate(content.splitlines(keepends=True), start=1):
        stripped = line.lstrip()
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            rewritten_lines.append(line)
            continue
        rewritten_line = pattern.sub(new_module, line)
        if rewritten_line != line:
            changed_lines.append(line_number)
        rewritten_lines.append(rewritten_line)
    return ("".join(rewritten_lines), changed_lines)
