"""Durations for form-builder chrome. Structure does not animate."""

from __future__ import annotations

from typing import Optional, Tuple

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QApplication

_CHIP_FADE_MS = 80
_REDUCE_KEY = "form_builder.reduce_motion"
_TRUE_TEXT = frozenset({"1", "true", "yes"})


def motion_ms(nominal_ms: int, reduce_motion: bool, effects_enabled: bool) -> int:
    """Zero when the user asked for less motion or menu animation is off."""
    if reduce_motion or not effects_enabled:
        return 0
    return nominal_ms


def motion_flags(settings: Optional[object] = None) -> Tuple[bool, bool]:
    """``form_builder.reduce_motion`` and ``UI_AnimateMenu``."""
    return _reduce_motion(settings), _menu_animation_enabled()


def chip_fade_ms(settings: Optional[object] = None) -> int:
    """Chips and handles. The only canvas-structure fade."""
    reduce_motion, effects_enabled = motion_flags(settings)
    return motion_ms(_CHIP_FADE_MS, reduce_motion, effects_enabled)


def _reduce_motion(settings: Optional[object]) -> bool:
    if settings is None:
        return False
    raw = getattr(settings, "value")(_REDUCE_KEY, False)
    if raw is True or raw == 1:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in _TRUE_TEXT
    return False


def _menu_animation_enabled() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    effect = getattr(getattr(Qt, "UIEffect", Qt), "UI_AnimateMenu")
    return bool(app.isEffectEnabled(effect))
