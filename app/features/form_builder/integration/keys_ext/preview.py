"""Ctrl+K, C: View Python code beside the canvas (M5.5a, UX-PREV-004).

Preview's own key, Ctrl+Shift+R, is a row of the command table and is bound by
the form tab, which sends it through the tab's ``PreviewControl``.
"""

from __future__ import annotations

from typing import Any

_FORM = ("form_tab",)


def _view_code(surface: Any) -> None:
    surface.toggle_code_view()


def register(keys: Any) -> None:
    keys.key("form.action.viewCode", "View Python code", "Ctrl+K, C", _FORM, run=_view_code)
