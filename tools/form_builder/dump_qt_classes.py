# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false
"""Write the Qt class table the form builder reads (CONTRACTS.md section 2.5).

Run under FreeCAD 1.1's PySide6 with QT_QPA_PLATFORM=offscreen, from the repo root::

    QT_QPA_PLATFORM=offscreen /Applications/FreeCAD.app/Contents/Resources/bin/python \
        tools/form_builder/dump_qt_classes.py

It rewrites ``app/features/form_builder/engine/ui4/data/qt_classes.json``. The JSON
shape is documented in ``engine/ui4/defaults.py``. ``--json`` prints the table to
stdout instead of writing it. ``--check`` exits 1 when the committed file differs.

What goes in the table: ``QObject``, ``QAction``, ``QActionGroup``, ``QButtonGroup``
and every widget and layout class of QtWidgets (plus the few extra widget modules
named in ``EXTRA_MODULES`` when they import), with every super class between them.

Defaults are read from a live instance. A value that depends on the style, the font
or the window (found by dumping twice under different styles and fonts) is marked
``volatile`` and carries no default. Qt enums that PySide cannot read through
``QObject.property`` are read through the widget's getter method.

The dump is deterministic: classes are sorted by name, properties keep the order of
Qt's meta-object (which is Designer's property-sheet order), and floats use the
engine's number formatting.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = (
    REPO_ROOT / "app" / "features" / "form_builder" / "engine" / "ui4" / "data" / "qt_classes.json"
)
FORMAT_VERSION = 1

#: Modules (besides QtWidgets) whose widget classes a form can hold. A module that
#: does not import here is left out of the table (and the header says which).
EXTRA_MODULES = ("QtOpenGLWidgets", "QtQuickWidgets", "QtSvgWidgets")

#: Classes Qt cannot instantiate (PySide raises) plus the ones that are abstract in
#: the C++ sense even where PySide lets them through.
ABSTRACT = frozenset(
    {
        "QAbstractButton",
        "QAbstractItemView",
        "QAbstractScrollArea",
        "QAbstractSlider",
        "QAbstractSpinBox",
        "QLayout",
    }
)

#: Widgets that hold dropped widgets (the engine's container test), and the
#: subset that holds pages. Same list the query layer fell back on.
PAGE_CONTAINERS = frozenset(
    {"QTabWidget", "QStackedWidget", "QToolBox", "QSplitter", "QWizard", "QMdiArea"}
)
CONTAINERS = PAGE_CONTAINERS | frozenset(
    {
        "QWidget",
        "QFrame",
        "QGroupBox",
        "QScrollArea",
        "QMainWindow",
        "QDialog",
        "QDockWidget",
        "QWizardPage",
        "QMenu",
        "QToolBar",
        "QMenuBar",
        "QStatusBar",
    }
)
MAIN_WINDOW_PARTS = frozenset({"QMenuBar", "QToolBar", "QStatusBar", "QDockWidget"})

#: Designer's double-click ("go to slot") signal per class family.
DEFAULT_SIGNALS = {
    "QCheckBox": "toggled(bool)",
    "QRadioButton": "toggled(bool)",
    "QAbstractButton": "clicked()",
    "QLineEdit": "editingFinished()",
    "QPlainTextEdit": "textChanged()",
    "QTextEdit": "textChanged()",
    "QComboBox": "currentIndexChanged(int)",
    "QDoubleSpinBox": "valueChanged(double)",
    "QSpinBox": "valueChanged(int)",
    "QAbstractSlider": "valueChanged(int)",
    "QTimeEdit": "timeChanged(QTime)",
    "QDateTimeEdit": "dateChanged(QDate)",
    "QTabWidget": "currentChanged(int)",
    "QListWidget": "itemActivated(QListWidgetItem*)",
    "QAbstractItemView": "activated(QModelIndex)",
    "QDialogButtonBox": "accepted()",
    "QAction": "triggered()",
}

#: Properties Designer adds to its property sheet that Qt's meta-object lacks, in the
#: order Designer writes them (appended after the class's own meta-object properties).
#: ``(name, kind)``. Their default is unknown. The resaved corpus pins the order:
#: margins follow ``spacing`` and ``sizeConstraint`` on box layouts; a grid or form
#: layout writes ``spacing`` after the margins, so those classes declare it again here
#: (the most derived declaration decides the position).
DESIGNER_EXTRA = {
    "QLayout": (
        ("margin", "number"),
        ("leftMargin", "number"),
        ("topMargin", "number"),
        ("rightMargin", "number"),
        ("bottomMargin", "number"),
    ),
    "QGridLayout": (("spacing", "number"),),
    "QFormLayout": (("spacing", "number"),),
    "QLabel": (("buddy", "cstring"),),
}

#: Properties whose value is a window or run-time state, not a default.
STATE_PROPERTIES = frozenset(
    {
        "geometry",
        "frameGeometry",
        "normalGeometry",
        "x",
        "y",
        "pos",
        "frameSize",
        "size",
        "width",
        "height",
        "rect",
        "childrenRect",
        "childrenRegion",
        "minimumSizeHint",
        "sizeHint",
        "visible",
        "isActiveWindow",
        "focus",
        "layoutDirection",
        "locale",
        # The calendar opens on today.
        "selectedDate",
        # Follows the frame width, which follows the style.
        "frameRect",
        # The platform decides whether the menu bar lives in the system menu bar.
        "nativeMenuBar",
    }
)

#: ui4 kinds whose default is never kept: they depend on style, font or platform.
VOLATILE_KINDS = frozenset({"font", "palette", "brush", "color", "locale", "iconset", "pixmap"})

#: Qt type name -> ui4 value element.
_KINDS = {
    "bool": "bool",
    "int": "number",
    "uint": "uint",
    "qlonglong": "longlong",
    "qulonglong": "ulonglong",
    "double": "double",
    "qreal": "double",
    "float": "float",
    "QString": "string",
    "QStringList": "stringlist",
    "QByteArray": "cstring",
    "QChar": "char",
    "QPoint": "point",
    "QPointF": "pointf",
    "QSize": "size",
    "QSizeF": "sizef",
    "QRect": "rect",
    "QRectF": "rectf",
    "QSizePolicy": "sizepolicy",
    "QDate": "date",
    "QTime": "time",
    "QDateTime": "datetime",
    "QLocale": "locale",
    "QUrl": "url",
    "QColor": "color",
    "QBrush": "brush",
    "QPalette": "palette",
    "QFont": "font",
    "QIcon": "iconset",
    "QPixmap": "pixmap",
    "QCursor": "cursorShape",
    "QKeySequence": "string",
}


# ----------------------------------------------------------------------------
# Class discovery
# ----------------------------------------------------------------------------


def _modules() -> Tuple[List[Any], List[str]]:
    import importlib

    from PySide6 import QtCore, QtGui, QtWidgets

    mods: List[Any] = [QtCore, QtGui, QtWidgets]
    missing: List[str] = []
    for name in EXTRA_MODULES:
        try:
            mods.append(importlib.import_module("PySide6." + name))
        except ImportError:
            missing.append(name)
    return mods, missing


def _classes() -> Tuple[Dict[str, type], List[str]]:
    """Meta class name -> Python class for everything that belongs in the table."""
    from PySide6 import QtCore, QtGui, QtWidgets

    mods, missing = _modules()
    found: Dict[str, type] = {}
    seeds = (QtCore.QObject, QtGui.QAction, QtGui.QActionGroup, QtWidgets.QButtonGroup)
    for mod in mods:
        for name in dir(mod):
            value = getattr(mod, name)
            if not isinstance(value, type) or not issubclass(value, QtCore.QObject):
                continue
            if value.__module__ not in {m.__name__ for m in mods}:
                continue
            if issubclass(value, (QtWidgets.QWidget, QtWidgets.QLayout)) or value in seeds:
                found[value.staticMetaObject.className()] = value
    pending = list(found.values())
    while pending:
        cls = pending.pop()
        parent = cls.staticMetaObject.superClass()
        if parent is None or parent.className() in found:
            continue
        for base in cls.__mro__[1:]:
            meta = getattr(base, "staticMetaObject", None)
            if meta is not None and meta.className() == parent.className():
                found[parent.className()] = base
                pending.append(base)
                break
    return found, missing


# ----------------------------------------------------------------------------
# Value conversion
# ----------------------------------------------------------------------------


def _enum_name(meta_enum: Any) -> str:
    return "%s::%s" % (meta_enum.scope(), meta_enum.enumName())


def _kind_of(prop: Any) -> str:
    if prop.isFlagType():
        return "set"
    if prop.isEnumType():
        return "enum"
    return _KINDS.get(prop.typeName(), "other")


def _enum_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return int(value)
    inner = getattr(value, "value", None)
    if isinstance(inner, int):
        return int(inner)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read(obj: Any, prop: Any) -> Any:
    """The property's current value, or ``_UNREADABLE``."""
    try:
        value = prop.read(obj)
    except Exception:
        value = _UNREADABLE
    if value is not _UNREADABLE:
        return value
    getter = getattr(obj, str(prop.name()), None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return _UNREADABLE
    return _UNREADABLE


class _Unreadable:
    pass


_UNREADABLE = _Unreadable()


def _default_json(prop: Any, kind: str, value: Any) -> Optional[object]:
    """The ui4 value for ``value`` as the engine's JSON, or None."""
    from app.features.form_builder.engine.ui4 import values as v

    if value is _UNREADABLE or value is None:
        return None
    made: Optional[object] = None
    if kind in ("enum", "set"):
        number = _enum_int(value)
        if number is None:
            return None
        meta_enum = prop.enumerator()
        scope = _enum_name(meta_enum)
        if kind == "enum":
            key = meta_enum.valueToKey(number)
            if not key:
                return None
            made = v.EnumValue("%s::%s" % (scope, _text(key)))
        else:
            raw = meta_enum.valueToKeys(number)
            keys = sorted(piece for piece in _text(raw).split("|") if piece)
            made = v.SetValue("|".join("%s::%s" % (scope, key) for key in keys) if keys else "0")
    elif kind == "bool":
        made = v.BoolValue(bool(value))
    elif kind == "number":
        made = v.NumberValue(int(value))
    elif kind == "uint":
        made = v.UIntValue(int(value))
    elif kind == "longlong":
        made = v.LongLongValue(int(value))
    elif kind == "ulonglong":
        made = v.ULongLongValue(int(value))
    elif kind == "double":
        made = v.DoubleValue(float(value))
    elif kind == "float":
        made = v.FloatValue(float(value))
    elif kind == "string":
        text = value.toString() if hasattr(value, "toString") else str(value)
        made = v.StringValue(str(text))
    elif kind == "stringlist":
        made = v.StringListValue(tuple(str(item) for item in value))
    elif kind == "cstring":
        made = v.CStringValue(_text(bytes(value)))
    elif kind == "point":
        made = v.PointValue(value.x(), value.y())
    elif kind == "pointf":
        made = v.PointFValue(float(value.x()), float(value.y()))
    elif kind == "size":
        made = v.SizeValue(value.width(), value.height())
    elif kind == "sizef":
        made = v.SizeFValue(float(value.width()), float(value.height()))
    elif kind == "rect":
        made = v.RectValue(value.x(), value.y(), value.width(), value.height())
    elif kind == "rectf":
        made = v.RectFValue(
            float(value.x()), float(value.y()), float(value.width()), float(value.height())
        )
    elif kind == "sizepolicy":
        made = v.SizePolicyValue(
            value.horizontalPolicy().name,
            value.verticalPolicy().name,
            int(value.horizontalStretch()),
            int(value.verticalStretch()),
        )
    elif kind == "date":
        if not value.isValid():
            return None
        made = v.DateValue(value.year(), value.month(), value.day())
    elif kind == "time":
        if not value.isValid():
            return None
        made = v.TimeValue(value.hour(), value.minute(), value.second())
    elif kind == "datetime":
        if not value.isValid():
            return None
        date, time = value.date(), value.time()
        made = v.DateTimeValue(
            time.hour(), time.minute(), time.second(), date.year(), date.month(), date.day()
        )
    elif kind == "url":
        made = v.UrlValue(v.StringValue(value.toString()))
    elif kind == "cursorShape":
        made = v.CursorShapeValue(value.shape().name)
    if made is None:
        return None
    payload = v.value_to_json(made)  # type: ignore[arg-type]
    assert isinstance(payload, dict)
    return {key: item for key, item in payload.items() if item is not None}


def _text(raw: Any) -> str:
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode("utf-8")
    try:
        return bytes(raw.data()).decode("utf-8")
    except Exception:
        return str(raw)


def _machine_dependent(cls: type, name: str) -> bool:
    """Defaults that follow the locale, the installed fonts or the platform."""
    from PySide6 import QtWidgets

    if name in ("text", "displayFormat") and issubclass(
        cls, (QtWidgets.QAbstractSpinBox, QtWidgets.QDateTimeEdit)
    ):
        return True
    if issubclass(cls, QtWidgets.QFontComboBox) and name in ("count", "currentText", "currentIndex"):
        return True
    return issubclass(cls, QtWidgets.QFileDialog) and name == "viewMode"


# ----------------------------------------------------------------------------
# Collection
# ----------------------------------------------------------------------------


_KEPT: List[Any] = []
#: Parent for the widgets the parented pass builds (None: no parent).
_PARENT: Optional[Any] = None


def _keep(item: Any) -> Any:
    _KEPT.append(item)
    return item


def _instance(cls: type) -> Optional[Any]:
    """A live object to read defaults from, or None for layouts Qt cannot build.

    An abstract widget (``QAbstractButton`` and friends) is built through a bare
    Python subclass, which keeps the base class's own defaults.
    """
    from PySide6 import QtWidgets

    if _PARENT is not None and issubclass(cls, QtWidgets.QWidget):
        try:
            return cls(_PARENT)
        except Exception:
            pass
    try:
        return cls()
    except Exception:
        pass
    from PySide6 import QtCore

    name = cls.staticMetaObject.className()
    arguments = {
        "QActionGroup": lambda: (None,),
        "QBoxLayout": lambda: (QtWidgets.QBoxLayout.Direction.LeftToRight,),
        "QHeaderView": lambda: (QtCore.Qt.Orientation.Horizontal,),
        "QRubberBand": lambda: (QtWidgets.QRubberBand.Shape.Rectangle,),
        "QSizeGrip": lambda: (_keep(QtWidgets.QWidget()),),
        "QSplitterHandle": lambda: (
            QtCore.Qt.Orientation.Horizontal,
            _keep(QtWidgets.QSplitter()),
        ),
    }.get(name)
    if arguments is not None:
        try:
            return cls(*arguments())
        except Exception:
            return None
    if issubclass(cls, QtWidgets.QWidget):
        try:
            return type("_Probe", (cls,), {})()
        except Exception:
            return None
    return None


class _Collector:
    """Walks the classes once for one style and font and yields raw defaults."""

    def __init__(self, classes: Dict[str, type]) -> None:
        self.classes = classes
        self.enums: Dict[str, Dict[str, object]] = {}

    def defaults(self) -> Dict[str, Dict[str, Optional[object]]]:
        """class name -> property name -> default JSON (None when unknown)."""
        found: Dict[str, Dict[str, Optional[object]]] = {}
        for name, cls in self.classes.items():
            if os.environ.get("CBCS_DUMP_TRACE"):
                sys.stderr.write("class %s\n" % name)
                sys.stderr.flush()
            obj = _instance(cls)
            table: Dict[str, Optional[object]] = {}
            meta = cls.staticMetaObject
            for index in range(meta.propertyCount()):
                prop = meta.property(index)
                kind = _kind_of(prop)
                if os.environ.get("CBCS_DUMP_TRACE"):
                    sys.stderr.write("  %s\n" % prop.name())
                    sys.stderr.flush()
                if obj is None:
                    table[str(prop.name())] = None
                    continue
                table[str(prop.name())] = _default_json(prop, kind, _read(obj, prop))
            found[name] = table
            if obj is not None and hasattr(obj, "deleteLater"):
                try:
                    obj.deleteLater()
                except Exception:
                    pass
        return found


def _remember_enum(enums: Dict[str, Dict[str, object]], meta_enum: Any) -> None:
    name = _enum_name(meta_enum)
    if name in enums:
        return
    flag_type: Optional[str] = None
    if meta_enum.isFlag():
        flag_type = "%s::%s" % (meta_enum.scope(), meta_enum.name())
    keys = [
        [_text(meta_enum.key(i)), int(meta_enum.value(i))] for i in range(meta_enum.keyCount())
    ]
    enums[name] = {"flag_type": flag_type, "is_flag": bool(meta_enum.isFlag()), "keys": keys}


def _own_methods(meta: Any) -> Tuple[List[str], List[str]]:
    from PySide6.QtCore import QMetaMethod

    signals: List[str] = []
    slots: List[str] = []
    for index in range(meta.methodOffset(), meta.methodCount()):
        method = meta.method(index)
        signature = _text(method.methodSignature())
        if method.methodType() == QMetaMethod.MethodType.Signal:
            if signature not in signals:
                signals.append(signature)
        elif method.methodType() == QMetaMethod.MethodType.Slot:
            if method.access() == QMetaMethod.Access.Public and signature not in slots:
                slots.append(signature)
    return signals, slots


def _module_of(cls: type) -> str:
    return cls.__module__.split(".")[-1]


def _order(classes: Dict[str, type]) -> List[str]:
    """Class names, super classes before their subclasses."""
    ordered: List[str] = []
    seen: Set[str] = set()

    def visit(name: str) -> None:
        if name in seen or name not in classes:
            return
        seen.add(name)
        parent = classes[name].staticMetaObject.superClass()
        if parent is not None:
            visit(parent.className())
        ordered.append(name)

    for name in sorted(classes):
        visit(name)
    return ordered


def _reject_today(classes: Dict[str, object]) -> None:
    """A default that is today's date would fail tomorrow: it has to be volatile."""
    from PySide6.QtCore import QDate

    today = QDate.currentDate()
    wanted = (today.year(), today.month(), today.day())
    for name, body in classes.items():
        assert isinstance(body, dict)
        found = [(item["name"], item["default"]) for item in body["properties"]]
        found.extend(body["defaults"].items())
        for prop, default in found:
            if isinstance(default, dict) and default.get("kind") in ("date", "datetime"):
                if (default["year"], default["month"], default["day"]) == wanted:
                    raise SystemExit("%s.%s defaults to today; mark it volatile" % (name, prop))


def build() -> Dict[str, object]:
    from PySide6 import QtCore, QtWidgets
    import PySide6

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["dump_qt_classes"])
    classes, missing = _classes()

    # Pass A is the reference. Pass B (other style, font and locale) and pass C (every
    # widget built with a parent) find what varies: those defaults are volatile.
    global _PARENT
    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QFont

    base_font = QFont(app.font())

    def settle(style: str, size: int, locale: str) -> None:
        # Only the size changes: some Linux Qt builds crash on a missing family
        # once the default locale is set.
        font = QFont(base_font)
        font.setPointSize(size)
        app.setStyle(style)
        app.setFont(font)
        QLocale.setDefault(QLocale(locale))

    settle("Fusion", 10, "en_US")
    first = _Collector(classes).defaults()
    settle("Windows", 17, "de_DE")
    second = _Collector(classes).defaults()
    settle("Fusion", 10, "en_US")
    _PARENT = _keep(QtWidgets.QWidget())
    third = _Collector(classes).defaults()
    _PARENT = None

    enums: Dict[str, Dict[str, object]] = {}
    out_classes: Dict[str, object] = {}
    resolved: Dict[str, Dict[str, Optional[object]]] = {}
    for name in _order(classes):
        cls = classes[name]
        meta = cls.staticMetaObject
        parent = meta.superClass()
        parent_name = parent.className() if parent is not None else None
        inherited = resolved.get(parent_name, {}) if parent_name else {}
        own_defaults: Dict[str, Optional[object]] = {}
        overrides: Dict[str, object] = {}
        props: List[Dict[str, object]] = []
        obj = _instance(cls)
        for index in range(meta.propertyCount()):
            prop = meta.property(index)
            pname = str(prop.name())
            kind = _kind_of(prop)
            reading = first[name].get(pname)
            varies = reading != second[name].get(pname) or reading != third[name].get(pname)
            volatile = (
                varies
                or pname in STATE_PROPERTIES
                or kind in VOLATILE_KINDS
                or _machine_dependent(cls, pname)
            )
            default = None if volatile else reading
            enum_type: Optional[str] = None
            if prop.isEnumType() or prop.isFlagType():
                _remember_enum(enums, prop.enumerator())
                enum_type = _enum_name(prop.enumerator())
            if index >= meta.propertyOffset():
                designable = bool(prop.isDesignable())
                notify = _text(prop.notifySignal().methodSignature()) if prop.hasNotifySignal() else None
                props.append(
                    {
                        "name": pname,
                        "kind": kind,
                        "default": default,
                        "designable": designable,
                        "stored": bool(prop.isStored()),
                        "volatile": bool(volatile),
                        "enum": enum_type,
                        "notify": notify,
                    }
                )
                own_defaults[pname] = default
            else:
                before = inherited.get(pname)
                if obj is None:
                    default = before
                if default != before:
                    overrides[pname] = default
                own_defaults[pname] = default
        for extra_name, extra_kind in DESIGNER_EXTRA.get(name, ()):
            props.append(
                {
                    "name": extra_name,
                    "kind": extra_kind,
                    "default": None,
                    "designable": True,
                    "stored": True,
                    "volatile": True,
                    "enum": None,
                    "notify": None,
                    "extra": True,
                }
            )
            own_defaults[extra_name] = None
        resolved[name] = own_defaults
        signals, slots = _own_methods(meta)
        flags: List[str] = []
        if issubclass(cls, QtWidgets.QLayout):
            flags.append("layout")
        elif issubclass(cls, QtWidgets.QWidget):
            flags.append("widget")
        if name in CONTAINERS:
            flags.append("container")
        if name in PAGE_CONTAINERS:
            flags.append("page_container")
        if name in MAIN_WINDOW_PARTS:
            flags.append("main_window_part")
        if name in ABSTRACT or obj is None:
            flags.append("abstract")
        body: Dict[str, object] = {
            "super": parent_name,
            "module": _module_of(cls),
            "flags": flags,
            "properties": props,
            "defaults": overrides,
            "signals": signals,
            "slots": slots,
            "default_signal": DEFAULT_SIGNALS.get(name),
        }
        out_classes[name] = body
    _reject_today(out_classes)
    # Sub-classes inherit a default signal from the nearest family entry in the
    # engine; the table lists it only on the family class itself.
    return {
        "format": FORMAT_VERSION,
        "qt_version": QtCore.qVersion(),
        "pyside_version": PySide6.__version__,
        "platform": sys.platform,
        "style": "Fusion",
        "missing_modules": missing,
        "classes": out_classes,
        "enums": {key: enums[key] for key in sorted(enums)},
    }


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------


def _line(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def render(table: Dict[str, object]) -> str:
    """Stable text: one class per block, one property per line."""
    out = ["{\n"]
    for key in ("format", "qt_version", "pyside_version", "platform", "style", "missing_modules"):
        out.append(" %s:%s,\n" % (_line(key), _line(table[key])))
    out.append(' "classes":{\n')
    classes = table["classes"]
    assert isinstance(classes, dict)
    names = sorted(classes)
    for position, name in enumerate(names):
        body = classes[name]
        out.append("  %s:{\n" % _line(name))
        for key in ("super", "module", "flags", "defaults", "signals", "slots", "default_signal"):
            out.append("   %s:%s,\n" % (_line(key), _line(body[key])))
        out.append('   "properties":[')
        props = body["properties"]
        for index, prop in enumerate(props):
            out.append("\n    " + _line(prop) + ("," if index + 1 < len(props) else "\n   "))
        out.append("]\n  }" + ("," if position + 1 < len(names) else "") + "\n")
    out.append(" },\n")
    out.append(' "enums":{\n')
    enums = table["enums"]
    assert isinstance(enums, dict)
    keys = sorted(enums)
    for index, key in enumerate(keys):
        out.append("  %s:%s%s\n" % (_line(key), _line(enums[key]), "," if index + 1 < len(keys) else ""))
    out.append(" }\n}\n")
    return "".join(out)


def main(argv: List[str]) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    table = build()
    text = render(table)
    json.loads(text)
    if "--json" in argv:
        sys.stdout.write(text)
        return 0
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != text:
            sys.stderr.write("qt_classes.json differs from the running Qt\n")
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    sys.stdout.write("wrote %s (%d bytes)\n" % (TARGET, len(text)))
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    # Qt widgets built here crash some Linux builds during interpreter teardown.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
