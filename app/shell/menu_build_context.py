"""Shared context for shell menu builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from app.shell.menus import MenuCallbacks


@dataclass(frozen=True)
class MenuBuildContext:
    """Dependencies shared by focused menu builder modules."""

    qt_widgets: Any
    qt_core: Any
    menu_bar: Any
    actions: dict[str, Any]
    menus: dict[str, Any]
    callbacks: "MenuCallbacks"
    shortcut_overrides: Mapping[str, str] | None = None
