
from __future__ import annotations

import dataclasses
from typing import Dict, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, SpacerNode, WidgetNode
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    BrushValue,
    CharValue,
    ColorValue,
    CStringValue,
    CursorShapeValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    EnumValue,
    FloatValue,
    FontValue,
    IconSetValue,
    LocaleValue,
    LongLongValue,
    NumberValue,
    PaletteValue,
    PointFValue,
    PointValue,
    RectFValue,
    ResourcePixmap,
    RectValue,
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
)
from app.features.form_builder.qtside.inspector.api import EnumSpec
from app.features.form_builder.qtside.inspector.model import LiveClass, LiveProperty
from app.features.form_builder.qtside.realize import CANVAS_OVERRIDES, Realizer
from app.qt.QtCore import QMetaMethod, QMetaObject, QMetaProperty
from app.qt.QtWidgets import QWidget
from app.qt.qt_compat import delete_now, enum_value

_ELEMENT_FOR_TYPE: Mapping[str, str] = {
    "QString": StringValue.ELEMENT,
    "QKeySequence": StringValue.ELEMENT,
    "QStringList": StringListValue.ELEMENT,
    "QByteArray": CStringValue.ELEMENT,
    "QChar": CharValue.ELEMENT,
    "bool": BoolValue.ELEMENT,
    "int": NumberValue.ELEMENT,
    "uint": UIntValue.ELEMENT,
    "qlonglong": LongLongValue.ELEMENT,
    "qulonglong": ULongLongValue.ELEMENT,
    "double": DoubleValue.ELEMENT,
    "float": FloatValue.ELEMENT,
    "QPoint": PointValue.ELEMENT,
    "QPointF": PointFValue.ELEMENT,
    "QSize": SizeValue.ELEMENT,
    "QSizeF": SizeFValue.ELEMENT,
    "QRect": RectValue.ELEMENT,
    "QRectF": RectFValue.ELEMENT,
    "QSizePolicy": SizePolicyValue.ELEMENT,
    "QColor": ColorValue.ELEMENT,
    "QFont": FontValue.ELEMENT,
    "QCursor": CursorShapeValue.ELEMENT,
    "QPalette": PaletteValue.ELEMENT,
    "QIcon": IconSetValue.ELEMENT,
    "QPixmap": ResourcePixmap.ELEMENT,
    "QBrush": BrushValue.ELEMENT,
    "QDate": DateValue.ELEMENT,
    "QTime": TimeValue.ELEMENT,
    "QDateTime": DateTimeValue.ELEMENT,
    "QLocale": LocaleValue.ELEMENT,
    "QUrl": UrlValue.ELEMENT,
}

# A spacer is a QSpacerItem, which has no meta-object, so its size type
# choices are spelled out here.
_SPACER = LiveClass(
    ("Spacer",),
    (
        LiveProperty(
            "sizeType",
            "Spacer",
            EnumValue.ELEMENT,
            EnumSpec(
                "QSizePolicy",
                "Policy",
                ("Fixed", "Minimum", "Maximum", "Preferred", "MinimumExpanding", "Expanding", "Ignored"),
                False,
            ),
            EnumValue("QSizePolicy::Expanding"),
        ),
    ),
    (),
    (),
)

_CACHE: Dict[str, LiveClass] = {}
# Class name -> the CANVAS_OVERRIDES values of an unmodified instance.
_PRISTINE: Dict[str, Dict[str, Optional[Value]]] = {}

def live_classes(
    realizer: Realizer,
    document: UiDocument,
    ids: Sequence[NodeId],
    *,
    with_values: bool = False,
) -> Dict[NodeId, LiveClass]:
    found: Dict[NodeId, LiveClass] = {}
    for node_id in ids:
        node = document.node(node_id)
        if isinstance(node, SpacerNode):
            found[node_id] = _SPACER
            continue
        obj = None
        if isinstance(node, WidgetNode):
            obj = realizer.widget_for(node_id)
        elif isinstance(node, LayoutNode):
            obj = realizer.layout_for(node_id)
        if obj is None:
            continue
        meta = obj.metaObject()
        key = _text(meta.className())
        cached = _CACHE.get(key)
        if cached is None:
            cached = parse_meta_object(meta)
            if key:
                _CACHE[key] = cached
        found[node_id] = _stamp_values(obj, cached) if with_values else cached
    return found

def parse_meta_object(meta: QMetaObject) -> LiveClass:
    return LiveClass(_chain(meta), _properties(meta), *_methods(meta))

def _chain(meta: QMetaObject) -> Tuple[str, ...]:
    names = []
    seen = set()
    current: Optional[QMetaObject] = meta
    while current is not None:
        name = _text(current.className())
        if not name or name in seen:
            break
        seen.add(name)
        names.append(name)
        current = current.superClass()
    return tuple(names)

def _properties(meta: QMetaObject) -> Tuple[LiveProperty, ...]:
    found = []
    seen = set()
    current: Optional[QMetaObject] = meta
    while current is not None:
        declared = _text(current.className())
        for index in range(current.propertyOffset(), current.propertyCount()):
            prop = current.property(index)
            name = _text(prop.name())
            if not name or name in seen:
                continue
            if not _flag(prop, "isDesignable") or not _flag(prop, "isWritable"):
                continue
            seen.add(name)
            live = _property(prop, declared)
            if live is not None:
                found.append(live)
        current = current.superClass()
    return tuple(found)

def _property(prop: QMetaProperty, declared: str) -> Optional[LiveProperty]:
    name = _text(prop.name())
    if _flag(prop, "isEnumType"):
        return _enum_property(prop, name, declared)
    element = _ELEMENT_FOR_TYPE.get(_text(prop.typeName()))
    if element is None:
        return None
    return LiveProperty(name, declared, element)

def _enum_property(prop: QMetaProperty, name: str, declared: str) -> LiveProperty:
    enumerator = prop.enumerator()
    names = []
    for index in range(enumerator.keyCount()):
        key = _text(enumerator.key(index))
        if key:
            names.append(key)
    is_flag = bool(enumerator.isFlag())
    scope = _text(enumerator.scope())
    type_name = _text(enumerator.name()) if hasattr(enumerator, "name") else ""
    enum_name = getattr(enumerator, "enumName", None)
    if callable(enum_name):
        typed = _text(enum_name())
        if typed:
            type_name = typed
    element = SetValue.ELEMENT if is_flag else EnumValue.ELEMENT
    return LiveProperty(
        name,
        declared,
        element,
        EnumSpec(scope, type_name, tuple(names), is_flag),
    )

def _methods(meta: QMetaObject) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    signals = []
    slots = []
    seen_signals = set()
    seen_slots = set()
    current: Optional[QMetaObject] = meta
    while current is not None:
        for index in range(current.methodOffset(), current.methodCount()):
            method = current.method(index)
            if _same(method.access(), QMetaMethod.Private):
                continue
            signature = _text(method.methodSignature())
            if not signature or signature.startswith("_"):
                continue
            kind = method.methodType()
            if _same(kind, QMetaMethod.Signal) and signature not in seen_signals:
                seen_signals.add(signature)
                signals.append(signature)
            elif _same(kind, QMetaMethod.Slot) and signature not in seen_slots:
                seen_slots.add(signature)
                slots.append(signature)
        current = current.superClass()
    return tuple(signals), tuple(slots)

def _stamp_values(obj: object, shape: LiveClass) -> LiveClass:
    pristine = _pristine_values(obj, shape)
    stamped = []
    for prop in shape.properties:
        if prop.name in pristine:
            value = pristine[prop.name]
        else:
            value = _read_value(obj, prop)
        stamped.append(dataclasses.replace(prop, value=value))
    return LiveClass(shape.chain, tuple(stamped), shape.signals, shape.slots)


def _pristine_values(obj: object, shape: LiveClass) -> Dict[str, Optional[Value]]:
    """The canvas-overridden properties, read once per class from a fresh widget."""
    if not isinstance(obj, QWidget):
        return {}
    key = _text(obj.metaObject().className())
    cached = _PRISTINE.get(key)
    if cached is not None:
        return cached
    found: Dict[str, Optional[Value]] = {}
    overridden = [prop for prop in shape.properties if prop.name in CANVAS_OVERRIDES]
    if overridden:
        try:
            fresh = type(obj)()
        except (TypeError, RuntimeError):
            fresh = None
        for prop in overridden:
            found[prop.name] = None if fresh is None else _read_value(fresh, prop)
        if fresh is not None:
            delete_now(fresh)
    if key:
        _PRISTINE[key] = found
    return found


def _read_value(obj: object, prop: LiveProperty) -> Optional[Value]:
    meta = getattr(obj, "metaObject", None)
    if not callable(meta):
        return None
    meta_object = meta()
    index = meta_object.indexOfProperty(prop.name)
    if index < 0:
        return None
    qt_prop = meta_object.property(index)
    try:
        raw = qt_prop.read(obj)
    except (TypeError, RuntimeError, AttributeError):
        return None
    try:
        return _coerce(prop, qt_prop, raw)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return None


def _coerce(prop: LiveProperty, qt_prop: QMetaProperty, raw: object) -> Optional[Value]:
    if prop.enum is not None or _flag(qt_prop, "isEnumType"):
        return _coerce_enum(qt_prop, raw, flag=bool(prop.enum and prop.enum.is_flag))
    element = prop.element
    if element == BoolValue.ELEMENT:
        return BoolValue(bool(raw))
    if element in (
        NumberValue.ELEMENT,
        UIntValue.ELEMENT,
        LongLongValue.ELEMENT,
        ULongLongValue.ELEMENT,
    ):
        return _number(element, raw)
    if element in (DoubleValue.ELEMENT, FloatValue.ELEMENT):
        cls = FloatValue if element == FloatValue.ELEMENT else DoubleValue
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return cls(float(raw))
    if element == StringValue.ELEMENT:
        return StringValue("" if raw is None else _text(raw))
    if element == CStringValue.ELEMENT:
        return CStringValue("" if raw is None else _text(raw))
    if element == StringListValue.ELEMENT and isinstance(raw, (list, tuple)):
        return StringListValue(tuple(_text(item) for item in raw))
    if element == FontValue.ELEMENT:
        return _font_value(raw)
    if element == RectValue.ELEMENT:
        return _rect_value(raw)
    if element == SizeValue.ELEMENT:
        return _size_value(raw)
    if element == PointValue.ELEMENT:
        return _point_value(raw)
    if element == ColorValue.ELEMENT:
        return _color_value(raw)
    return None


def _number(element: str, raw: object) -> Optional[Value]:
    number = _as_int(raw)
    if number is None:
        return None
    if element == UIntValue.ELEMENT:
        return UIntValue(number)
    if element == LongLongValue.ELEMENT:
        return LongLongValue(number)
    if element == ULongLongValue.ELEMENT:
        return ULongLongValue(number)
    return NumberValue(number)


def _as_int(raw: object) -> Optional[int]:
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    try:
        return int(enum_value(raw))
    except (TypeError, ValueError):
        return None


def _call_int(raw: object, name: str) -> Optional[int]:
    method = getattr(raw, name, None)
    if not callable(method):
        return None
    found = method()
    return _as_int(found)


def _rect_value(raw: object) -> Optional[RectValue]:
    x = _call_int(raw, "x")
    y = _call_int(raw, "y")
    width = _call_int(raw, "width")
    height = _call_int(raw, "height")
    if x is None or y is None or width is None or height is None:
        return None
    return RectValue(x, y, width, height)


def _size_value(raw: object) -> Optional[SizeValue]:
    width = _call_int(raw, "width")
    height = _call_int(raw, "height")
    if width is None or height is None:
        return None
    return SizeValue(width, height)


def _point_value(raw: object) -> Optional[PointValue]:
    x = _call_int(raw, "x")
    y = _call_int(raw, "y")
    if x is None or y is None:
        return None
    return PointValue(x, y)


def _color_value(raw: object) -> Optional[ColorValue]:
    red = _call_int(raw, "red")
    green = _call_int(raw, "green")
    blue = _call_int(raw, "blue")
    alpha = _call_int(raw, "alpha")
    if red is None or green is None or blue is None or alpha is None:
        return None
    return ColorValue(red, green, blue, None if alpha == 255 else alpha)


def _coerce_enum(qt_prop: QMetaProperty, raw: object, *, flag: bool) -> Optional[Value]:
    enumerator = qt_prop.enumerator()
    number = int(enum_value(raw))
    if flag or bool(enumerator.isFlag()):
        keys = _text(enumerator.valueToKeys(number))
        return SetValue(keys) if keys else None
    key = _text(enumerator.valueToKey(number))
    return EnumValue(key) if key else None


def _font_value(raw: object) -> Optional[FontValue]:
    family = getattr(raw, "family", None)
    point = getattr(raw, "pointSize", None)
    bold = getattr(raw, "bold", None)
    italic = getattr(raw, "italic", None)
    if not callable(family):
        return None
    size = point() if callable(point) else -1
    return FontValue(
        family=_text(family()) or None,
        pointsize=int(size) if isinstance(size, int) and size > 0 else None,
        bold=bool(bold()) if callable(bold) else None,
        italic=bool(italic()) if callable(italic) else None,
    )


def _flag(prop: QMetaProperty, name: str) -> bool:
    method = getattr(prop, name)
    try:
        return bool(method())
    except TypeError:
        return bool(method(None))

def _same(left: object, right: object) -> bool:
    return enum_value(left) == enum_value(right)

def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    data = getattr(value, "data", None)
    if callable(data):
        raw = data()
        if isinstance(raw, bytes):
            return raw.decode("utf-8", "replace")
        if isinstance(raw, str):
            return raw
    return str(value)
