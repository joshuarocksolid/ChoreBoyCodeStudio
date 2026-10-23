"""Raw XML stubs show a value as its ui4 element and parse it back."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ui4.values import (
    BrushValue,
    ColorRole,
    ColorValue,
    IconSetValue,
    PaletteValue,
    ResourcePixmap,
    StringValue,
    Value,
)
from app.features.form_builder.qtside.inspector.editors.raw import (
    RawValueError,
    parse_raw_value,
    raw_text,
)

pytestmark = pytest.mark.unit

_PALETTE = PaletteValue(
    active=(ColorRole("WindowText", BrushValue(brushstyle="SolidPattern", color=ColorValue(200, 10, 20))),),
)
_ICON = IconSetValue(resource="icons.qrc", normaloff=ResourcePixmap(":/icons/ok.png", resource="icons.qrc"))


@pytest.mark.parametrize(
    "value",
    [_PALETTE, _ICON, StringValue("color: red;")],
    ids=["palette", "iconset", "stylesheet"],
)
def test_raw_text_is_the_value_element_and_parses_back(value: Value) -> None:
    text = raw_text(value)

    assert text.startswith("<" + value.ELEMENT)
    assert parse_raw_value(value.ELEMENT, text) == value


@pytest.mark.parametrize("text", ["<string>x</string>", "<palette>", ""], ids=["other-kind", "broken", "empty"])
def test_raw_text_that_is_not_one_palette_is_rejected(text: str) -> None:
    with pytest.raises(RawValueError):
        parse_raw_value(PaletteValue.ELEMENT, text)
