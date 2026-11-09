# pyright: reportAttributeAccessIssue=false
"""Chip and handle fades drop to zero when motion is reduced or effects are off."""

from __future__ import annotations

import pytest

from app.qt.QtCore import Qt  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication

pytestmark = pytest.mark.usefixtures("qapp")


class _Settings:
    def __init__(self, stored: object) -> None:
        self.stored = stored
        self.key = ""

    def value(self, key: str, default: object = None) -> object:
        self.key = key
        if self.stored is None:
            return default
        return self.stored


def test_motion_keeps_the_nominal_duration_when_animation_is_allowed() -> None:
    from app.features.form_builder.qtside.motion import motion_ms

    assert motion_ms(80, False, True) == 80


def test_reduce_motion_or_disabled_effects_drop_the_duration() -> None:
    from app.features.form_builder.qtside.motion import motion_ms

    assert motion_ms(80, True, True) == 0
    assert motion_ms(80, False, False) == 0
    assert motion_ms(80, True, False) == 0


def test_settings_and_menu_animation_feed_the_chip_fade(qapp: QApplication) -> None:
    from app.features.form_builder.qtside.motion import chip_fade_ms, motion_flags, motion_ms

    effect = getattr(getattr(Qt, "UIEffect", Qt), "UI_AnimateMenu")
    settings = _Settings(None)
    reduce_motion, effects_enabled = motion_flags(settings)
    assert settings.key == "form_builder.reduce_motion"
    assert reduce_motion is False
    assert effects_enabled is bool(qapp.isEffectEnabled(effect))
    assert chip_fade_ms(settings) == motion_ms(80, reduce_motion, effects_enabled)
    assert chip_fade_ms(_Settings(True)) == 0
    assert chip_fade_ms(_Settings("yes")) == 0
