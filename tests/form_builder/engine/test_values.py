"""Every ui4 value kind parses, writes, and parses back to the same value."""
from __future__ import annotations

import locale
import os
import random
import re
from pathlib import Path
from typing import Callable, Optional, Tuple, Type

import pytest

from app.features.form_builder.engine.commands.ops import SetPropertyOp
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.mutate import apply
from app.features.form_builder.engine.ui4.numfmt import format_double, format_float, parse_real, real_round_trips
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    VALUE_CLASSES,
    BoolValue,
    BrushValue,
    CStringValue,
    CharValue,
    ColorRole,
    ColorValue,
    CursorShapeValue,
    CursorValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    EnumValue,
    FloatValue,
    FontValue,
    GradientStop,
    GradientValue,
    IconSetValue,
    LocaleValue,
    LongLongValue,
    NumberValue,
    OpaqueValue,
    PaletteValue,
    PointFValue,
    PointValue,
    RectFValue,
    RectValue,
    ResourcePixmap,
    SetValue,
    SizeFValue,
    SizePolicyValue,
    SizeValue,
    StringListValue,
    StringValue,
    TimeValue,
    UIntValue,
    ULongLongValue,
    UrlValue,
    Value,
    semantic_equal,
    value_from_json,
    value_to_json,
)
from app.features.form_builder.engine.ui4.writer import write_ui

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"
_FB005_TAG = re.compile(r"<([^>\s]+)>")
_Probe = Callable[[Value], None]


def _form(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0"><widget class="QWidget" name="Form">\n'
        " <property name=\"v\">\n%s\n </property>\n"
        "</widget></ui>\n" % body
    )


def _round_trip(body: str, *, compare_values: bool = True) -> Tuple[Value, Tuple[object, ...]]:
    loaded = read_ui(_form(body), allocator=IdAllocator())
    prop = loaded.document.root.prop("v")
    assert prop is not None
    saved = write_ui(loaded.document).text
    second = write_ui(read_ui(saved, allocator=IdAllocator()).document).text
    assert second == saved
    again = read_ui(saved, allocator=IdAllocator())
    restored = again.document.root.prop("v")
    assert restored is not None
    assert value_from_json(value_to_json(prop.value)) == prop.value
    if compare_values:
        assert restored.value == prop.value
        assert hash(prop.value) == hash(restored.value)
    codes = tuple(item.code for item in loaded.diagnostics)
    return prop.value, codes


def _paint(red: int, green: int, blue: int, alpha: Optional[int] = None) -> str:
    alpha_attr = "" if alpha is None else ' alpha="%s"' % alpha
    return (
        "<color%s><red>%s</red><green>%s</green><blue>%s</blue></color>"
        % (alpha_attr, red, green, blue)
    )


def _check_palette(value: Value) -> None:
    assert isinstance(value, PaletteValue)
    assert value.active[0] == ColorRole(
        "WindowText",
        BrushValue(brushstyle="SolidPattern", color=ColorValue(1, 2, 3, 255)),
    )
    window = value.active[1]
    assert window.role == "Window"
    assert window.brush.brushstyle == "SolidPattern"
    assert window.brush.color == ColorValue(240, 240, 240, 255)
    gradient = value.active[2].brush.gradient
    assert gradient is not None
    assert gradient.type == "LinearGradient"
    assert gradient.spread == "PadSpread"
    assert gradient.stops[0].position == 0.0
    assert gradient.stops[1].color == ColorValue(0, 0, 255, 128)
    assert value.inactive[0].brush.gradient is not None
    assert value.inactive[0].brush.gradient.type == "RadialGradient"
    conical = value.disabled[0].brush.gradient
    assert conical is not None and conical.type == "ConicalGradient"
    assert conical.angle == 45.0
    texture = value.disabled[1].brush
    assert texture.brushstyle == "TexturePattern"
    assert texture.texture_name == "windowTexture"
    assert texture.texture == ResourcePixmap(":/cbcs/icons/dot.png", "icons.qrc", "dot")


def _check_iconset(value: Value) -> None:
    assert isinstance(value, IconSetValue)
    assert value.theme == "document-new"
    assert value.resource == "icons.qrc"
    assert value.text == ":/a.png"
    assert value.normaloff == ResourcePixmap(":/a.png", "icons.qrc", "dot")
    assert value.normalon == ResourcePixmap(":/b.png")
    assert value.disabledoff == ResourcePixmap(":/c.png")
    assert value.disabledon == ResourcePixmap(":/d.png")
    assert value.activeoff == ResourcePixmap(":/e.png")
    assert value.activeon == ResourcePixmap(":/f.png")
    assert value.selectedoff == ResourcePixmap(":/g.png")
    assert value.selectedon == ResourcePixmap(":/h.png")


def _check_legacy_icon(value: Value) -> None:
    assert isinstance(value, IconSetValue)
    assert value.resource == "remotecontrol.qrc"
    assert value.text == ":/remotecontrol/enter.png"
    assert value.normaloff is None
    assert value.theme is None


_CASES = [
    ("bool", "<bool>false</bool>", BoolValue, lambda value: value.value is False),
    ("color", _paint(9, 8, 7, 255), ColorValue, lambda value: value == ColorValue(9, 8, 7, 255)),
    ("color-no-alpha", _paint(1, 2, 3), ColorValue, lambda value: value.alpha is None),
    ("cstring", "<cstring>nameEdit</cstring>", CStringValue, lambda value: value.text == "nameEdit"),
    ("cursor", "<cursor>4</cursor>", CursorValue, lambda value: value.value == 4),
    ("cursorShape", "<cursorShape>IBeamCursor</cursorShape>", CursorShapeValue, lambda value: value.name == "IBeamCursor"),
    ("enum", "<enum>Qt::LeftToRight</enum>", EnumValue, lambda value: value.text == "Qt::LeftToRight"),
    ("font", "<font><family>DejaVu Sans</family><pointsize>11</pointsize><bold>true</bold></font>", FontValue, lambda value: value.family == "DejaVu Sans" and value.bold is True and value.italic is None),
    ("pixmap", '<pixmap resource="icons.qrc" alias="dot">:/cbcs/icons/dot.png</pixmap>', ResourcePixmap, lambda value: value == ResourcePixmap(":/cbcs/icons/dot.png", "icons.qrc", "dot")),
    ("point", "<point><x>2</x><y>-3</y></point>", PointValue, lambda value: value == PointValue(2, -3)),
    ("pointf", "<pointf><x>1.25</x><y>-0</y></pointf>", PointFValue, lambda value: value == PointFValue(1.25, 0.0)),
    ("rect", "<rect><x>0</x><y>0</y><width>12</width><height>14</height></rect>", RectValue, lambda value: value.width == 12),
    ("rectf", "<rectf><x>0.5</x><y>0.5</y><width>2.5</width><height>3.5</height></rectf>", RectFValue, lambda value: value.width == 2.5),
    ("set", "<set>Qt::AlignLeft|Qt::AlignVCenter</set>", SetValue, lambda value: value.text.startswith("Qt::AlignLeft")),
    ("locale", '<locale language="English" country="UnitedStates"/>', LocaleValue, lambda value: value == LocaleValue("English", "UnitedStates")),
    ("sizepolicy", '<sizepolicy hsizetype="Preferred" vsizetype="Minimum"><horstretch>1</horstretch><verstretch>0</verstretch></sizepolicy>', SizePolicyValue, lambda value: value.horstretch == 1 and value.hsizetype == "Preferred"),
    ("sizepolicy-legacy", '<sizepolicy hsizetype="Expanding" vsizetype="Preferred"><hsizetype>7</hsizetype><vsizetype>5</vsizetype><horstretch>0</horstretch><verstretch>1</verstretch></sizepolicy>', SizePolicyValue, lambda value: value == SizePolicyValue("Expanding", "Preferred", 0, 1)),
    ("sizepolicy-ints", "<sizepolicy><hsizetype>7</hsizetype><vsizetype>5</vsizetype></sizepolicy>", SizePolicyValue, lambda value: value.hsizetype == "Expanding" and value.vsizetype == "Preferred"),
    ("size", "<size><width>16</width><height>0</height></size>", SizeValue, lambda value: value == SizeValue(16, 0)),
    ("sizef", "<sizef><width>1.5</width><height>2.5</height></sizef>", SizeFValue, lambda value: value == SizeFValue(1.5, 2.5)),
    ("string", '<string notr="true" comment="cap" extracomment="hint" id="cap.id">Hello</string>', StringValue, lambda value: value.text == "Hello" and value.notr is True and value.id == "cap.id"),
    ("string-exact", "<string>  keep\nme  </string>", StringValue, lambda value: value.text == "  keep\nme  "),
    ("stringlist", '<stringlist notr="true"><string>one</string><string></string><string>two &amp; three</string></stringlist>', StringListValue, lambda value: value.items == ("one", "", "two & three") and value.notr is True),
    ("number", "<number>-7</number>", NumberValue, lambda value: value.value == -7),
    ("float", "<float>0.5</float>", FloatValue, lambda value: value.value == 0.5),
    ("double", "<double>3.14</double>", DoubleValue, lambda value: value.value == parse_real("3.14")),
    ("date", "<date><year>2026</year><month>10</month><day>21</day></date>", DateValue, lambda value: value == DateValue(2026, 10, 21)),
    ("time", "<time><hour>8</hour><minute>30</minute><second>0</second></time>", TimeValue, lambda value: value == TimeValue(8, 30, 0)),
    ("datetime", "<datetime><hour>8</hour><minute>30</minute><second>1</second><year>2026</year><month>1</month><day>2</day></datetime>", DateTimeValue, lambda value: value.year == 2026 and value.second == 1),
    ("longlong", "<longlong>-9223372036854775808</longlong>", LongLongValue, lambda value: value.value == -9223372036854775808),
    ("char", "<char><unicode>66</unicode></char>", CharValue, lambda value: value.unicode == 66),
    ("url", '<url><string notr="true">https://example.com/a</string></url>', UrlValue, lambda value: value.string.text == "https://example.com/a" and value.string.notr is True),
    ("uint", "<uint>4294967295</uint>", UIntValue, lambda value: value.value == 4294967295),
    ("ulonglong", "<ulonglong>18446744073709551615</ulonglong>", ULongLongValue, lambda value: value.value == 18446744073709551615),
    ("brush", '<brush brushstyle="SolidPattern">%s</brush>' % _paint(1, 2, 3, 255), BrushValue, lambda value: value.brushstyle == "SolidPattern" and value.color == ColorValue(1, 2, 3, 255) and value.gradient is None),
    ("brush-empty", '<brush brushstyle="NoBrush"/>', BrushValue, lambda value: value.brushstyle == "NoBrush" and value.color is None),
    (
        "brush-gradient",
        '<brush brushstyle="LinearGradientPattern"><gradient startx="0" endy="1" type="LinearGradient"><gradientstop position="0.2">%s</gradientstop></gradient></brush>' % _paint(0, 255, 0, 255),
        BrushValue,
        lambda value: value.gradient is not None and value.gradient.stops == (GradientStop(0.2, ColorValue(0, 255, 0, 255)),) and value.gradient.endx is None,
    ),
]


def _palette_body() -> str:
    return """<palette>
 <active>
  <color><red>1</red><green>2</green><blue>3</blue></color>
  <colorrole role="Window"><brush brushstyle="SolidPattern">%s</brush></colorrole>
  <colorrole role="WindowText"><brush brushstyle="LinearGradientPattern"><gradient startx="0" starty="0" endx="100" endy="20" angle="15" type="LinearGradient" spread="PadSpread"><gradientstop position="0">%s</gradientstop><gradientstop position="1">%s</gradientstop></gradient></brush></colorrole>
 </active>
 <inactive>
  <colorrole role="Button"><brush brushstyle="RadialGradientPattern"><gradient centralx="0.5" centraly="0.5" focalx="0.4" focaly="0.4" radius="0.8" type="RadialGradient" spread="RepeatSpread" coordinatemode="ObjectMode"><gradientstop position="0.2">%s</gradientstop></gradient></brush></colorrole>
 </inactive>
 <disabled>
  <colorrole role="Base"><brush brushstyle="ConicalGradientPattern"><gradient centralx="0.5" centraly="0.5" angle="45" type="ConicalGradient" spread="ReflectSpread"><gradientstop position="0.5">%s</gradientstop></gradient></brush></colorrole>
  <colorrole role="AlternateBase"><brush brushstyle="TexturePattern"><texture name="windowTexture"><pixmap resource="icons.qrc" alias="dot">:/cbcs/icons/dot.png</pixmap></texture></brush></colorrole>
 </disabled>
</palette>""" % (
        _paint(240, 240, 240, 255),
        _paint(255, 0, 0, 255),
        _paint(0, 0, 255, 128),
        _paint(0, 255, 0, 255),
        _paint(10, 10, 10, 200),
    )


def _iconset_body() -> str:
    # Designer writes the backward-compat path once, after the last state,
    # and that path equals normaloff.
    return """<iconset theme="document-new" resource="icons.qrc">
 <normaloff resource="icons.qrc" alias="dot">:/a.png</normaloff>
 <normalon>:/b.png</normalon>
 <disabledoff>:/c.png</disabledoff>
 <disabledon>:/d.png</disabledon>
 <activeoff>:/e.png</activeoff>
 <activeon>:/f.png</activeon>
 <selectedoff>:/g.png</selectedoff>
 <selectedon>:/h.png</selectedon>:/a.png
</iconset>"""


@pytest.mark.parity("R3-287")
@pytest.mark.parity("R3-317")
def test_qt68_writes_cursorShape_and_gradientstop() -> None:
    shape, codes = _round_trip("<cursorShape>IBeamCursor</cursorShape>")
    assert isinstance(shape, CursorShapeValue)
    assert shape.name == "IBeamCursor"
    assert "FB005" not in codes
    saved = write_ui(read_ui(_form("<cursorShape>IBeamCursor</cursorShape>"), allocator=IdAllocator()).document).text
    assert "<cursorShape>" in saved
    assert "<cursorshape>" not in saved

    legacy, legacy_codes = _round_trip("<cursorshape>Qt::IBeamCursor</cursorshape>")
    assert isinstance(legacy, CursorShapeValue)
    assert legacy.name == "Qt::IBeamCursor"
    assert "FB005" not in legacy_codes

    body = (
        '<brush brushstyle="LinearGradientPattern"><gradient type="LinearGradient" startx="0">'
        "<gradientstop position=\"0.2\">%s</gradientstop></gradient></brush>" % _paint(0, 255, 0, 255)
    )
    brush, brush_codes = _round_trip(body)
    assert isinstance(brush, BrushValue)
    assert brush.gradient is not None
    assert brush.gradient.stops == (GradientStop(0.2, ColorValue(0, 255, 0, 255)),)
    assert "FB005" not in brush_codes
    saved = write_ui(read_ui(_form(body), allocator=IdAllocator()).document).text
    assert "<gradientstop " in saved
    assert "gradientStop" not in saved

    old_stop = (
        '<brush brushstyle="LinearGradientPattern"><gradient type="LinearGradient">'
        "<gradientStop position=\"1\">%s</gradientStop></gradient></brush>" % _paint(1, 2, 3, 255)
    )
    old_brush, old_codes = _round_trip(old_stop)
    assert isinstance(old_brush, BrushValue)
    assert old_brush.gradient is not None
    assert "FB005" not in old_codes


# Qt 6.8's DomProperty::write spells these three kinds in camelCase. Its reader
# compares tags case-insensitively, so both spellings load the same.
_DESIGNER_INT_TAGS = (
    ("longLong", LongLongValue, "-9223372036854775808"),
    ("UInt", UIntValue, "4294967295"),
    ("uLongLong", ULongLongValue, "18446744073709551615"),
)


@pytest.mark.parametrize(("tag", "kind", "text"), _DESIGNER_INT_TAGS, ids=[item[0] for item in _DESIGNER_INT_TAGS])
def test_designer_camelcase_int_tag_is_typed(tag: str, kind: Type[Value], text: str) -> None:
    value, codes = _round_trip("<%s>%s</%s>" % (tag, text, tag))
    assert type(value) is kind
    assert value == kind(int(text))  # type: ignore[call-arg]
    assert "FB005" not in codes


@pytest.mark.parametrize(("tag", "kind", "text"), _DESIGNER_INT_TAGS, ids=[item[0] for item in _DESIGNER_INT_TAGS])
def test_designer_camelcase_int_tag_out_of_range_stays_verbatim(tag: str, kind: Type[Value], text: str) -> None:
    del kind
    too_big = str(int(text) - 1) if text.startswith("-") else str(int(text) + 1)
    value, codes = _round_trip("<%s>%s</%s>" % (tag, too_big, tag), compare_values=False)
    assert isinstance(value, OpaqueValue)
    assert "FB005" in codes


@pytest.mark.parity("R3-284")
@pytest.mark.parity("R3-286")
@pytest.mark.parity("R3-291")
@pytest.mark.parity("R3-293")
@pytest.mark.parity("R3-296")
@pytest.mark.parity("R3-300")
@pytest.mark.parity("R3-304")
@pytest.mark.parity("R3-305")
@pytest.mark.parity("R3-306")
@pytest.mark.parity("R3-307")
@pytest.mark.parity("R3-308")
@pytest.mark.parity("R3-309")
@pytest.mark.parity("R3-310")
@pytest.mark.parity("R3-311")
@pytest.mark.parity("R3-312")
@pytest.mark.parity("R3-313")
@pytest.mark.parity("R3-314")
@pytest.mark.parity("R3-315")
@pytest.mark.parametrize(
    ("name", "body", "kind", "probe"),
    [(name, body, kind, probe) for name, body, kind, probe in _CASES],
    ids=[item[0] for item in _CASES],
)
def test_typed_value_round_trips(name: str, body: str, kind: Type[Value], probe: _Probe) -> None:
    del name
    value, codes = _round_trip(body)
    assert isinstance(value, kind)
    assert "FB005" not in codes
    probe(value)


@pytest.mark.parity("R3-290")
def test_designer_multistate_iconset_keeps_one_compat_path() -> None:
    body = "<iconset><normaloff>a.png</normaloff><normalon>b.png</normalon>a.png</iconset>"
    value, codes = _round_trip(body)
    assert "FB005" not in codes
    assert isinstance(value, IconSetValue)
    assert value.normaloff == ResourcePixmap("a.png")
    assert value.normalon == ResourcePixmap("b.png")
    assert value.text == "a.png"
    saved = write_ui(read_ui(_form(body), allocator=IdAllocator()).document).text
    assert "<normalon>b.png</normalon>a.png</iconset>" in saved
    assert "<normaloff>a.png</normaloff>a.png" not in saved


@pytest.mark.parity("R3-320")
def test_designer_eight_icon_states_round_trip() -> None:
    value, codes = _round_trip(_iconset_body())
    assert "FB005" not in codes
    _check_iconset(value)


@pytest.mark.parity("R3-292")
@pytest.mark.parity("R3-316")
@pytest.mark.parity("R3-318")
@pytest.mark.parity("R3-319")
@pytest.mark.parity("R3-321")
@pytest.mark.parametrize(
    ("body", "probe"),
    [
        (_palette_body(), _check_palette),
        ('<iconset resource="remotecontrol.qrc">:/remotecontrol/enter.png</iconset>', _check_legacy_icon),
        ('<iconset theme="document-open"/>', lambda value: isinstance(value, IconSetValue) and value.theme == "document-open" and value.text is None),
    ],
)
def test_palette_iconset_round_trip(body: str, probe: _Probe) -> None:
    value, codes = _round_trip(body)
    assert "FB005" not in codes
    probe(value)


@pytest.mark.parametrize(
    "body",
    [
        "<bool>1</bool>",
        "<double>1e-400</double>",
        "<pointf><x>1e-400</x><y>0</y></pointf>",
        "<uint>-1</uint>",
        "<ulonglong>18446744073709551616</ulonglong>",
        '<pixmap extra="1">a.png</pixmap>',
        "<brush><color><red>1</red><green>2</green><blue>3</blue></color><gradient type=\"LinearGradient\"/></brush>",
        "<palette><active/><inactive/></palette>",
        "<iconset><normaloff>a.png</normaloff>nope<normalon>b.png</normalon></iconset>",
        "<char><unicode>nope</unicode></char>",
        '<locale language="English"/>',
        "<url><string>a</string><string>b</string></url>",
        "<sparkle>1</sparkle>",
        '<sizepolicy hsizetype="Fixed" vsizetype="Preferred"><hsizetype>7</hsizetype><vsizetype>5</vsizetype></sizepolicy>',
    ],
)
def test_lossy_or_unknown_value_stays_verbatim(body: str) -> None:
    value, codes = _round_trip(body, compare_values=False)
    assert isinstance(value, OpaqueValue)
    assert "FB005" in codes


def test_enum_spellings_are_semantically_equal() -> None:
    horizontal = EnumValue("Qt::Horizontal")
    qualified = EnumValue("Qt::Orientation::Horizontal")
    assert semantic_equal(horizontal, qualified)
    assert horizontal != qualified
    assert not semantic_equal(horizontal, EnumValue("Qt::Vertical"))
    assert semantic_equal(
        SetValue("Qt::AlignLeft|Qt::AlignLeft"),
        SetValue("Qt::AlignmentFlag::AlignLeft"),
    )
    assert not semantic_equal(SetValue("Qt::AlignLeft"), SetValue("Qt::AlignRight"))
    assert not semantic_equal(horizontal, SetValue("Qt::Horizontal"))


def test_real_formatting_is_independent_of_locale() -> None:
    before_double = format_double(-0.0)
    before_float = format_float(1.5)
    before_parse = parse_real("1.5")
    selected = None
    for name in ("de_DE.UTF-8", "de_DE.utf8"):
        try:
            locale.setlocale(locale.LC_ALL, name)
        except locale.Error:
            continue
        selected = name
        break
    if selected is None:
        pytest.skip("de_DE.UTF-8 is not installed")
    try:
        assert format_double(-0.0) == before_double == "0.000000000000000"
        assert format_float(1.5) == before_float == "1.50000000"
        assert parse_real("1.5") == before_parse
        assert "," not in format_double(1.5)
    finally:
        locale.setlocale(locale.LC_ALL, "C")


def _designer_spelled_form() -> str:
    """Properties spelled the way Qt 6.8's DomProperty::write spells them."""
    body = "".join(
        ' <property name="p%s" stdset="0">\n  <%s>5</%s>\n </property>\n' % (index, tag, tag)
        for index, (tag, _kind, _text) in enumerate(_DESIGNER_INT_TAGS)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0"><widget class="QWidget" name="Form">\n%s</widget></ui>\n' % body
    )


def _is_typed_kind_tag(tag: str) -> bool:
    # Qt reads value tags case-insensitively, so <longLong> is the longlong kind.
    return tag.lower() in VALUE_CLASSES


def test_corpus_typed_values_are_not_kept_verbatim() -> None:
    failures = []
    folders = ("qt_examples", "synthetic")
    paths = [path for folder in folders for path in sorted((_CORPUS / folder).rglob("*.ui"))]
    assert paths
    sources = [(path.name, path.read_text(encoding="utf-8")) for path in paths]
    sources.append(("designer-spelled ints", _designer_spelled_form()))
    for name, text in sources:
        loaded = read_ui(text, allocator=IdAllocator())
        for item in loaded.diagnostics:
            if item.code != "FB005":
                continue
            match = _FB005_TAG.search(item.message)
            tag = match.group(1) if match else ""
            if _is_typed_kind_tag(tag):
                failures.append("%s: %s" % (name, item.message))
        for node in loaded.document.iter_preorder():
            entries = node.properties() + node.attributes()
            for entry in entries:
                element = entry.value.element if isinstance(entry.value, OpaqueValue) else None
                if element is not None and _is_typed_kind_tag(element.tag):
                    failures.append("%s property %s kept <%s>" % (name, entry.name, element.tag))
    assert failures == []


def _stable_real(rng: random.Random) -> float:
    parsed = parse_real(format_double(rng.uniform(-500.0, 500.0)))
    assert real_round_trips(parsed)
    return parsed


def _stable_float(rng: random.Random) -> float:
    parsed = parse_real(format_float(rng.uniform(-50.0, 50.0)))
    assert real_round_trips(parsed, element="float")
    return parsed


def _text(rng: random.Random) -> str:
    alphabet = "abcXYZ &<>\"'\n\t./:-_"
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8)))


def _color(rng: random.Random) -> ColorValue:
    alpha = None if rng.randrange(2) == 0 else rng.randint(0, 255)
    return ColorValue(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255), alpha)


def _pixmap(rng: random.Random) -> ResourcePixmap:
    resource = None if rng.randrange(2) == 0 else "icons.qrc"
    alias = None if rng.randrange(2) == 0 else _text(rng).replace("\n", "").replace("\t", "")
    return ResourcePixmap(":/cbcs/%s.png" % rng.randrange(100), resource, alias)


def _gradient(rng: random.Random) -> GradientValue:
    stops = tuple(
        GradientStop(_stable_real(rng), _color(rng))
        for _ in range(rng.randint(0, 3))
    )
    return GradientValue(
        type=rng.choice(["LinearGradient", "RadialGradient", "ConicalGradient", None]),
        spread=rng.choice(["PadSpread", "RepeatSpread", None]),
        coordinatemode=rng.choice(["LogicalMode", "ObjectMode", None]),
        startx=_stable_real(rng) if rng.randrange(2) else None,
        endy=_stable_real(rng) if rng.randrange(2) else None,
        angle=_stable_real(rng) if rng.randrange(2) else None,
        radius=_stable_real(rng) if rng.randrange(2) else None,
        stops=stops,
    )


def _brush(rng: random.Random) -> BrushValue:
    style = rng.choice(["SolidPattern", "NoBrush", "LinearGradientPattern", "TexturePattern", None])
    kind = rng.choice(["none", "color", "texture", "gradient"])
    if kind == "color":
        return BrushValue(style, _color(rng), None, None)
    if kind == "texture":
        name = None if rng.randrange(2) else "windowTexture"
        return BrushValue(style, None, _pixmap(rng), None, name)
    if kind == "gradient":
        return BrushValue(style, None, None, _gradient(rng))
    return BrushValue(style, None, None, None)


def _icon(rng: random.Random) -> IconSetValue:
    if rng.randrange(2) == 0:
        return IconSetValue(
            theme=rng.choice([None, "document-new"]),
            resource=rng.choice([None, "icons.qrc"]),
            text=":/icons/%s.png" % rng.randrange(20),
        )
    states = {}
    names = ("normaloff", "normalon", "disabledoff", "disabledon", "activeoff", "activeon", "selectedoff", "selectedon")
    for name in names:
        if rng.randrange(2):
            states[name] = _pixmap(rng)
    if not states:
        states["normaloff"] = _pixmap(rng)
    return IconSetValue(theme="document-new", resource="icons.qrc", text=None, **states)


def _palette(rng: random.Random) -> PaletteValue:
    def group() -> Tuple[ColorRole, ...]:
        roles = []
        for name in rng.sample(["Window", "WindowText", "Button", "Base"], rng.randint(0, 2)):
            roles.append(ColorRole(name, _brush(rng)))
        return tuple(roles)

    return PaletteValue(group(), group(), group())


def _random_value(rng: random.Random) -> Value:
    builders = [
        lambda: BoolValue(bool(rng.randrange(2))),
        lambda: NumberValue(rng.randint(-2147483648, 2147483647)),
        lambda: UIntValue(rng.randint(0, 4294967295)),
        lambda: LongLongValue(rng.randint(-9223372036854775808, 9223372036854775807)),
        lambda: ULongLongValue(rng.randint(0, 18446744073709551615)),
        lambda: FloatValue(_stable_float(rng)),
        lambda: DoubleValue(_stable_real(rng)),
        lambda: StringValue(_text(rng), rng.choice([None, True, False]), rng.choice([None, "note"]), None, rng.choice([None, "id"])),
        lambda: StringListValue(tuple(_text(rng) for _ in range(rng.randint(0, 3))), rng.choice([None, True])),
        lambda: CStringValue(_text(rng).replace("\n", "")),
        lambda: CharValue(rng.randint(0, 0x10FFFF)),
        lambda: EnumValue(rng.choice(["Qt::Horizontal", "Qt::Orientation::Vertical"])),
        lambda: SetValue(rng.choice(["0", "Qt::AlignLeft|Qt::AlignVCenter"])),
        lambda: CursorValue(rng.randint(-100, 100)),
        lambda: CursorShapeValue(rng.choice(["ArrowCursor", "Qt::IBeamCursor"])),
        lambda: PointValue(rng.randint(-20, 20), rng.randint(-20, 20)),
        lambda: PointFValue(_stable_real(rng), _stable_real(rng)),
        lambda: SizeValue(rng.randint(0, 40), rng.randint(0, 40)),
        lambda: SizeFValue(_stable_real(rng), _stable_real(rng)),
        lambda: RectValue(rng.randint(-5, 5), rng.randint(-5, 5), rng.randint(0, 30), rng.randint(0, 30)),
        lambda: RectFValue(_stable_real(rng), _stable_real(rng), _stable_real(rng), _stable_real(rng)),
        lambda: SizePolicyValue(rng.choice(["Preferred", "Expanding"]), rng.choice(["Fixed", "Minimum"]), rng.randint(0, 5), rng.randint(0, 5)),
        lambda: DateValue(rng.randint(1, 9999), rng.randint(1, 12), rng.randint(1, 28)),
        lambda: TimeValue(rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)),
        lambda: DateTimeValue(rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59), rng.randint(1, 9999), rng.randint(1, 12), rng.randint(1, 28)),
        lambda: LocaleValue(rng.choice(["English", "German"]), rng.choice(["UnitedStates", "Germany"])),
        lambda: UrlValue(StringValue(_text(rng).replace("\n", ""), notr=True)),
        lambda: _color(rng),
        lambda: _brush(rng),
        lambda: _palette(rng),
        lambda: FontValue(family=rng.choice([None, "Sans"]), pointsize=rng.choice([None, 12]), bold=rng.choice([None, True, False]), stylestrategy=rng.choice([None, "PreferDefault"])),
        lambda: _pixmap(rng),
        lambda: _icon(rng),
    ]
    return builders[rng.randrange(len(builders))]()


def _through_xml(value: Value) -> Value:
    document = read_ui(
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"><widget class="QWidget" name="Form"/></ui>\n',
        allocator=IdAllocator(),
    ).document
    apply(
        document,
        SetPropertyOp(
            owner=document.root.id,
            kind="property",
            name="v",
            entry=PropertyEntry("property", "v", value),
            index=0,
        ),
    )
    saved = write_ui(document).text
    second = write_ui(read_ui(saved, allocator=IdAllocator()).document).text
    assert second == saved
    restored = read_ui(saved, allocator=IdAllocator()).document.root.prop("v")
    assert restored is not None
    return restored.value


def test_random_values_round_trip() -> None:
    seed = int(os.environ.get("FB_SEED", "20261021"))
    rng = random.Random(seed)
    seen = set()
    for _ in range(48):
        original = _random_value(rng)
        seen.add(type(original))
        cloned = value_from_json(value_to_json(original))
        assert cloned == original, "FB_SEED=%s json %s" % (seed, type(original).__name__)
        restored = _through_xml(original)
        assert restored == original, "FB_SEED=%s xml %s\n%s" % (seed, type(original).__name__, original)
        assert semantic_equal(restored, original)
    assert len(seen) >= 20
