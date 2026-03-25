"""Designer editing mode state controller."""

from __future__ import annotations

from dataclasses import dataclass

from PySide2.QtCore import QObject, Signal


MODE_WIDGET = "widget"
MODE_SIGNALS_SLOTS = "signals_slots"
MODE_BUDDY = "buddy"
MODE_TAB_ORDER = "tab_order"

_SUPPORTED_MODES = {
    MODE_WIDGET,
    MODE_SIGNALS_SLOTS,
    MODE_BUDDY,
    MODE_TAB_ORDER,
}


@dataclass(frozen=True)
class DesignerModeDefinition:
    """Mode metadata for menu and mode-bar rendering."""

    mode_id: str
    display_name: str
    shortcut: str
    icon_char: str = ""
    tooltip: str = ""


DESIGNER_MODE_DEFINITIONS: tuple[DesignerModeDefinition, ...] = (
    DesignerModeDefinition(
        MODE_WIDGET, "Widget", "F3",
        icon_char="\u270E", tooltip="Widget Editing Mode (F3)",
    ),
    DesignerModeDefinition(
        MODE_SIGNALS_SLOTS, "Signals", "F4",
        icon_char="\u26A1", tooltip="Signals/Slots Mode (F4)",
    ),
    DesignerModeDefinition(
        MODE_BUDDY, "Buddy", "F5",
        icon_char="\u2696", tooltip="Buddy Assignment Mode (F5)",
    ),
    DesignerModeDefinition(
        MODE_TAB_ORDER, "Tab Order", "F6",
        icon_char="\u2195", tooltip="Tab Order Mode (F6)",
    ),
)


class DesignerModeController(QObject):
    """Owns current designer mode and emits mode changes."""

    mode_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_mode = MODE_WIDGET

    @property
    def current_mode(self) -> str:
        return self._current_mode

    def set_mode(self, mode_id: str) -> bool:
        if mode_id not in _SUPPORTED_MODES:
            return False
        if mode_id == self._current_mode:
            return False
        self._current_mode = mode_id
        self.mode_changed.emit(mode_id)
        return True

