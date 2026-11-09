"""Project-tree and start-screen entry for Adopt this form."""

from __future__ import annotations

import os
from typing import Any, List

from app.qt.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT, UI_EDITOR_FONT_SIZE_DEFAULT
from app.features.form_builder.engine.project.adopt_offer import prepare_adoption
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError, relative_posix
from app.features.form_builder.engine.project.loaders import scan_ui_loaders
from app.features.form_builder.engine.ui4.reader import UiReadError
from app.features.form_builder.integration.adopt_dialog import (
    _DEFAULT_HINT,
    adoption_hint,
    show_adopt_dialog,
)
from app.shell.theme_tokens import tokens_from_palette

START_ENTRIES = (
    {
        "id": "adopt-loaded-form",
        "title": "Adopt a form your code already loads",
        "action": "adopt_form",
    },
)


def adopt_from_tree(window: Any, ui_path: str) -> None:
    """Adopt ``ui_path``, generate its Python, and show the suggestion."""
    project = getattr(window, "_loaded_project", None)
    root = getattr(project, "project_root", None)
    if not root:
        QMessageBox.information(window, "Adopt this form", "Open a project before adopting a form.")
        return
    try:
        before, after = prepare_adoption(str(root), ui_path)
    except ProjectOpError as exc:
        QMessageBox.warning(window, "Adopt this form", str(exc))
        return
    except (OSError, UnicodeError, ValueError, UiReadError) as exc:
        QMessageBox.warning(window, "Adopt this form", str(exc))
        return
    show_adopt_dialog(
        window,
        before=before,
        after=after,
        tokens=_tokens(window),
        hint=_hint(str(root), ui_path),
        editor_font=_editor_font(window),
    )


def adopt_from_start(window: Any) -> None:
    """The New form card: adopt the one form the code loads, else let the user pick."""
    project = getattr(window, "_loaded_project", None)
    root = getattr(project, "project_root", None)
    if not root:
        QMessageBox.information(window, "Adopt this form", "Open a project before adopting a form.")
        return
    found = _loaded_forms(str(root))
    if len(found) == 1:
        adopt_from_tree(window, found[0])
        return
    start = found[0] if found else str(root)
    picked, _filter = QFileDialog.getOpenFileName(
        window, "Adopt a form your code already loads", start, "Qt forms (*.ui)"
    )
    if picked:
        adopt_from_tree(window, picked)


def _loaded_forms(root: str) -> List[str]:
    """Existing .ui files named literally by a runtime loader call in the project."""
    found: List[str] = []
    for site in scan_ui_loaders(root):
        if not site.ui_literal:
            continue
        for base in (os.path.dirname(site.path), root):
            candidate = os.path.normpath(os.path.join(base, site.ui_literal))
            if os.path.isfile(candidate) and candidate not in found:
                found.append(candidate)
                break
    return found


def _hint(root: str, ui_path: str) -> str:
    scope = scope_for(ui_path, root, OsFileSystem())
    if not scope.generated_path or not scope.window_path or not scope.project_root:
        return _DEFAULT_HINT
    return adoption_hint(
        relative_posix(scope.generated_path, scope.project_root),
        relative_posix(scope.window_path, scope.project_root),
    )


def _editor_font(window: Any) -> tuple[str, int]:
    family = getattr(window, "_editor_font_family", "") or UI_EDITOR_FONT_FAMILY_DEFAULT
    size = getattr(window, "_editor_font_size", 0) or UI_EDITOR_FONT_SIZE_DEFAULT
    return str(family), int(size)


def _tokens(window: Any):
    getter = getattr(window, "current_theme_tokens", None)
    if callable(getter):
        return getter()
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("No application palette is available for the adopt dialog.")
    return tokens_from_palette(app.palette())
