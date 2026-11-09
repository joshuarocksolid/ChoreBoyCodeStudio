"""Keys the formula field and the State list handle themselves."""

from __future__ import annotations

from typing import Any

_FIELD = ("formula_field",)
_LIST = ("state_list",)


def register(keys: Any) -> None:
    keys.key("form.action.commitFormula", "Commit formula", "Ctrl+Enter", _FIELD, kind="qt", available=True)
    keys.key("form.action.cancelFormula", "Cancel formula", "Esc", _FIELD, kind="qt", available=True)
    keys.key("form.action.completeFormula", "Complete", "Ctrl+Space", _FIELD, kind="qt", available=True)
    keys.key("form.action.applyFormulaFix", "Apply formula fix", "Ctrl+.", _FIELD, kind="qt", available=True)
    keys.key("form.action.editStateRow", "Edit the State row", "Enter", _LIST, kind="qt", available=True)
