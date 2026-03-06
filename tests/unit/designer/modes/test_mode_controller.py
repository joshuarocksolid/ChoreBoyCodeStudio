"""Unit tests for designer mode controller."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtCore", exc_type=ImportError)

from app.designer.modes import (
    MODE_BUDDY,
    MODE_SIGNALS_SLOTS,
    MODE_TAB_ORDER,
    MODE_WIDGET,
    DesignerModeController,
)

pytestmark = pytest.mark.unit


def test_mode_controller_switches_modes_and_emits() -> None:
    controller = DesignerModeController()
    seen: list[str] = []
    controller.mode_changed.connect(seen.append)

    assert controller.current_mode == MODE_WIDGET
    assert controller.set_mode(MODE_SIGNALS_SLOTS) is True
    assert controller.current_mode == MODE_SIGNALS_SLOTS
    assert controller.set_mode(MODE_BUDDY) is True
    assert controller.set_mode(MODE_TAB_ORDER) is True
    assert seen == [MODE_SIGNALS_SLOTS, MODE_BUDDY, MODE_TAB_ORDER]


def test_mode_controller_rejects_invalid_or_duplicate_modes() -> None:
    controller = DesignerModeController()
    assert controller.set_mode("unknown") is False
    assert controller.set_mode(MODE_WIDGET) is False
