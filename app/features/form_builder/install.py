"""Feature registration (CONTRACTS.md sections 1 and 11).

Module-level imports stay on the standard library, ``typing``, and
``app.bootstrap.qt_binding_choice``. Qt and the tab provider are imported
inside ``install_form_builder``. ``form_builder_enabled`` does not import Qt.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from app.bootstrap.qt_binding_choice import select_binding

if TYPE_CHECKING:
    from app.shell.shell_composition_context import ShellCompositionContext

#: ``CBCS_FORM_BUILDER=0`` hides the feature even on PySide6.
KILL_SWITCH_ENV = "CBCS_FORM_BUILDER"

#: Tab-content provider id registered by this feature.
PROVIDER_ID = "form-builder.ui"


def form_builder_enabled() -> bool:
    """True when the kill switch is off and the active binding is PySide6.

    ``select_binding`` is the import-free equivalent of ``IS_QT6``. An
    ``ImportError`` means no binding can be chosen, so the feature stays off.
    """
    if os.environ.get(KILL_SWITCH_ENV, "1") == "0":
        return False
    try:
        return select_binding() == "PySide6"
    except ImportError:
        return False


def install_form_builder(ctx: "ShellCompositionContext") -> None:
    """Register the ``.ui`` provider, the New form tab, and the run, package
    and adopt hooks.

    Qt and shell imports stay inside this function so importing the module
    on PySide2 does not load a binding. ``form_builder_enabled`` is the gate.
    ``RememberingFormTabProvider`` owns ``.ui`` files and records recent forms.
    Sessions start when a tab opens.
    """
    from app.features.form_builder.integration.adopt_flow import (
        START_ENTRIES,
        adopt_from_start,
        adopt_from_tree,
    )
    from app.features.form_builder.integration.new_form import (
        RememberingFormTabProvider,
        attach_new_form,
        bind_adopt_entry,
    )
    from app.features.form_builder.engine.shell_commands import shortcut_rows
    from app.features.form_builder.integration.keys_ext import extra_shortcut_rows
    from app.features.form_builder.integration.form_menu import register_form_menu
    from app.packaging.form_files import save_packaged_form
    from app.shell.shell_composition_context import bind_private_attrs
    from app.shell.shortcut_preferences import ShortcutCommand, register_shortcut_commands

    window = ctx.w

    def save_form(ui_path: str) -> str:
        project = getattr(window, "_loaded_project", None)
        root = getattr(project, "project_root", None)
        if not root:
            return "Open a project before saving the form."
        return save_packaged_form(str(root), ui_path)

    def adopt(ui_path: str) -> None:
        adopt_from_tree(window, ui_path)

    def go_to_widget() -> bool:
        """Ctrl+R in a form tab. False lets the shell run Go to Symbol."""
        from app.features.form_builder.integration.surface import FormSurface

        surface = getattr(window, "_form_undo_surface", None)
        if not isinstance(surface, FormSurface) or not surface.isVisible():
            return False
        return surface.go_to_widget()

    window._tab_content_registry.register(RememberingFormTabProvider())
    attach_new_form(window)
    bind_adopt_entry(lambda: adopt_from_start(window))
    register_shortcut_commands(
        tuple(
            ShortcutCommand(action_id, label, shortcut, category)
            for action_id, label, shortcut, category in shortcut_rows() + extra_shortcut_rows()
        )
    )
    _refresh_shortcut_maps(window)
    register_form_menu(window)
    bind_private_attrs(
        window,
        {
            "_form_builder_save_form": save_form,
            "_form_builder_adopt_form": adopt,
            "_form_builder_go_to_widget": go_to_widget,
            "_form_builder_start_entries": START_ENTRIES,
        },
    )
    _reset_preview_on_quit()


def _refresh_shortcut_maps(window: object) -> None:
    """Re-read keybindings now that form rows are known ids."""
    from app.shell.shortcut_preferences import (
        build_effective_shortcut_map,
        parse_shortcut_overrides,
    )

    service = getattr(window, "_settings_service", None)
    load_global = getattr(service, "load_global", None)
    if not callable(load_global):
        return
    overrides = parse_shortcut_overrides(load_global())
    setattr(window, "_shortcut_overrides", overrides)
    setattr(window, "_effective_shortcuts", build_effective_shortcut_map(overrides))


def _reset_preview_on_quit() -> None:
    """The shell cannot import this feature. The quit hook lives here."""
    if getattr(_reset_preview_on_quit, "done", False):
        return
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    from app.features.form_builder.qtside.preview.pool import PreviewPool

    app.aboutToQuit.connect(PreviewPool.reset_shared)
    _reset_preview_on_quit.done = True  # type: ignore[attr-defined]


__all__ = ["KILL_SWITCH_ENV", "PROVIDER_ID", "form_builder_enabled", "install_form_builder"]
