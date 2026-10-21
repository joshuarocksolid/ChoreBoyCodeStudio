"""Typed ui4 property values (CONTRACTS.md section 2.4).

Every value is a frozen, hashable dataclass. Commands, events and undo entries
share value objects by reference; nothing ever deep-copies a value.

One class per ui4 value element (R3 items 283-321). ``ELEMENT`` is the XML tag.
A value element the reader cannot represent losslessly becomes ``OpaqueValue``
(diagnostic FB005), so ``write(read(x))`` never changes what Qt would load.

Equality is structural (dataclass ``__eq__``). ``semantic_equal`` additionally
treats enum/set spellings that name the same enumerators as equal
(``Qt::Horizontal`` == ``Qt::Orientation::Horizontal``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple, Union

from app.features.form_builder.engine.ui4.opaque import OpaqueElement

# ----------------------------------------------------------------------------
# Scalars
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class BoolValue:
    """``<bool>``. Only ``true``/``false`` parse; anything else is OpaqueValue."""

    ELEMENT: ClassVar[str] = "bool"
    value: bool


@dataclass(frozen=True)
class NumberValue:
    """``<number>``: signed 32-bit. Out-of-range text becomes OpaqueValue."""

    ELEMENT: ClassVar[str] = "number"
    value: int


@dataclass(frozen=True)
class UIntValue:
    """``<uint>``: 0 .. 2**32-1."""

    ELEMENT: ClassVar[str] = "uint"
    value: int


@dataclass(frozen=True)
class LongLongValue:
    """``<longlong>``: signed 64-bit."""

    ELEMENT: ClassVar[str] = "longlong"
    value: int


@dataclass(frozen=True)
class ULongLongValue:
    """``<ulonglong>``: 0 .. 2**64-1."""

    ELEMENT: ClassVar[str] = "ulonglong"
    value: int


@dataclass(frozen=True)
class FloatValue:
    """``<float>``. Written with ``numfmt.format_real``. A text whose value does not
    survive ``parse(format(parse(text)))`` is kept as OpaqueValue."""

    ELEMENT: ClassVar[str] = "float"
    value: float


@dataclass(frozen=True)
class DoubleValue:
    """``<double>``. Same rule as FloatValue."""

    ELEMENT: ClassVar[str] = "double"
    value: float


@dataclass(frozen=True)
class StringValue:
    """``<string>``. ``text`` is exact (no stripping, no newline changes).

    ``notr``: None when the attribute is absent, else the parsed bool.
    ``comment`` is Qt's disambiguation, ``extracomment`` the translator comment,
    ``id`` the id-based translation id (R3 item 155).
    """

    ELEMENT: ClassVar[str] = "string"
    text: str
    notr: Optional[bool] = None
    comment: Optional[str] = None
    extracomment: Optional[str] = None
    id: Optional[str] = None


@dataclass(frozen=True)
class StringListValue:
    """``<stringlist>`` with ``<string>`` children (plain text items)."""

    ELEMENT: ClassVar[str] = "stringlist"
    items: Tuple[str, ...]
    notr: Optional[bool] = None
    comment: Optional[str] = None
    extracomment: Optional[str] = None
    id: Optional[str] = None


@dataclass(frozen=True)
class CStringValue:
    """``<cstring>``: untranslated identifier text (buddy names)."""

    ELEMENT: ClassVar[str] = "cstring"
    text: str


@dataclass(frozen=True)
class CharValue:
    """``<char><unicode>N</unicode></char>``."""

    ELEMENT: ClassVar[str] = "char"
    unicode: int


@dataclass(frozen=True)
class EnumValue:
    """``<enum>``: enumerator spelled as in the file (``Qt::AlignLeft`` or
    ``Qt::AlignmentFlag::AlignLeft``). Stored by name, never by int.

    ``text`` is kept verbatim. New values created by commands use the document's
    enum spelling style (``engine.ui4.document.UiDocument.enum_style``).
    """

    ELEMENT: ClassVar[str] = "enum"
    text: str

    def key(self) -> Tuple[str, str]:
        """``(scope, enumerator)`` with any enum-type qualifier removed:
        ``Qt::Orientation::Horizontal`` -> ``("Qt", "Horizontal")``."""
        ...


@dataclass(frozen=True)
class SetValue:
    """``<set>``: flag names joined by ``|``, verbatim. ``0`` or empty means no flags."""

    ELEMENT: ClassVar[str] = "set"
    text: str

    def keys(self) -> Tuple[Tuple[str, str], ...]:
        """Normalised ``(scope, enumerator)`` pairs, sorted, duplicates removed."""
        ...


@dataclass(frozen=True)
class CursorValue:
    """Legacy ``<cursor>`` integer shape id."""

    ELEMENT: ClassVar[str] = "cursor"
    value: int


@dataclass(frozen=True)
class CursorShapeValue:
    """``<cursorshape>``: shape name such as ``ArrowCursor``."""

    ELEMENT: ClassVar[str] = "cursorshape"
    name: str


# ----------------------------------------------------------------------------
# Geometry
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PointValue:
    ELEMENT: ClassVar[str] = "point"
    x: int
    y: int


@dataclass(frozen=True)
class PointFValue:
    ELEMENT: ClassVar[str] = "pointf"
    x: float
    y: float


@dataclass(frozen=True)
class SizeValue:
    ELEMENT: ClassVar[str] = "size"
    width: int
    height: int


@dataclass(frozen=True)
class SizeFValue:
    ELEMENT: ClassVar[str] = "sizef"
    width: float
    height: float


@dataclass(frozen=True)
class RectValue:
    ELEMENT: ClassVar[str] = "rect"
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class RectFValue:
    ELEMENT: ClassVar[str] = "rectf"
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SizePolicyValue:
    """``<sizepolicy hsizetype=".." vsizetype="..">`` with ``horstretch``/``verstretch``.

    ``hsizetype``/``vsizetype`` are policy names (``Preferred``, ``Expanding``...)
    as written. Legacy integer child forms are read into the same fields and
    re-written in attribute form (Designer does the same).
    """

    ELEMENT: ClassVar[str] = "sizepolicy"
    hsizetype: str
    vsizetype: str
    horstretch: int = 0
    verstretch: int = 0


# ----------------------------------------------------------------------------
# Time, locale, url
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class DateValue:
    ELEMENT: ClassVar[str] = "date"
    year: int
    month: int
    day: int


@dataclass(frozen=True)
class TimeValue:
    ELEMENT: ClassVar[str] = "time"
    hour: int
    minute: int
    second: int


@dataclass(frozen=True)
class DateTimeValue:
    ELEMENT: ClassVar[str] = "datetime"
    hour: int
    minute: int
    second: int
    year: int
    month: int
    day: int


@dataclass(frozen=True)
class LocaleValue:
    """``<locale language=".." country=".."/>`` with names as written."""

    ELEMENT: ClassVar[str] = "locale"
    language: str
    country: str


@dataclass(frozen=True)
class UrlValue:
    """``<url><string>..</string></url>``."""

    ELEMENT: ClassVar[str] = "url"
    string: StringValue


# ----------------------------------------------------------------------------
# Paint values
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ColorValue:
    """``<color alpha="..">`` with ``red``/``green``/``blue``. ``alpha`` None = absent."""

    ELEMENT: ClassVar[str] = "color"
    red: int
    green: int
    blue: int
    alpha: Optional[int] = None


@dataclass(frozen=True)
class GradientStop:
    position: float
    color: ColorValue


@dataclass(frozen=True)
class GradientValue:
    """``<gradient>``: every attribute optional and kept only when present."""

    ELEMENT: ClassVar[str] = "gradient"
    type: Optional[str] = None
    spread: Optional[str] = None
    coordinatemode: Optional[str] = None
    startx: Optional[float] = None
    starty: Optional[float] = None
    endx: Optional[float] = None
    endy: Optional[float] = None
    centralx: Optional[float] = None
    centraly: Optional[float] = None
    focalx: Optional[float] = None
    focaly: Optional[float] = None
    radius: Optional[float] = None
    angle: Optional[float] = None
    stops: Tuple[GradientStop, ...] = ()


@dataclass(frozen=True)
class ResourcePixmap:
    """``<pixmap resource=".." alias="..">path</pixmap>`` and the eight icon-state
    children of ``<iconset>``. ``path`` is a file path or a ``:/`` resource path."""

    ELEMENT: ClassVar[str] = "pixmap"
    path: str
    resource: Optional[str] = None
    alias: Optional[str] = None


@dataclass(frozen=True)
class BrushValue:
    """``<brush brushstyle="..">`` with exactly one of color, texture, gradient."""

    ELEMENT: ClassVar[str] = "brush"
    brushstyle: Optional[str] = None
    color: Optional[ColorValue] = None
    texture: Optional[ResourcePixmap] = None
    gradient: Optional[GradientValue] = None


@dataclass(frozen=True)
class ColorRole:
    """``<colorrole role="..">`` with a brush. Legacy palette ``<color>`` lists are
    read into the same shape with ``role`` set from Qt's legacy role order."""

    role: str
    brush: BrushValue


@dataclass(frozen=True)
class PaletteValue:
    """``<palette>`` with all three groups (required by the schema)."""

    ELEMENT: ClassVar[str] = "palette"
    active: Tuple[ColorRole, ...] = ()
    inactive: Tuple[ColorRole, ...] = ()
    disabled: Tuple[ColorRole, ...] = ()


@dataclass(frozen=True)
class FontValue:
    """``<font>``. Each child is optional; only present children are written, in the
    schema order: family, pointsize, weight, italic, bold, underline, strikeout,
    antialiasing, stylestrategy, kerning, hintingpreference, fontweight."""

    ELEMENT: ClassVar[str] = "font"
    family: Optional[str] = None
    pointsize: Optional[int] = None
    weight: Optional[int] = None
    italic: Optional[bool] = None
    bold: Optional[bool] = None
    underline: Optional[bool] = None
    strikeout: Optional[bool] = None
    antialiasing: Optional[bool] = None
    stylestrategy: Optional[str] = None
    kerning: Optional[bool] = None
    hintingpreference: Optional[str] = None
    fontweight: Optional[str] = None


@dataclass(frozen=True)
class IconSetValue:
    """``<iconset theme=".." resource="..">``: optional legacy text (a single path)
    plus up to eight state pixmaps (R3 item 165)."""

    ELEMENT: ClassVar[str] = "iconset"
    theme: Optional[str] = None
    resource: Optional[str] = None
    text: Optional[str] = None
    normaloff: Optional[ResourcePixmap] = None
    normalon: Optional[ResourcePixmap] = None
    disabledoff: Optional[ResourcePixmap] = None
    disabledon: Optional[ResourcePixmap] = None
    activeoff: Optional[ResourcePixmap] = None
    activeon: Optional[ResourcePixmap] = None
    selectedoff: Optional[ResourcePixmap] = None
    selectedon: Optional[ResourcePixmap] = None


@dataclass(frozen=True)
class OpaqueValue:
    """A value element kept verbatim: an unknown tag, or a known tag whose content
    does not parse losslessly. Written back byte-for-byte (modulo the writer's
    indentation). Not realized on the canvas; inspector shows it read-only with
    "Edit as XML". Diagnostic FB005 (Info) names it."""

    ELEMENT: ClassVar[str] = ""
    element: OpaqueElement


Value = Union[
    BoolValue,
    NumberValue,
    UIntValue,
    LongLongValue,
    ULongLongValue,
    FloatValue,
    DoubleValue,
    StringValue,
    StringListValue,
    CStringValue,
    CharValue,
    EnumValue,
    SetValue,
    CursorValue,
    CursorShapeValue,
    PointValue,
    PointFValue,
    SizeValue,
    SizeFValue,
    RectValue,
    RectFValue,
    SizePolicyValue,
    DateValue,
    TimeValue,
    DateTimeValue,
    LocaleValue,
    UrlValue,
    ColorValue,
    BrushValue,
    PaletteValue,
    FontValue,
    ResourcePixmap,
    IconSetValue,
    OpaqueValue,
]

#: Value element tag -> class. Exactly the 33 ui4 value elements (R3 283-315).
VALUE_CLASSES = {
    cls.ELEMENT: cls
    for cls in (
        BoolValue, NumberValue, UIntValue, LongLongValue, ULongLongValue,
        FloatValue, DoubleValue, StringValue, StringListValue, CStringValue,
        CharValue, EnumValue, SetValue, CursorValue, CursorShapeValue,
        PointValue, PointFValue, SizeValue, SizeFValue, RectValue, RectFValue,
        SizePolicyValue, DateValue, TimeValue, DateTimeValue, LocaleValue,
        UrlValue, ColorValue, BrushValue, PaletteValue, FontValue,
        ResourcePixmap, IconSetValue,
    )
}


def semantic_equal(a: Optional[Value], b: Optional[Value]) -> bool:
    """Structural equality, except EnumValue/SetValue compare by ``key()``/``keys()``.

    Used by SetProperty to detect no-op edits and by merge rules.
    """
    ...


def value_to_json(value: Value) -> object:
    """Canonical JSON form ``{"kind": ELEMENT, ...fields}`` used by the preview IPC
    and by command traces. Deterministic: keys in field order, floats as the
    ``numfmt.format_real`` string."""
    ...


def value_from_json(data: object) -> Value:
    """Inverse of ``value_to_json``. Raises ValueError on malformed data."""
    ...
