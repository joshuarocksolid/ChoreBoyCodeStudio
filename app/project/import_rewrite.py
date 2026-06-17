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

from app.persistence.atomic_write import atomic_write_batch
from app.project.file_inventory import iter_python_files
from app.project.import_layout import (
    ProjectImportLayout,
    load_project_import_layout,
    module_name_from_relative_path,
)


@dataclass(frozen=True)
class ImportRewritePreview:
    """Preview information for one file import rewrite."""

    file_path: str
    changed_line_numbers: list[int]
    updated_content: str


def plan_import_rewrites(
    project_root: str,
    old_relative_path: str,
    new_relative_path: str,
    *,
    import_layout: ProjectImportLayout | None = None,
) -> list[ImportRewritePreview]:
    """Plan deterministic import rewrites for Python files impacted by a move/rename."""
    root = Path(project_root).expanduser().resolve()
    layout = import_layout or load_project_import_layout(root)
    old_module = module_name_from_relative_path(layout, old_relative_path)
    new_module = module_name_from_relative_path(layout, new_relative_path)
    if old_module is None or new_module is None or old_module == new_module:
        return []
    previews: list[ImportRewritePreview] = []
    for file_path in iter_python_files(root):
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
    writes = {preview.file_path: preview.updated_content for preview in previews}
    return atomic_write_batch(writes)


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
