"""Designer widget palette registry contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class PaletteWidgetDefinition:
    """Defines one palette entry."""

    class_name: str
    display_name: str
    category: str
    default_object_name_prefix: str
    allowed_parent_classes: tuple[str, ...] = ()
    default_properties: Mapping[str, object] = field(default_factory=dict)
    is_layout_item: bool = False


class WidgetPaletteRegistry:
    """In-memory registry of palette widget definitions."""

    def __init__(self, definitions: list[PaletteWidgetDefinition]) -> None:
        self._definitions = list(definitions)
        self._by_class_name = {item.class_name: item for item in self._definitions}

    def list_all(self) -> list[PaletteWidgetDefinition]:
        return list(self._definitions)

    def list_by_category(self, category: str) -> list[PaletteWidgetDefinition]:
        return [item for item in self._definitions if item.category == category]

    def lookup(self, class_name: str) -> PaletteWidgetDefinition | None:
        return self._by_class_name.get(class_name)


def default_widget_palette_registry() -> WidgetPaletteRegistry:
    """Build the baseline D1 widget palette registry."""
    definitions = [
        PaletteWidgetDefinition("QWidget", "Widget", "Containers", "widget"),
        PaletteWidgetDefinition("QFrame", "Frame", "Containers", "frame"),
        PaletteWidgetDefinition("QGroupBox", "Group Box", "Containers", "groupBox"),
        PaletteWidgetDefinition("QTabWidget", "Tab Widget", "Containers", "tabWidget"),
        PaletteWidgetDefinition("QScrollArea", "Scroll Area", "Containers", "scrollArea"),
        PaletteWidgetDefinition("QLineEdit", "Line Edit", "Inputs", "lineEdit"),
        PaletteWidgetDefinition("QTextEdit", "Text Edit", "Inputs", "textEdit"),
        PaletteWidgetDefinition("QComboBox", "Combo Box", "Inputs", "comboBox"),
        PaletteWidgetDefinition("QCheckBox", "Check Box", "Inputs", "checkBox"),
        PaletteWidgetDefinition("QRadioButton", "Radio Button", "Inputs", "radioButton"),
        PaletteWidgetDefinition("QLabel", "Label", "Display", "label"),
        PaletteWidgetDefinition("QPushButton", "Push Button", "Buttons/Actions", "pushButton"),
        PaletteWidgetDefinition(
            "QSpacerItem",
            "Spacer",
            "Layout Items",
            "spacerItem",
            is_layout_item=True,
        ),
    ]
    return WidgetPaletteRegistry(definitions)
