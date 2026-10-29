"""Form > Form settings… (UX-FSET-001): select the form, open the inspector, open Code and focus Author.

The item replaces the command table's own "Form settings…" row. The form
settings are groups in the form inspector, so nothing opens a dialog.
"""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.form_menu_ext import FormMenuItem


def _run(surface: Any) -> None:
    from app.features.form_builder.qtside.inspector.editors.form_settings import reveal

    reveal(surface)


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(FormMenuItem("form.action.formSettings", ("Form settings…",), _run))
