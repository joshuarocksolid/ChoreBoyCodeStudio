"""Project-tree and start-screen entry for Adopt this form."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QApplication, QMessageBox

from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT, UI_EDITOR_FONT_SIZE_DEFAULT
from app.features.form_builder.engine.project.adopt_offer import prepare_adoption
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError, relative_posix
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
