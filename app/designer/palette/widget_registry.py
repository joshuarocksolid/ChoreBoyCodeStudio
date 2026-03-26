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
    icon_char: str = ""


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
        PaletteWidgetDefinition("QWidget", "Widget", "Containers", "widget", icon_char="\u25A1"),
        PaletteWidgetDefinition("QFrame", "Frame", "Containers", "frame", icon_char="\u25A0"),
        PaletteWidgetDefinition("QGroupBox", "Group Box", "Containers", "groupBox", icon_char="\u25A3"),
        PaletteWidgetDefinition("QTabWidget", "Tab Widget", "Containers", "tabWidget", icon_char="\u2630"),
        PaletteWidgetDefinition("QScrollArea", "Scroll Area", "Containers", "scrollArea", icon_char="\u2B13"),
        PaletteWidgetDefinition("QLineEdit", "Line Edit", "Inputs", "lineEdit", icon_char="\u270E"),
        PaletteWidgetDefinition("QTextEdit", "Text Edit", "Inputs", "textEdit", icon_char="\u2263"),
        PaletteWidgetDefinition("QComboBox", "Combo Box", "Inputs", "comboBox", icon_char="\u25BE"),
        PaletteWidgetDefinition("QCheckBox", "Check Box", "Inputs", "checkBox", icon_char="\u2611"),
        PaletteWidgetDefinition("QRadioButton", "Radio Button", "Inputs", "radioButton", icon_char="\u25C9"),
        PaletteWidgetDefinition("QSpinBox", "Spin Box", "Numeric Inputs", "spinBox", icon_char="\u2460"),
        PaletteWidgetDefinition("QDoubleSpinBox", "Double Spin Box", "Numeric Inputs", "doubleSpinBox", icon_char="\u2461"),
        PaletteWidgetDefinition("QSlider", "Slider", "Numeric Inputs", "slider", icon_char="\u2550"),
        PaletteWidgetDefinition("QDial", "Dial", "Numeric Inputs", "dial", icon_char="\u25EF"),
        PaletteWidgetDefinition("QDateEdit", "Date Edit", "Date/Time Inputs", "dateEdit", icon_char="\U0001F4C5"),
        PaletteWidgetDefinition("QTimeEdit", "Time Edit", "Date/Time Inputs", "timeEdit", icon_char="\u23F2"),
        PaletteWidgetDefinition("QDateTimeEdit", "Date Time Edit", "Date/Time Inputs", "dateTimeEdit", icon_char="\U0001F552"),
        PaletteWidgetDefinition("QLabel", "Label", "Display", "label", icon_char="\u24C1"),
        PaletteWidgetDefinition("QProgressBar", "Progress Bar", "Indicators", "progressBar", icon_char="\u25A4"),
        PaletteWidgetDefinition("QPushButton", "Push Button", "Buttons/Actions", "pushButton", icon_char="\u25B6"),
        PaletteWidgetDefinition("QToolButton", "Tool Button", "Buttons/Actions", "toolButton", icon_char="\u25B8"),
        PaletteWidgetDefinition("QDialogButtonBox", "Dialog Button Box", "Buttons/Actions", "buttonBox", icon_char="\u25A7"),
        PaletteWidgetDefinition(
            "QSpacerItem",
            "Spacer",
            "Layout Items",
            "spacerItem",
            is_layout_item=True,
            icon_char="\u2B0C",
        ),
    ]
    return WidgetPaletteRegistry(definitions)
