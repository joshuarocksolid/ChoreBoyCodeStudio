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

import dataclasses
from dataclasses import dataclass
from typing import ClassVar, Dict, Optional, Tuple, Type, Union, get_type_hints

from app.features.form_builder.engine.ui4.numfmt import format_real, parse_real
from app.features.form_builder.engine.ui4.opaque import OpaqueComment, OpaqueElement, OpaquePI

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


def _enum_key(text: str) -> Tuple[str, str]:
    parts = text.split("::")
    if len(parts) == 1:
        return ("", parts[0])
    return (parts[0], parts[-1])


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
        return _enum_key(self.text)


@dataclass(frozen=True)
class SetValue:
    """``<set>``: flag names joined by ``|``, verbatim. ``0`` or empty means no flags."""

    ELEMENT: ClassVar[str] = "set"
    text: str

    def keys(self) -> Tuple[Tuple[str, str], ...]:
        """Normalised ``(scope, enumerator)`` pairs, sorted, duplicates removed."""
        found = []
        seen = set()
        for piece in self.text.split("|"):
            name = piece.strip()
            if not name or name == "0":
                continue
            item = _enum_key(name)
            if item in seen:
                continue
            seen.add(item)
            found.append(item)
        found.sort()
        return tuple(found)


@dataclass(frozen=True)
class CursorValue:
    """Legacy ``<cursor>`` integer shape id."""

    ELEMENT: ClassVar[str] = "cursor"
    value: int


@dataclass(frozen=True)
class CursorShapeValue:
    """``<cursorShape>``: shape name such as ``ArrowCursor``.

    Qt 6.8 writes ``cursorShape``. The ui4 schema and older files use
    ``cursorshape``. The reader accepts both. JSON kind ``cursorshape`` is
    the same value.
    """

    ELEMENT: ClassVar[str] = "cursorShape"
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
    """``<brush brushstyle="..">`` with at most one of color, texture, gradient.

    ``texture_name`` is the optional ``name`` attribute on the ``<texture>``
    wrapper. It is absent when the attribute was not in the file.
    """

    ELEMENT: ClassVar[str] = "brush"
    brushstyle: Optional[str] = None
    color: Optional[ColorValue] = None
    texture: Optional[ResourcePixmap] = None
    gradient: Optional[GradientValue] = None
    texture_name: Optional[str] = None


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


#: Child tags of ``<iconset>``, in the order the writer emits them.
ICON_STATES: Tuple[str, ...] = (
    "normaloff",
    "normalon",
    "disabledoff",
    "disabledon",
    "activeoff",
    "activeon",
    "selectedoff",
    "selectedon",
)


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
    if a is None or b is None:
        return a is b
    if isinstance(a, EnumValue) and isinstance(b, EnumValue):
        return a.key() == b.key()
    if isinstance(a, SetValue) and isinstance(b, SetValue):
        return a.keys() == b.keys()
    return a == b


def value_to_json(value: Value) -> object:
    """Canonical JSON form ``{"kind": ELEMENT, ...fields}`` used by the preview IPC
    and by command traces. Deterministic: keys in field order, floats as the
    ``numfmt.format_real`` string."""
    kind = value.ELEMENT or "opaque"
    payload: Dict[str, object] = {"kind": kind}
    for field in dataclasses.fields(value):
        payload[field.name] = _to_json(getattr(value, field.name))
    return payload


def value_from_json(data: object) -> Value:
    """Inverse of ``value_to_json``. Raises ValueError on malformed data."""
    if not isinstance(data, dict) or "kind" not in data:
        raise ValueError("value json needs a kind")
    kind = data["kind"]
    if not isinstance(kind, str):
        raise ValueError("value kind must be a string")
    if kind == "opaque":
        element = data.get("element")
        return OpaqueValue(element=_element_from_json(element))
    if kind == "cursorshape":
        kind = CursorShapeValue.ELEMENT
    cls = VALUE_CLASSES.get(kind)
    if cls is None:
        raise ValueError("unknown value kind %r" % (kind,))
    return _dataclass_from_json(cls, data)


def _to_json(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return format_real(value)
    if isinstance(value, tuple):
        return [_to_json(item) for item in value]
    if isinstance(value, OpaqueElement):
        return {
            "tag": value.tag,
            "attrs": [[key, item] for key, item in value.attrs],
            "children": [_to_json(child) for child in value.children],
        }
    if isinstance(value, OpaqueComment):
        return {"$": "comment", "text": value.text}
    if isinstance(value, OpaquePI):
        return {"$": "pi", "target": value.target, "data": value.data}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        payload: Dict[str, object] = {}
        element = getattr(value, "ELEMENT", None)
        if isinstance(element, str) and element:
            payload["kind"] = element
        for field in dataclasses.fields(value):
            payload[field.name] = _to_json(getattr(value, field.name))
        return payload
    raise TypeError("cannot encode %r" % (type(value).__name__,))


def _from_json(annotation: object, data: object) -> object:
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is Union:
        if data is None:
            return None
        for option in args:
            if option is type(None):  # noqa: E721
                continue
            try:
                return _from_json(option, data)
            except (TypeError, ValueError):
                continue
        raise ValueError("cannot decode %r" % (data,))
    if origin in (tuple, Tuple):
        if not isinstance(data, list):
            raise ValueError("expected a list")
        item_type = args[0] if args else object
        return tuple(_from_json(item_type, item) for item in data)
    if annotation is float or annotation == float:
        if isinstance(data, str):
            return parse_real(data)
        if isinstance(data, (int, float)):
            return float(data)
        raise ValueError("expected a real")
    if annotation in (int, str, bool):
        if not isinstance(data, annotation):
            raise ValueError("expected %s" % (annotation,))
        return data
    if annotation is OpaqueElement or annotation == OpaqueElement:
        return _element_from_json(data)
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return _dataclass_from_json(annotation, data)
    if isinstance(data, annotation):
        return data
    raise ValueError("cannot decode %r as %r" % (data, annotation))


def _element_from_json(data: object) -> OpaqueElement:
    if not isinstance(data, dict):
        raise ValueError("opaque element must be an object")
    tag = data.get("tag")
    attrs = data.get("attrs", [])
    children = data.get("children", [])
    if not isinstance(tag, str) or not isinstance(attrs, list) or not isinstance(children, list):
        raise ValueError("malformed opaque element")
    return OpaqueElement(
        tag=tag,
        attrs=tuple((str(pair[0]), str(pair[1])) for pair in attrs),
        children=tuple(_opaque_child_from_json(child) for child in children),
    )


def _opaque_child_from_json(data: object) -> object:
    if isinstance(data, str):
        return data
    if isinstance(data, dict) and data.get("$") == "comment":
        return OpaqueComment(text=str(data.get("text", "")))
    if isinstance(data, dict) and data.get("$") == "pi":
        return OpaquePI(target=str(data.get("target", "")), data=str(data.get("data", "")))
    return _element_from_json(data)


def _dataclass_from_json(cls: Type[object], data: object) -> object:
    if not isinstance(data, dict):
        raise ValueError("expected an object for %s" % (cls.__name__,))
    hints = get_type_hints(cls)
    kwargs = {}
    for field in dataclasses.fields(cls):  # type: ignore[arg-type]
        if field.name not in data:
            if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:  # type: ignore[misc]
                raise ValueError("%s is missing %s" % (cls.__name__, field.name))
            continue
        kwargs[field.name] = _from_json(hints[field.name], data[field.name])
    return cls(**kwargs)
