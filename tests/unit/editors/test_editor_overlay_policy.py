"""Unit tests for pure editor overlay/highlighting policy helpers."""

from __future__ import annotations

import pytest

from app.core import constants
from app.editors.editor_overlay_policy import (
    effective_highlighting_mode,
    is_large_document,
    visible_document_window,
)

pytestmark = pytest.mark.unit


def test_is_large_document_uses_reduced_threshold() -> None:
    assert is_large_document(document_size=1001, reduced_threshold_chars=1000) is True
    assert is_large_document(document_size=1000, reduced_threshold_chars=1000) is False


def test_effective_highlighting_mode_respects_forced_lexical_mode() -> None:
    mode = effective_highlighting_mode(
        adaptive_mode=constants.HIGHLIGHTING_MODE_LEXICAL_ONLY,
        document_size=10,
        reduced_threshold_chars=1000,
        lexical_only_threshold_chars=2000,
    )
    assert mode == constants.HIGHLIGHTING_MODE_LEXICAL_ONLY


def test_effective_highlighting_mode_applies_reduced_and_lexical_thresholds() -> None:
    assert (
        effective_highlighting_mode(
            adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
            document_size=1500,
            reduced_threshold_chars=1000,
            lexical_only_threshold_chars=2000,
        )
        == constants.HIGHLIGHTING_MODE_REDUCED
    )
    assert (
        effective_highlighting_mode(
            adaptive_mode=constants.HIGHLIGHTING_MODE_NORMAL,
            document_size=2500,
            reduced_threshold_chars=1000,
            lexical_only_threshold_chars=2000,
        )
        == constants.HIGHLIGHTING_MODE_LEXICAL_ONLY
    )


def test_visible_document_window_bounds_positions_with_margin() -> None:
    start, end = visible_document_window(
        top_position=200,
        bottom_position=120,
        max_position=250,
        margin=20,
    )
    assert start == 100
    assert end == 220

    low_start, low_end = visible_document_window(
        top_position=4,
        bottom_position=10,
        max_position=15,
        margin=20,
    )
    assert low_start == 0
    assert low_end == 15
