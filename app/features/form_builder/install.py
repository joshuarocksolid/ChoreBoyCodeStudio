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
    """Register the ``.ui`` provider and the New form tab.

    One provider id owns ``.ui`` files. ``RememberingFormTabProvider`` is that
    provider and records recent forms. ``attach_new_form`` adds the virtual tab
    and the callback menus read after this install.
    """
    from app.features.form_builder.integration.new_form import (
        RememberingFormTabProvider,
        attach_new_form,
    )

    ctx.w._tab_content_registry.register(RememberingFormTabProvider())
    attach_new_form(ctx.w)


__all__ = ["KILL_SWITCH_ENV", "PROVIDER_ID", "form_builder_enabled", "install_form_builder"]
