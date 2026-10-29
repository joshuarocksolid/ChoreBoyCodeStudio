"""Form > Form settings… (UX-FSET-001): select the form, open the inspector, open Code and focus Author.

The item replaces the command table's own "Form settings…" row. The form
settings are groups in the form inspector, so nothing opens a dialog. The
inspector's widgets are found by the object names its groups set.
"""

from __future__ import annotations

from typing import Any

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.form_menu_ext import FormMenuItem
from app.features.form_builder.qtside.inspector import TabId
from app.features.form_builder.qtside.inspector.editors.form_settings import CODE
from app.qt.QtWidgets import QLineEdit, QWidget


def reveal(surface: Any) -> bool:
    """Select the form, open the inspector, open Code and focus Author. True when focus landed."""
    session = surface.session
    workbench = surface.workbench
    session.selection.clear(source=SelectionSource.PROGRAM)
    workbench.focus_inspector_tab(TabId.PROPERTIES)
    inspector = workbench.inspector
    inspector.flush()
    inspector.set_group_expanded(CODE, True)
    inspector.flush()
    body = inspector.findChild(QWidget, "formBuilder.formSettings.code")
    target = body.findChild(QLineEdit, "formBuilder.formSetting.author.edit") if body is not None else None
    if target is None:
        return False
    target.setFocus()
    target.selectAll()
    return True


def _run(surface: Any) -> None:
    reveal(surface)


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(FormMenuItem("form.action.formSettings", ("Form settings\u2026",), _run))
