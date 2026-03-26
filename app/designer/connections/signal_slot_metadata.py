"""Signal/slot metadata helpers for designer connection editing."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

try:  # pragma: no cover - import guard only
    from PySide2.QtCore import QMetaMethod
    from PySide2.QtWidgets import QWidget
    import PySide2.QtWidgets as QtWidgets
except ImportError:  # pragma: no cover - exercised in environments without Qt
    QMetaMethod = None  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
    QtWidgets = None  # type: ignore[assignment]

from app.designer.model import UIModel


@dataclass(frozen=True)
class ConnectionObjectOption:
    """Object/class metadata for connection sender and receiver pickers."""

    object_name: str
    class_name: str


_FALLBACK_SIGNAL_OPTIONS: dict[str, tuple[str, ...]] = {
    "QPushButton": ("clicked()", "pressed()", "released()", "toggled(bool)"),
    "QCheckBox": ("clicked(bool)", "stateChanged(int)", "toggled(bool)"),
    "QRadioButton": ("clicked(bool)", "toggled(bool)"),
    "QLineEdit": ("textChanged(QString)", "textEdited(QString)", "returnPressed()"),
    "QComboBox": ("currentIndexChanged(int)", "currentTextChanged(QString)"),
}

_FALLBACK_SLOT_OPTIONS: dict[str, tuple[str, ...]] = {
    "QWidget": (
        "setFocus()",
        "setEnabled(bool)",
        "setVisible(bool)",
        "show()",
        "hide()",
        "close()",
    ),
    "QLineEdit": ("clear()", "setText(QString)", "setFocus()"),
    "QLabel": ("setText(QString)", "clear()", "setFocus()"),
}

_SIGNAL_ALIAS_OPTIONS: dict[str, tuple[str, ...]] = {
    "clicked()": ("clicked(bool)",),
    "clicked(bool)": ("clicked()",),
}

_SLOT_ALIAS_OPTIONS: dict[str, tuple[str, ...]] = {
    "setVisible(bool)": ("setHidden(bool)",),
    "setHidden(bool)": ("setVisible(bool)",),
}

_GENERIC_SIGNAL_OPTIONS: tuple[str, ...] = ("customSignal()",)
_GENERIC_SLOT_OPTIONS: tuple[str, ...] = ("setFocus()",)


def connection_object_options(model: UIModel) -> list[ConnectionObjectOption]:
    """Return deterministic object/class options for connection editing."""
    options: list[ConnectionObjectOption] = []
    for object_name in model.collect_object_names():
        widget = model.root_widget.find_by_object_name(object_name)
        if widget is None:
            continue
        options.append(ConnectionObjectOption(object_name=object_name, class_name=widget.class_name))
    return options


def signal_choices_for_class(class_name: str) -> tuple[str, ...]:
    """Return signal signatures available for a widget class."""
    class_key = class_name.strip()
    if not class_key:
        return _GENERIC_SIGNAL_OPTIONS
    signatures = _introspect_method_signatures(class_key, _signal_method_type())
    if signatures:
        return signatures
    fallback = _FALLBACK_SIGNAL_OPTIONS.get(class_key)
    if fallback:
        return fallback
    return _GENERIC_SIGNAL_OPTIONS


def slot_choices_for_class(class_name: str) -> tuple[str, ...]:
    """Return slot signatures available for a widget class."""
    class_key = class_name.strip()
    if not class_key:
        return _GENERIC_SLOT_OPTIONS
    signatures = _introspect_method_signatures(class_key, _slot_method_type())
    if signatures:
        return signatures
    fallback = _FALLBACK_SLOT_OPTIONS.get(class_key)
    if fallback:
        return fallback
    if _is_qwidget_class(class_key):
        widget_fallback = _FALLBACK_SLOT_OPTIONS.get("QWidget")
        if widget_fallback:
            return widget_fallback
    return _GENERIC_SLOT_OPTIONS


def has_class_specific_signal_catalog(class_name: str) -> bool:
    """Return whether class has non-generic signal metadata."""
    class_key = class_name.strip()
    if not class_key:
        return False
    if _introspect_method_signatures(class_key, _signal_method_type()):
        return True
    return class_key in _FALLBACK_SIGNAL_OPTIONS


def has_class_specific_slot_catalog(class_name: str) -> bool:
    """Return whether class has non-generic slot metadata."""
    class_key = class_name.strip()
    if not class_key:
        return False
    if _introspect_method_signatures(class_key, _slot_method_type()):
        return True
    if class_key in _FALLBACK_SLOT_OPTIONS:
        return True
    return _is_qwidget_class(class_key)


def signal_supported_for_class(class_name: str, signature: str) -> bool:
    """Return whether a signal signature is supported by class metadata."""
    value = signature.strip()
    if not value:
        return False
    candidates = signal_choices_for_class(class_name)
    if value in candidates:
        return True
    for alias in _SIGNAL_ALIAS_OPTIONS.get(value, ()):
        if alias in candidates:
            return True
    return False


def slot_supported_for_class(class_name: str, signature: str) -> bool:
    """Return whether a slot signature is supported by class metadata."""
    value = signature.strip()
    if not value:
        return False
    candidates = slot_choices_for_class(class_name)
    if value in candidates:
        return True
    for alias in _SLOT_ALIAS_OPTIONS.get(value, ()):
        if alias in candidates:
            return True
    return False


def is_signal_slot_pair_compatible(signal_signature: str, slot_signature: str) -> bool:
    """Check signature compatibility based on argument arity/type shape."""
    signal_name, signal_args = _parse_signature(signal_signature)
    slot_name, slot_args = _parse_signature(slot_signature)
    if not signal_name or not slot_name:
        return False
    if signal_name in {"clicked"} and signal_args == ("bool",):
        if len(slot_args) == 0:
            return True
    if len(slot_args) > len(signal_args):
        return False
    for index, slot_arg in enumerate(slot_args):
        signal_arg = signal_args[index]
        if not signal_arg or not slot_arg:
            continue
        if signal_arg == slot_arg:
            continue
        return False
    return True


def _parse_signature(signature: str) -> tuple[str, tuple[str, ...]]:
    value = signature.strip()
    if not value.endswith(")") or "(" not in value:
        return "", ()
    name, args_portion = value.split("(", 1)
    method_name = name.strip()
    raw_args = args_portion[:-1].strip()
    if not method_name:
        return "", ()
    if not raw_args:
        return method_name, ()
    args: list[str] = []
    for raw_arg in raw_args.split(","):
        normalized = _normalize_type_name(raw_arg)
        if normalized:
            args.append(normalized)
    return method_name, tuple(args)


def _normalize_type_name(raw_type: str) -> str:
    value = raw_type.strip()
    if not value:
        return ""
    compact = value.replace("const ", "").replace("&", "").strip()
    aliases = {
        "QStringList": "QStringList",
        "QString": "QString",
        "QVariant": "QVariant",
        "int": "int",
        "bool": "bool",
        "double": "double",
        "float": "float",
    }
    return aliases.get(compact, compact)


@lru_cache(maxsize=256)
def _introspect_method_signatures(class_name: str, method_type: int | None) -> tuple[str, ...]:
    if QtWidgets is None or method_type is None:
        return ()
    qt_class = getattr(QtWidgets, class_name, None)
    if qt_class is None:
        return ()
    static_meta_object = getattr(qt_class, "staticMetaObject", None)
    if static_meta_object is None:
        return ()
    signatures: list[str] = []
    seen: set[str] = set()
    meta_object = static_meta_object
    while meta_object is not None:
        method_offset = int(meta_object.methodOffset())
        method_count = int(meta_object.methodCount())
        for index in range(method_offset, method_count):
            method = meta_object.method(index)
            if int(method.methodType()) != method_type:
                continue
            signature = _method_signature_text(method)
            if not signature or signature in seen:
                continue
            seen.add(signature)
            signatures.append(signature)
        meta_object = meta_object.superClass()
    signatures.sort()
    return tuple(signatures)


def _method_signature_text(method: object) -> str:
    raw_value = method.methodSignature()  # type: ignore[call-arg]
    if isinstance(raw_value, bytes):
        return raw_value.decode("utf-8", errors="ignore")
    if hasattr(raw_value, "data"):
        data = raw_value.data()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="ignore")
    return str(raw_value)


def _signal_method_type() -> int | None:
    if QMetaMethod is None:
        return None
    return int(QMetaMethod.Signal)


def _slot_method_type() -> int | None:
    if QMetaMethod is None:
        return None
    return int(QMetaMethod.Slot)


@lru_cache(maxsize=256)
def _is_qwidget_class(class_name: str) -> bool:
    if QtWidgets is None:
        return False
    qt_class = getattr(QtWidgets, class_name, None)
    if qt_class is None:
        return False
    try:
        return bool(issubclass(qt_class, QWidget))
    except TypeError:
        return False
