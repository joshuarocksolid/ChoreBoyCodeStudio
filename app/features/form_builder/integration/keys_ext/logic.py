"""Shift+F12 lists uses of the focused name. Enter on a logic row is the row's own key."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.qtside.logic_panel.open import show_uses

_FORM = ("form_tab",)
_LIST = ("logic_list",)


def open_uses(surface: Any) -> None:
    """The shell's Find References action calls this while a form is focused."""
    show_uses(surface)


def register(keys: Any) -> None:
    keys.key(
        "form.action.logicUses",
        "Uses of this name",
        "Shift+F12",
        _FORM,
        shell_action_id="shell.action.edit.findReferences",
        run=show_uses,
    )
    keys.key(
        "form.action.openLogicRow",
        "Open logic row",
        "Enter",
        _LIST,
        kind="qt",
        available=True,
    )
