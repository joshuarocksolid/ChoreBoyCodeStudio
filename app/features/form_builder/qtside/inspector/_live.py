
from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
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
)
from app.features.form_builder.qtside.inspector.api import EnumSpec
from app.features.form_builder.qtside.inspector.model import LiveClass, LiveProperty
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtCore import QMetaMethod, QMetaObject, QMetaProperty
from app.qt.qt_compat import enum_value

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

_CACHE: Dict[str, LiveClass] = {}

def live_classes(
    realizer: Realizer, document: UiDocument, ids: Sequence[NodeId]
) -> Dict[NodeId, LiveClass]:
    found: Dict[NodeId, LiveClass] = {}
    for node_id in ids:
        node = document.node(node_id)
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
        found[node_id] = cached
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
