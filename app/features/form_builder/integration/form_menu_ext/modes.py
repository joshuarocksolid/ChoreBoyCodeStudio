"""Form > Overlays ▸ Tab order, Buddies, Tab order list…, and Help > Form designer keys (M5.6, UX-M5-010)."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.form_menu_ext import HELP, FormMenuItem

_TITLE = "Overlays"


def _visual(surface: Any) -> bool:
    return surface is not None and surface.can_use_overlays()


def _toggle(kind: str) -> Any:
    def run(surface: Any) -> None:
        surface.toggle_overlay(kind)

    return run


def _list(surface: Any) -> None:
    surface.focus_tab_order_list()


def _keys(surface: Any) -> None:
    from app.features.form_builder.integration.widget_help import show_keys_page

    show_keys_page(surface)


def register(registry: Any) -> None:
    add = registry.add
    add(FormMenuItem("form.action.tabOrder", (_TITLE, "Tab order"), _toggle("tab_order"), rank=0, enabled=_visual))
    add(FormMenuItem("form.action.buddies", (_TITLE, "Buddies"), _toggle("buddies"), rank=1, enabled=_visual))
    add(FormMenuItem("form.action.tabOrderList", (_TITLE, "Tab order list…"), _list, rank=2, enabled=_visual))
    add(
        FormMenuItem(
            "form.help.formKeys",
            ("Form designer keys",),
            _keys,
            target=HELP,
        )
    )
