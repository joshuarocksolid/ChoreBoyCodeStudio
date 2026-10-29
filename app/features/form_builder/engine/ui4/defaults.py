"""The committed Qt class table (CONTRACTS.md section 2.5).

Data file: ``engine/ui4/data/qt_classes.json``, produced by
``tools/form_builder/dump_qt_classes.py`` running under FreeCAD 1.1's PySide6
with ``QT_QPA_PLATFORM=offscreen``. The engine reads only the JSON; it never
imports Qt. A test (section 13) re-runs the dump under the current Qt and fails
on any difference, naming the class and property.

JSON shape (version 1)::

    {
      "format": 1,
      "qt_version": "6.8.3",
      "pyside_version": "6.8.3",
      "classes": {
        "QPushButton": {
          "super": "QAbstractButton",
          "module": "QtWidgets",
          "flags": ["widget"],            # widget | layout | container | page_container
                                          # | main_window_part | abstract
          "properties": [                 # meta-object order, own properties only
            {"name": "autoDefault", "kind": "bool", "default": {"kind": "bool", "value": false},
             "designable": true, "stored": true, "volatile": false,
             "enum": null, "notify": null}
          ],
          "defaults": {"sizePolicy": {...}},  # inherited properties whose default this
                                          # class changes (value json, or null for none)
          "signals": ["clicked(bool)", "pressed()", ...],   # own, normalised signatures
          "slots": ["showMenu()", ...],
          "default_signal": "clicked()"   # Designer's double-click default, or null
        },
        ...
      },
      "enums": {
        "Qt::AlignmentFlag": {"flag_type": "Qt::Alignment", "is_flag": true,
                              "keys": [["AlignLeft", 1], ...]},
        ...
      }
    }

``default`` uses ``values.value_to_json``. ``volatile`` marks defaults that depend
on platform, style or fonts (font, palette, geometry, sizeHint...): they are
never shown as "the default value" in the inspector and never compared.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.ui4.values import Value, value_from_json

DATA_FILE = "data/qt_classes.json"
FORMAT_VERSION = 1

_LOCK = threading.Lock()
_SHARED: Optional["QtClassTable"] = None
_ANCESTORS: Dict[int, Tuple[str, ...]] = {}


@dataclass(frozen=True)
class PropertyInfo:
    name: str
    #: ui4 value element used for this property (``number``, ``enum``, ``set``...).
    kind: str
    default: Optional[Value]
    designable: bool
    stored: bool
    volatile: bool
    #: Qualified enum or flag type for ``enum``/``set`` kinds, e.g. ``Qt::AlignmentFlag``.
    enum: Optional[str]
    #: Position in Designer property-sheet order across the class chain
    #: (QObject first). Used for rank insertion of new property entries.
    rank: int
    #: The class that declares it (for "inherited from" display).
    declared_by: str


@dataclass(frozen=True)
class EnumInfo:
    name: str
    is_flag: bool
    flag_type: Optional[str]
    keys: Tuple[Tuple[str, int], ...]

    def key_for(self, value: int) -> Optional[str]:
        for key, number in self.keys:
            if number == value:
                return key
        return None

    def value_of(self, key: str) -> Optional[int]:
        for name, number in self.keys:
            if name == key:
                return number
        return None


@dataclass(frozen=True)
class ClassInfo:
    name: str
    super_name: Optional[str]
    module: str
    flags: Tuple[str, ...]
    default_signal: Optional[str]

    def is_a(self, base: str) -> bool:
        """True when ``base`` is this class or an ancestor."""
        chain = _ANCESTORS.get(id(self), (self.name,))
        return base in chain


class QtClassTable:
    """Read-only, process-wide, loaded lazily on first use (budget: 25 ms CPU,
    once per process). Thread-safe for reads."""

    def __init__(
        self,
        qt_version: str,
        classes: Dict[str, ClassInfo],
        properties: Dict[str, Tuple[PropertyInfo, ...]],
        signals: Dict[str, Tuple[str, ...]],
        slots: Dict[str, Tuple[str, ...]],
        enums: Dict[str, EnumInfo],
        overrides: Optional[Dict[str, Dict[str, Optional[Value]]]] = None,
    ) -> None:
        self._qt_version = qt_version
        self._classes = classes
        self._properties = properties
        self._signals = signals
        self._slots = slots
        self._enums = enums
        self._overrides = overrides or {}
        self._resolved: Dict[str, Tuple[PropertyInfo, ...]] = {}
        self._by_name: Dict[Tuple[str, str], Optional[PropertyInfo]] = {}

    @classmethod
    def shared(cls) -> "QtClassTable":
        global _SHARED
        with _LOCK:
            if _SHARED is None:
                _SHARED = _load()
            return _SHARED

    @property
    def qt_version(self) -> str:
        return self._qt_version

    def class_info(self, class_name: str) -> Optional[ClassInfo]:
        """None for unknown classes. Custom widgets resolve through their
        ``extends`` (callers use ``effective_class``)."""
        return self._classes.get(class_name)

    def chain(self, class_name: str) -> Tuple[ClassInfo, ...]:
        """Leaf first, QObject last."""
        found: List[ClassInfo] = []
        seen = set()
        current: Optional[str] = class_name
        while current and current not in seen:
            info = self._classes.get(current)
            if info is None:
                break
            seen.add(current)
            found.append(info)
            current = info.super_name
        return tuple(found)

    def properties(self, class_name: str) -> Tuple[PropertyInfo, ...]:
        """All properties across the chain, ``rank`` order. A subclass that changes
        an inherited default (``QLineEdit`` is an I-beam) shows its own default."""
        cached = self._resolved.get(class_name)
        if cached is not None:
            return cached
        chain = self.chain(class_name)
        collected: List[PropertyInfo] = []
        taken = set()
        # A class that declares a property again (QDialog.modal, QDockWidget.windowTitle,
        # QGridLayout.spacing) owns its position: Designer writes it there.
        for info in chain:
            for item in self._properties.get(info.name, ()):
                if item.name not in taken:
                    taken.add(item.name)
                    collected.append(item)
        collected.sort(key=lambda item: (item.rank, item.name))
        if any(self._overrides.get(info.name) for info in chain):
            for index, item in enumerate(collected):
                for info in chain:
                    changed = self._overrides.get(info.name)
                    if changed is not None and item.name in changed:
                        collected[index] = replace(item, default=changed[item.name])
                        break
        result = tuple(collected)
        self._resolved[class_name] = result
        return result

    def property_info(self, class_name: str, name: str) -> Optional[PropertyInfo]:
        """O(1) after first lookup for the class."""
        key = (class_name, name)
        cached = self._by_name.get(key)
        if cached is not None or key in self._by_name:
            return cached
        found = None
        for item in self.properties(class_name):
            if item.name == name:
                found = item
                break
        self._by_name[key] = found
        return found

    def property_rank(self, class_name: str, name: str, *, dynamic: bool) -> Tuple[int, int, str]:
        """Sort key for inserting a new ``<property>`` entry: ``(group, rank, name)``.
        group 0 = known Qt property (rank from the table), 1 = other dynamic
        property, 2 = ``cbcs*`` logic property (rank from
        ``engine.logic.storage.LOGIC_PROPERTY_ORDER``). A name the table knows ranks as a
        Qt property even when the entry says ``stdset="0"``: Designer writes that
        for any property whose setter is not ``set<Name>`` (``isWrapping``). So
        ``dynamic`` only matters for names the table does not know, which sort in
        group 1 by name."""
        if name.startswith("cbcs"):
            # Imported here: the logic package imports this one.
            from app.features.form_builder.engine.logic.storage import LOGIC_PROPERTY_ORDER

            if name in LOGIC_PROPERTY_ORDER:
                return (2, LOGIC_PROPERTY_ORDER.index(name), name)
            # Other cbcs names keep the order they were written in (no name tie-break).
            return (2, len(LOGIC_PROPERTY_ORDER), "")
        info = self.property_info(class_name, name)
        if info is not None:
            return (0, info.rank, name)
        return (1, 0, name)

    def enum_info(self, qualified: str) -> Optional[EnumInfo]:
        """By enum type (``Qt::AlignmentFlag``) or flag type (``Qt::Alignment``)."""
        direct = self._enums.get(qualified)
        if direct is not None:
            return direct
        for info in self._enums.values():
            if info.flag_type == qualified:
                return info
        return None

    def signals(self, class_name: str) -> Tuple[str, ...]:
        """All signals across the chain, normalised signatures, chain order."""
        found: List[str] = []
        for info in reversed(self.chain(class_name)):
            found.extend(self._signals.get(info.name, ()))
        return tuple(found)

    def slots(self, class_name: str) -> Tuple[str, ...]:
        found: List[str] = []
        for info in reversed(self.chain(class_name)):
            found.extend(self._slots.get(info.name, ()))
        return tuple(found)

    def effective_class(self, class_name: str, extends_of: Optional[str] = None) -> str:
        """``class_name`` if known, else ``extends_of`` if known, else ``QWidget``."""
        if class_name in self._classes:
            return class_name
        if extends_of and extends_of in self._classes:
            return extends_of
        return "QWidget"


def _load() -> QtClassTable:
    path = Path(__file__).resolve().parent / DATA_FILE
    if not path.is_file():
        return QtClassTable("", {}, {}, {}, {}, {})
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_VERSION:
        raise ValueError("qt_classes.json format is not %s" % (FORMAT_VERSION,))
    classes_raw = payload.get("classes") or {}
    enums_raw = payload.get("enums") or {}
    classes: Dict[str, ClassInfo] = {}
    properties: Dict[str, Tuple[PropertyInfo, ...]] = {}
    signals: Dict[str, Tuple[str, ...]] = {}
    slots: Dict[str, Tuple[str, ...]] = {}
    supers: Dict[str, Optional[str]] = {}
    overrides: Dict[str, Dict[str, Optional[Value]]] = {}
    for name, body in classes_raw.items():
        if not isinstance(name, str) or not isinstance(body, dict):
            continue
        super_name = body.get("super")
        if not isinstance(super_name, str) or super_name == "":
            super_name = None
        flags = tuple(item for item in body.get("flags") or () if isinstance(item, str))
        default_signal = body.get("default_signal")
        if not isinstance(default_signal, str):
            default_signal = None
        module = body.get("module")
        info = ClassInfo(
            name=name,
            super_name=super_name,
            module=module if isinstance(module, str) else "",
            flags=flags,
            default_signal=default_signal,
        )
        classes[name] = info
        supers[name] = super_name
        own: List[PropertyInfo] = []
        for index, prop in enumerate(body.get("properties") or ()):
            if not isinstance(prop, dict) or not isinstance(prop.get("name"), str):
                continue
            default_raw = prop.get("default")
            default = value_from_json(default_raw) if isinstance(default_raw, dict) else None
            enum_name = prop.get("enum")
            own.append(
                PropertyInfo(
                    name=prop["name"],
                    kind=prop.get("kind") if isinstance(prop.get("kind"), str) else "",
                    default=default,
                    designable=bool(prop.get("designable")),
                    stored=bool(prop.get("stored", True)),
                    volatile=bool(prop.get("volatile")),
                    enum=enum_name if isinstance(enum_name, str) else None,
                    rank=index,
                    declared_by=name,
                )
            )
        properties[name] = tuple(own)
        changed = body.get("defaults")
        if isinstance(changed, dict) and changed:
            overrides[name] = {
                key: value_from_json(item) if isinstance(item, dict) else None
                for key, item in changed.items()
                if isinstance(key, str)
            }
        signals[name] = tuple(item for item in body.get("signals") or () if isinstance(item, str))
        slots[name] = tuple(item for item in body.get("slots") or () if isinstance(item, str))
    # ``rank`` counts across the chain: every property of the super classes
    # comes before the class's own, as in Designer's property sheet.
    offsets: Dict[str, int] = {}

    def offset_of(class_name: str) -> int:
        known = offsets.get(class_name)
        if known is not None:
            return known
        offsets[class_name] = 0
        parent = supers.get(class_name)
        total = 0
        if isinstance(parent, str) and parent in properties:
            total = offset_of(parent) + len(properties[parent])
        offsets[class_name] = total
        return total

    for name in list(properties):
        base = offset_of(name)
        if base:
            properties[name] = tuple(replace(item, rank=item.rank + base) for item in properties[name])
    for name, info in classes.items():
        chain = [name]
        current = supers.get(name)
        seen = {name}
        while isinstance(current, str) and current not in seen:
            seen.add(current)
            chain.append(current)
            current = supers.get(current)
        _ANCESTORS[id(info)] = tuple(chain)
    enums: Dict[str, EnumInfo] = {}
    for name, body in enums_raw.items():
        if not isinstance(name, str) or not isinstance(body, dict):
            continue
        keys = []
        for pair in body.get("keys") or ():
            if isinstance(pair, (list, tuple)) and len(pair) == 2 and isinstance(pair[0], str) and isinstance(pair[1], int):
                keys.append((pair[0], pair[1]))
        flag_type = body.get("flag_type")
        enums[name] = EnumInfo(
            name=name,
            is_flag=bool(body.get("is_flag")),
            flag_type=flag_type if isinstance(flag_type, str) else None,
            keys=tuple(keys),
        )
    version = payload.get("qt_version")
    return QtClassTable(
        version if isinstance(version, str) else "",
        classes,
        properties,
        signals,
        slots,
        enums,
        overrides,
    )
