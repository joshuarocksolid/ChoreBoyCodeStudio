# pyright: reportAttributeAccessIssue=false
"""UX-ICON-005: every catalog entry paints its own non-blank glyph at 16 and 20 px and at DPR 2."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("qapp")

_SIZES = ((16, 1.0), (20, 1.0), (16, 2.0))


def _catalog_glyphs() -> dict:
    from app.features.form_builder.qtside.insert.catalog import load_catalog

    catalog = load_catalog()
    found: dict = {}
    for entry in catalog.entries + catalog.windows:
        found.setdefault(entry.glyph, entry.key)
    found.setdefault("custom", "custom:*")
    return found


def _ink(name: str, logical: int, dpr: float) -> tuple:
    from app.features.form_builder.qtside.icons.glyphs import paint_glyph

    image = paint_glyph(name, "#222222", logical, dpr).toImage()
    width, height = image.width(), image.height()
    return tuple(image.pixelColor(x, y).alpha() for y in range(height) for x in range(width))


@pytest.mark.parametrize(("logical", "dpr"), _SIZES)
def test_every_catalog_glyph_has_ink(logical: int, dpr: float) -> None:
    for name in _catalog_glyphs():
        assert max(_ink(name, logical, dpr)) > 40, "%s is blank at %s px, DPR %s" % (name, logical, dpr)


@pytest.mark.parametrize(("logical", "dpr"), _SIZES)
def test_two_entries_never_paint_the_same_pixels(logical: int, dpr: float) -> None:
    seen: dict = {}
    for name, key in _catalog_glyphs().items():
        signature = _ink(name, logical, dpr)
        assert signature not in seen, "%s and %s paint the same pixels" % (key, seen.get(signature))
        seen[signature] = key


def test_each_entry_names_its_own_glyph() -> None:
    from app.features.form_builder.qtside.insert.catalog import load_catalog

    catalog = load_catalog()
    names = [entry.glyph for entry in catalog.entries + catalog.windows]
    assert len(names) == len(set(names))
