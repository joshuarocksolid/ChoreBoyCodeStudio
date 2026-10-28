"""Apply one document property to a live Qt object.

Build and patch both go through these functions, so a patched tree and a fresh
build read back the same values. A missing setter is recorded and skipped.
Nothing here raises for a bad value.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.qt import QtCore, QtGui, QtWidgets
from app.qt.QtCore import QDate, QDateTime, QPoint, QRect, QSize, QTime, Qt, QUrl
from app.qt.QtGui import QBrush, QColor, QFont, QIcon, QImageReader, QPalette, QPixmap
from app.qt.QtWidgets import QFrame, QSizePolicy
from app.qt.qt_compat import enum_value
from app.features.form_builder.engine.logic.storage import is_logic_key
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.qtside.realize.forced import CANVAS_OVERRIDES
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    BrushValue,
    ColorRole,
    ColorValue,
    CStringValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    EnumValue,
    FloatValue,
    FontValue,
    ICON_STATES,
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
)

_MARGINS = ("leftMargin", "topMargin", "rightMargin", "bottomMargin")
_SKIP = frozenset({"buddy", "cbcsSplitterSizes"})

# uic applies the legacy value first. A stored side or axis then wins, in any file order.
_METRIC_ORDER = ("margin",) + _MARGINS + ("spacing", "horizontalSpacing", "verticalSpacing")
_METRIC_NAMES = frozenset(_METRIC_ORDER)


def ordered_layout_metrics(
    entries: Sequence[PropertyEntry],
    override_name: Optional[str] = None,
    override: Optional[PropertyEntry] = None,
) -> List[PropertyEntry]:
    """Margin and spacing entries in uic order.

    ``margin`` is applied before any side, and ``spacing`` before
    ``horizontalSpacing`` or ``verticalSpacing``. File order does not matter.
    ``override`` replaces ``override_name``. ``override`` None drops it.
    """
    by_name: Dict[str, PropertyEntry] = {}
    for entry in entries:
        if entry.name in _METRIC_NAMES:
            by_name[entry.name] = entry
    if override_name in _METRIC_NAMES:
        if override is None:
            by_name.pop(override_name, None)
        else:
            by_name[override_name] = override
    return [by_name[name] for name in _METRIC_ORDER if name in by_name]


#: (node id, property name) -> why the canvas widget did not take the value (UX-PED-009).
Refusals = Dict[Tuple[int, str], str]

REFUSED_BY_QT = "Qt refused this value."
_NODE_ID = "_cbcsNodeId"


def apply_entry(
    obj: object,
    entry: PropertyEntry,
    *,
    is_root: bool,
    resolve_path: Callable[[str], str],
    problems: List[str],
    refusals: Optional[Refusals] = None,
) -> bool:
    """Apply ``entry``. False when the value was skipped or rejected.

    With ``refusals``, a value Qt refuses (``setProperty`` returns False for a
    real property, or the setter raises) is recorded under the object's node
    id, and a value it takes clears that record.
    """
    name = entry.name
    if name in _SKIP or is_logic_key(name) or name in CANVAS_OVERRIDES:
        return False
    value = entry.value
    if isinstance(value, OpaqueValue):
        return False
    try:
        if name == "orientation" and _is_line(obj):
            _apply_line_orientation(obj, value)
            return _took(obj, name, refusals)
        if name == "geometry" and isinstance(value, (RectValue, RectFValue)):
            apply_geometry(obj, value, is_root)
            return _took(obj, name, refusals)
        if name in _MARGINS or name == "margin":
            _apply_margin(obj, name, int(_number(value)))
            return _took(obj, name, refusals)
        if isinstance(value, SizePolicyValue):
            _apply_size_policy(obj, value)
            return _took(obj, name, refusals)
        qvalue = to_qt(value, resolve_path)
        if qvalue is None:
            return False
        reason = _picture_reason(value, resolve_path, qvalue)
        setter = _setter(obj, name)
        if setter is None:
            if not set_property_checked(obj, name, qvalue):
                return _refuse(obj, name, REFUSED_BY_QT, refusals)
            return _finish(obj, name, refusals, reason)
        try:
            setter(qvalue)
        except (TypeError, ValueError, OverflowError):
            if not set_property_checked(obj, name, qvalue):
                return _refuse(obj, name, REFUSED_BY_QT, refusals)
        return _finish(obj, name, refusals, reason)
    except (TypeError, ValueError, OverflowError, RuntimeError, AttributeError) as exc:
        problems.append("%s.%s: %s" % (_type_name(obj), name, exc))
        return _refuse(obj, name, str(exc) or REFUSED_BY_QT, refusals)


def _is_line(obj: object) -> bool:
    try:
        return bool(obj.property("_cbcs_line"))  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, TypeError):
        return False


def _apply_line_orientation(obj: object, value: object) -> None:
    """Designer turns a line's orientation into the frame shape."""
    text = str(getattr(value, "text", ""))
    name = "VLine" if "Vertical" in text else "HLine"
    shape = getattr(getattr(QFrame, "Shape", QFrame), name)
    obj.setFrameShape(shape)  # type: ignore[attr-defined]


def set_property_checked(obj: object, name: str, value: object) -> bool:
    """``setProperty``; False only when ``name`` is a real Qt property that refused the value.

    A name that is not a Q_PROPERTY becomes a dynamic property, which Qt also
    reports as False; that is not a refusal.
    """
    taken = bool(obj.setProperty(name, value))  # type: ignore[attr-defined]
    if taken:
        return True
    meta = obj.metaObject()  # type: ignore[attr-defined]
    return meta.indexOfProperty(name) < 0


def _finish(obj: object, name: str, refusals: Optional[Refusals], reason: Optional[str]) -> bool:
    if reason:
        return _refuse(obj, name, reason, refusals)
    return _took(obj, name, refusals)


def _took(obj: object, name: str, refusals: Optional[Refusals]) -> bool:
    if refusals:
        key = _refusal_key(obj, name)
        if key is not None:
            refusals.pop(key, None)
    return True


def _refuse(obj: object, name: str, reason: str, refusals: Optional[Refusals]) -> bool:
    if refusals is not None:
        key = _refusal_key(obj, name)
        if key is not None:
            refusals[key] = reason
    return False


def _refusal_key(obj: object, name: str) -> Optional[Tuple[int, str]]:
    try:
        raw = obj.property(_NODE_ID)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, TypeError):
        return None
    if raw is None:
        return None
    try:
        return int(raw), name
    except (TypeError, ValueError):
        return None


def to_qt(value: Value, resolve_path: Callable[[str], str]) -> object:
    """A Qt value, or None when this value is not shown on the canvas."""
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    if isinstance(value, BoolValue):
        return value.value
    if isinstance(value, (NumberValue, UIntValue, LongLongValue, ULongLongValue)):
        return value.value
    if isinstance(value, (DoubleValue, FloatValue)):
        return value.value
    if isinstance(value, StringListValue):
        return list(value.items)
    if isinstance(value, (EnumValue, SetValue)):
        return resolve_enum(value.text)
    if isinstance(value, PointValue):
        return QPoint(value.x, value.y)
    if isinstance(value, PointFValue):
        return QPoint(int(value.x), int(value.y))
    if isinstance(value, SizeValue):
        return QSize(value.width, value.height)
    if isinstance(value, SizeFValue):
        return QSize(int(value.width), int(value.height))
    if isinstance(value, RectValue):
        return QRect(value.x, value.y, value.width, value.height)
    if isinstance(value, RectFValue):
        return QRect(int(value.x), int(value.y), int(value.width), int(value.height))
    if isinstance(value, ColorValue):
        return _color(value)
    if isinstance(value, FontValue):
        return _font(value)
    if isinstance(value, ResourcePixmap):
        disk = resolve_path(value.path) if value.path else ""
        return QPixmap(disk) if disk else QPixmap()
    if isinstance(value, IconSetValue):
        return _icon(value, resolve_path)
    if isinstance(value, PaletteValue):
        return _palette(value)
    if isinstance(value, BrushValue):
        return _brush(value, resolve_path)
    if isinstance(value, DateValue):
        return QDate(value.year, value.month, value.day)
    if isinstance(value, TimeValue):
        return QTime(value.hour, value.minute, value.second)
    if isinstance(value, DateTimeValue):
        return QDateTime(QDate(value.year, value.month, value.day), QTime(value.hour, value.minute, value.second))
    if isinstance(value, UrlValue):
        return QUrl(value.string.text)
    if isinstance(value, LocaleValue):
        return value.language
    return None


def resolve_enum(text: str) -> object:
    """``Qt::AlignLeft`` or a ``|`` set of those spellings. None when unknown."""
    combined: Any = None
    for piece in text.split("|"):
        parts = [part.strip() for part in piece.strip().split("::") if part.strip()]
        if len(parts) < 2:
            continue
        member = _enum_member(parts, QtCore, QtGui, QtWidgets)
        if member is None:
            continue
        combined = member if combined is None else combined | member
    return combined


def text_of(value: Value) -> str:
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    if isinstance(value, EnumValue):
        return value.text
    return ""


def apply_geometry(obj: object, value: object, is_root: bool) -> None:
    if isinstance(value, RectValue):
        x, y, width, height = value.x, value.y, value.width, value.height
    elif isinstance(value, RectFValue):
        x, y, width, height = int(value.x), int(value.y), int(value.width), int(value.height)
    else:
        return
    if is_root:
        obj.resize(width, height)  # type: ignore[attr-defined]
        return
    obj.setGeometry(x, y, width, height)  # type: ignore[attr-defined]


def _apply_margin(obj: object, name: str, amount: int) -> None:
    margins = obj.contentsMargins()  # type: ignore[attr-defined]
    left, top, right, bottom = margins.left(), margins.top(), margins.right(), margins.bottom()
    if name == "margin":
        left = top = right = bottom = amount
    elif name == "leftMargin":
        left = amount
    elif name == "topMargin":
        top = amount
    elif name == "rightMargin":
        right = amount
    elif name == "bottomMargin":
        bottom = amount
    obj.setContentsMargins(left, top, right, bottom)  # type: ignore[attr-defined]


def _apply_size_policy(obj: object, value: SizePolicyValue) -> None:
    policy_enum = getattr(QSizePolicy, "Policy", QSizePolicy)
    horiz = getattr(policy_enum, value.hsizetype, None)
    vert = getattr(policy_enum, value.vsizetype, None)
    if horiz is None:
        horiz = QSizePolicy.Preferred
    if vert is None:
        vert = QSizePolicy.Preferred
    policy = QSizePolicy(horiz, vert)
    policy.setHorizontalStretch(value.horstretch)
    policy.setVerticalStretch(value.verstretch)
    if hasattr(obj, "sizePolicy"):
        policy.setHeightForWidth(obj.sizePolicy().hasHeightForWidth())  # type: ignore[attr-defined]
    obj.setSizePolicy(policy)  # type: ignore[attr-defined]


def _setter(obj: object, name: str) -> Optional[Callable[..., object]]:
    if not name:
        return None
    method = getattr(obj, "set" + name[0].upper() + name[1:], None)
    if callable(method):
        return method
    return None


def _enum_member(parts: List[str], qt_core: object, qt_gui: object, qt_widgets: object) -> Any:
    name = parts[-1]
    scope_name = parts[0]
    if scope_name == "Qt":
        owner: object = Qt
    else:
        owner = None
        for module in (qt_widgets, qt_gui, qt_core):
            if hasattr(module, scope_name):
                owner = getattr(module, scope_name)
                break
        if owner is None:
            return None
    if len(parts) >= 3:
        enum_type = getattr(owner, parts[-2], None)
        if enum_type is not None and hasattr(enum_type, name):
            return getattr(enum_type, name)
    if hasattr(owner, name):
        return getattr(owner, name)
    return None


def _color(value: ColorValue) -> QColor:
    color = QColor(value.red, value.green, value.blue)
    if value.alpha is not None:
        color.setAlpha(value.alpha)
    return color


def _font(value: FontValue) -> QFont:
    font = QFont()
    if value.family:
        font.setFamily(value.family)
    if value.pointsize:
        font.setPointSize(value.pointsize)
    if value.bold is not None:
        font.setBold(value.bold)
    elif value.weight is not None and value.weight >= 63:
        font.setBold(True)
    if value.italic is not None:
        font.setItalic(value.italic)
    if value.underline is not None:
        font.setUnderline(value.underline)
    if value.strikeout is not None:
        font.setStrikeOut(value.strikeout)
    if value.kerning is not None:
        font.setKerning(value.kerning)
    return font


_ICON_FILES = (
    ("normaloff", "Normal", "Off"),
    ("normalon", "Normal", "On"),
    ("disabledoff", "Disabled", "Off"),
    ("disabledon", "Disabled", "On"),
    ("activeoff", "Active", "Off"),
    ("activeon", "Active", "On"),
    ("selectedoff", "Selected", "Off"),
    ("selectedon", "Selected", "On"),
)


def _icon(value: IconSetValue, resolve_path: Callable[[str], str]) -> QIcon:
    icon = QIcon()
    if value.theme:
        themed = QIcon.fromTheme(value.theme)
        if not themed.isNull():
            icon = themed
    added = False
    for attr, mode_name, state_name in _ICON_FILES:
        pixmap = getattr(value, attr)
        path = pixmap.path if isinstance(pixmap, ResourcePixmap) else ""
        if not path and attr == "normaloff" and value.text:
            path = value.text
        if not path:
            continue
        disk = resolve_path(path)
        if not disk or not os.path.isfile(disk):
            continue
        icon.addFile(disk, QSize(), _icon_enum("Mode", mode_name), _icon_enum("State", state_name))
        added = True
    if added or (value.theme and not icon.isNull()):
        return icon
    return QIcon()


def _icon_enum(group: str, name: str) -> object:
    enum = getattr(QIcon, group, QIcon)
    return getattr(enum, name)


def _palette(value: PaletteValue) -> QPalette:
    palette = QPalette()
    _paint_group(palette, QPalette.Active, value.active)
    _paint_group(palette, QPalette.Inactive, value.inactive)
    _paint_group(palette, QPalette.Disabled, value.disabled)
    return palette


def _paint_group(palette: QPalette, group: object, roles: Tuple[ColorRole, ...]) -> None:
    for role in roles:
        qt_role = getattr(QPalette, role.role, None)
        if qt_role is None or role.brush.color is None:
            continue
        palette.setColor(group, qt_role, _color(role.brush.color))


def _brush(value: BrushValue, resolve_path: Callable[[str], str]) -> QBrush:
    if value.texture is not None and value.texture.path:
        disk = resolve_path(value.texture.path)
        pixmap = QPixmap(disk) if disk else QPixmap()
        return QBrush(pixmap)
    if value.color is not None:
        return QBrush(_color(value.color))
    return QBrush()


def _number(value: Value) -> float:
    if isinstance(value, (NumberValue, UIntValue, LongLongValue, ULongLongValue, DoubleValue, FloatValue)):
        return float(value.value)
    return 0.0


def _type_name(obj: object) -> str:
    return type(obj).__name__


def norm_qt(value: object) -> object:
    """A comparable form of a Qt readback."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    horizontal = getattr(value, "horizontalPolicy", None)
    vertical = getattr(value, "verticalPolicy", None)
    if callable(horizontal) and callable(vertical):
        stretch_h = getattr(value, "horizontalStretch", None)
        stretch_v = getattr(value, "verticalStretch", None)
        return (
            _enum_name(horizontal()),
            _enum_name(vertical()),
            int(stretch_h()) if callable(stretch_h) else 0,
            int(stretch_v()) if callable(stretch_v) else 0,
        )
    raw = getattr(value, "value", None)
    if raw is not None and not isinstance(value, (bytes, bytearray)):
        try:
            return enum_value(value)
        except (TypeError, ValueError):
            return str(value)
    if hasattr(value, "width") and hasattr(value, "height") and hasattr(value, "x"):
        return (value.x(), value.y(), value.width(), value.height())  # type: ignore[operator]
    if hasattr(value, "width") and hasattr(value, "height"):
        return (value.width(), value.height())  # type: ignore[operator]
    name = getattr(value, "name", None)
    if callable(name):
        try:
            return name()
        except TypeError:
            pass
    text = getattr(value, "text", None)
    if callable(text):
        return text()
    kind = type(value).__name__
    if kind == "QFont":
        to_string = getattr(value, "toString", None)
        if callable(to_string):
            return to_string()
    if kind == "QCursor":
        shape = getattr(value, "shape", None)
        if callable(shape):
            return _enum_name(shape())
    if kind == "QPalette":
        return _palette_norm(value)
    if kind == "QIcon":
        return _icon_norm(value)
    return str(value)


def _palette_norm(palette: QPalette) -> Tuple[Tuple[str, str, str], ...]:
    group_owner = getattr(QPalette, "ColorGroup", QPalette)
    role_owner = getattr(QPalette, "ColorRole", QPalette)
    groups = ("Active", "Inactive", "Disabled")
    roles = (
        "Window",
        "WindowText",
        "Base",
        "Text",
        "Button",
        "ButtonText",
        "Highlight",
        "HighlightedText",
    )
    found = []
    for group_name in groups:
        group = getattr(group_owner, group_name)
        for role_name in roles:
            role = getattr(role_owner, role_name, None)
            if role is None:
                continue
            found.append((group_name, role_name, palette.color(group, role).name()))
    return tuple(found)


def _icon_norm(icon: QIcon) -> Tuple[object, ...]:
    if icon.isNull():
        return ("icon",)
    sizes = tuple(sorted((size.width(), size.height()) for size in icon.availableSizes()))
    extent = max((max(width, height) for width, height in sizes), default=16)
    image = icon.pixmap(max(extent, 1), max(extent, 1)).toImage()
    return ("icon", sizes, _image_token(image))


def _image_token(image: object) -> bytes:
    import hashlib

    from app.qt.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    saved = image.save(buffer, "PNG")  # type: ignore[attr-defined]
    if not saved:
        return b""
    return hashlib.sha256(bytes(buffer.data())).digest()


def _enum_name(value: object) -> str:
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name.split("::")[-1]
    return str(value).rsplit(".", 1)[-1]


def resolve_stored_picture(stored: str, base_dir: str, document: object) -> str:
    """A ``:/`` path becomes the image file from the form's ``.qrc``. Other paths stay on disk."""
    from app.features.form_builder.engine.project.pictures import index_for_document, lookup_stored

    if stored.startswith(":/"):
        _disk, missing = lookup_stored(stored, base_dir, index_for_document(document, base_dir))
        return "" if missing else _disk
    return path_under(base_dir, stored)


def _picture_reason(value: Value, resolve_path: Callable[[str], str], qvalue: object) -> Optional[str]:
    if isinstance(value, ResourcePixmap) and isinstance(qvalue, QPixmap):
        # Already decoded once: a null pixmap is a missing or unreadable file.
        return "Code Studio can't find %s." % value.path if value.path and qvalue.isNull() else None
    for stored in _picture_paths(value):
        disk = resolve_path(stored)
        # The header says whether Qt can read it; decoding it twice per apply would not.
        if not disk or not os.path.isfile(disk) or not QImageReader(disk).canRead():
            return "Code Studio can't find %s." % stored
    return None


def _picture_paths(value: Value) -> Tuple[str, ...]:
    if isinstance(value, ResourcePixmap):
        return (value.path,) if value.path else ()
    if isinstance(value, IconSetValue):
        found = []
        for name in ICON_STATES:
            pixmap = getattr(value, name)
            if isinstance(pixmap, ResourcePixmap) and pixmap.path:
                found.append(pixmap.path)
        if not found and value.text:
            found.append(value.text)
        return tuple(found)
    if isinstance(value, BrushValue) and value.texture is not None and value.texture.path:
        return (value.texture.path,)
    return ()


def path_under(base_dir: str, path: str) -> str:
    if path.startswith(":/") or os.path.isabs(path):
        return path
    return os.path.join(base_dir, path)
