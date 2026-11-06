"""Generic shell extension points a feature can register before the window exists.

The registry holds callables only. It does not know about any one feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.qt.QtGui import QColor, QIcon
from app.qt.QtWidgets import QWidget


SidebarIconFactory = Callable[[QColor, QColor], QIcon]
SidebarWidgetFactory = Callable[[QWidget], QWidget]
DecorationLookup = Callable[[str], Optional[tuple[str, str]]]
ThemeHook = Callable[[object], None]


@dataclass
class SidebarContribution:
    view_id: str
    tooltip: str
    icon_factory: SidebarIconFactory
    widget_factory: SidebarWidgetFactory


@dataclass
class ToolbarContribution:
    """A widget inserted on the run toolbar, to the left of Package Project."""

    factory: Callable[[QWidget], QWidget]


@dataclass
class ExplorerMenuAction:
    label: str
    on_trigger: Callable[[str], None]


class ShellContributions:
    """Collects feature registrations and fans them out when the shell is built."""

    def __init__(self) -> None:
        self.sidebar: list[SidebarContribution] = []
        self.toolbar: list[ToolbarContribution] = []
        self.explorer_decorations: list[DecorationLookup] = []
        self.explorer_menu_actions: list[ExplorerMenuAction] = []
        self.editor_page_hooks: list[Callable[[QWidget, str], None]] = []
        self.finalize_hooks: list[Callable[[object], None]] = []
        self.file_saved_hooks: list[Callable[[str], None]] = []
        self.theme_hooks: list[ThemeHook] = []
        self.package_extras: list[Callable[[object], None]] = []
        self.packaged_hooks: list[Callable[[object, str], None]] = []
        self.settings_group_factories: list[Callable[[QWidget], QWidget]] = []

    def notify_file_saved(self, path: str) -> None:
        for hook in list(self.file_saved_hooks):
            hook(path)

    def apply_theme(self, tokens: object) -> None:
        for hook in list(self.theme_hooks):
            hook(tokens)

    def notify_packaged(self, wizard: object, version: str) -> None:
        for hook in list(self.packaged_hooks):
            hook(wizard, version)


__all__ = [
    "DecorationLookup",
    "ExplorerMenuAction",
    "ShellContributions",
    "SidebarContribution",
    "ToolbarContribution",
]
