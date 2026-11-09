# pyright: reportAttributeAccessIssue=false
"""Painted form-builder glyphs stay sharp at the sizes the chrome asks for."""

from __future__ import annotations

import pytest

from app.qt.QtGui import QColor  # type: ignore[reportAttributeAccessIssue]

pytestmark = pytest.mark.usefixtures("qapp")

REQUIRED = (
    "chevron_up",
    "chevron_down",
    "chevron_left",
    "chevron_right",
    "plus",
    "minus",
    "close",
    "reset",
    "undo",
    "redo",
    "play",
    "zoom",
    "fit",
    "two_widths",
    "text_size",
    "xml",
    "tab_order",
    "buddy",
    "connection",
    "warning",
    "error",
    "info",
    "check",
    "lock",
    "database",
    "search",
    "grip",
    "more",
    "outline",
    "insert",
    "properties",
    "behavior",
    "pin",
)

CRISP = (12, 16, 20, 24)


def test_a_glyph_is_painted_at_device_resolution() -> None:
    from app.features.form_builder.qtside.icons.glyphs import paint_glyph

    pixmap = paint_glyph("plus", "#111111", 16, 2.0)
    assert pixmap.width() == 32
    assert pixmap.height() == 32
    assert abs(pixmap.devicePixelRatio() - 2.0) < 0.01
    image = pixmap.toImage()
    assert image.pixelColor(16, 16).alpha() > 200


@pytest.mark.parametrize("logical", CRISP)
def test_crisp_sizes_match_the_pixmap(logical: int) -> None:
    from app.features.form_builder.qtside.icons.glyphs import paint_glyph

    pixmap = paint_glyph("plus", "#111111", logical, 1.0)
    assert pixmap.width() == logical
    assert pixmap.height() == logical
    assert abs(pixmap.devicePixelRatio() - 1.0) < 0.01


def test_every_named_glyph_leaves_ink() -> None:
    from app.features.form_builder.qtside.icons.glyphs import paint_glyph

    for name in REQUIRED:
        image = paint_glyph(name, "#222222", 16, 1.0).toImage()
        assert _ink_count(image, 40) > 0, name


def test_the_colour_is_the_ink_colour() -> None:
    from app.features.form_builder.qtside.icons.glyphs import paint_glyph

    red = _first_ink(paint_glyph("check", "#ff0000", 16, 1.0).toImage())
    blue = _first_ink(paint_glyph("check", "#0000ff", 16, 1.0).toImage())
    assert red.red() > red.blue()
    assert blue.blue() > blue.red()


def test_stroke_thickness_scales_with_device_pixels() -> None:
    from app.features.form_builder.qtside.icons.glyphs import paint_glyph

    thin = paint_glyph("plus", "#000000", 16, 1.0).toImage()
    thick = paint_glyph("plus", "#000000", 16, 2.0).toImage()
    assert _stem_width(thin, 5) < _stem_width(thick, 10)


def test_unknown_glyph_is_refused() -> None:
    from app.features.form_builder.qtside.icons.glyphs import paint_glyph

    with pytest.raises(KeyError):
        paint_glyph("not_a_glyph", "#000000", 16, 1.0)


def _ink_count(image: object, minimum_alpha: int) -> int:
    count = 0
    for y in range(image.height()):  # type: ignore[attr-defined]
        for x in range(image.width()):  # type: ignore[attr-defined]
            if image.pixelColor(x, y).alpha() > minimum_alpha:  # type: ignore[attr-defined]
                count += 1
    return count


def _first_ink(image: object) -> QColor:
    for y in range(image.height()):  # type: ignore[attr-defined]
        for x in range(image.width()):  # type: ignore[attr-defined]
            colour = image.pixelColor(x, y)  # type: ignore[attr-defined]
            if colour.alpha() > 200:
                return colour
    raise AssertionError("glyph has no opaque ink")


def _stem_width(image: object, y: int) -> int:
    return sum(
        1
        for x in range(image.width())  # type: ignore[attr-defined]
        if image.pixelColor(x, y).alpha() > 100  # type: ignore[attr-defined]
    )
