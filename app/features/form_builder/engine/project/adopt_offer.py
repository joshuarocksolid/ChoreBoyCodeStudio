"""Adopt a form and build the setupUi suggestion. User Python is not rewritten."""

from __future__ import annotations

import os
from typing import Optional, Tuple

from app.features.form_builder.engine.project.adoption import adopt_form, scope_for
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.loaders import suggestion_text
from app.features.form_builder.engine.project.packaging import save_form_now


def prepare_adoption(
    project_root: str,
    ui_path: str,
    fs: Optional[OsFileSystem] = None,
) -> Tuple[str, str]:
    """Record the form when it is outside ``forms/``, generate, and return the suggestion.

    A form already under ``forms/`` is generated without a new manifest entry.
    """
    files = fs if fs is not None else OsFileSystem()
    root = os.path.abspath(project_root)
    try:
        adopt_form(root, ui_path, files)
    except ProjectOpError as exc:
        if "already in forms" not in str(exc):
            raise
    written = save_form_now(root, ui_path, files)
    if not written.text_written:
        detail = written.diagnostics[0].message if written.diagnostics else "The form could not be generated."
        raise ProjectOpError(detail)
    scope = scope_for(ui_path, root, files)
    return suggestion_text(root, ui_path, scope)
