"""Unit tests for WCAG contrast helpers.

These helpers are pure functions, used to audit the centrally-defined theme
palette.  Branching is non-trivial (sRGB linearization, hex parsing, ratio
ordering) so the gate from ``testing_when_to_write.mdc`` is satisfied.
"""

from __future__ import annotations

import pytest

from app.shell.contrast import (
    WCAG_AA_NORMAL_TEXT_RATIO,
    contrast_ratio,
    meets_wcag_aa_normal,
    relative_luminance,
)

pytestmark = pytest.mark.unit


class TestRelativeLuminance:
    def test_pure_black_is_zero(self) -> None:
        assert relative_luminance("#000000") == pytest.approx(0.0)

    def test_pure_white_is_one(self) -> None:
        assert relative_luminance("#FFFFFF") == pytest.approx(1.0)

    def test_short_form_hex_supported(self) -> None:
        assert relative_luminance("#FFF") == pytest.approx(relative_luminance("#FFFFFF"))

    def test_invalid_hex_raises(self) -> None:
        with pytest.raises(ValueError):
            relative_luminance("not-a-color")


class TestContrastRatio:
    def test_white_on_black_is_21_to_1(self) -> None:
        # 21:1 is the maximum possible WCAG contrast ratio.
        assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, rel=1e-6)

    def test_ratio_is_symmetric(self) -> None:
        a = contrast_ratio("#3366FF", "#FFFFFF")
        b = contrast_ratio("#FFFFFF", "#3366FF")
        assert a == pytest.approx(b)

    def test_identical_colors_give_one_to_one(self) -> None:
        assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)

    def test_meets_wcag_aa_helper_uses_threshold(self) -> None:
        # 4.5:1 is the AA-normal threshold; a known passing pair.
        assert meets_wcag_aa_normal("#212529", "#FFFFFF")
        # Light gray on white is below threshold.
        assert not meets_wcag_aa_normal("#ADB5BD", "#FFFFFF")
        # The threshold constant is exposed for reuse and is exactly 4.5.
        assert WCAG_AA_NORMAL_TEXT_RATIO == 4.5
