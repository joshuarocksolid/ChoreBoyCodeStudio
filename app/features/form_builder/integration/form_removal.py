"""When a form leaves its folder, Problems names it on the forms that open it."""

from __future__ import annotations

import os
from typing import List, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.rename import open_form_problems
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form
from app.project.path_removed import set_path_removed_listener


def forms_left_behind(project_root: str, removed_ui: str) -> List[Tuple[str, FormDiagnostic]]:
    """FB120 rows for forms in the removed file's folder that open its stem."""

    if not removed_ui.lower().endswith(".ui"):
        return []
    folder = os.path.dirname(os.path.abspath(removed_ui))
    stem = os.path.splitext(os.path.basename(removed_ui))[0]
    return open_form_problems(project_root, folder, stem, OsFileSystem())


def install_form_removal(window: object) -> None:
    """Publish those rows on the shell Problems panel. The tree calls the listener."""

    def on_removed(path: str) -> None:
        project = getattr(window, "_loaded_project", None)
        root = getattr(project, "project_root", None)
        if not root:
            return
        controller = getattr(window, "_problems_controller", None)
        apply = getattr(controller, "apply_lint_diagnostics_result", None)
        grouped: dict[str, List[FormDiagnostic]] = {}
        for ui_path, item in forms_left_behind(str(root), path):
            grouped.setdefault(ui_path, []).append(item)
        for ui_path, items in grouped.items():
            if callable(apply):
                apply(ui_path, code_diagnostics_for_form(ui_path, items))

    set_path_removed_listener(on_removed)
