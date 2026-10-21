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

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.ui4.values import Value

DATA_FILE = "data/qt_classes.json"
FORMAT_VERSION = 1


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
        ...

    def value_of(self, key: str) -> Optional[int]:
        ...


@dataclass(frozen=True)
class ClassInfo:
    name: str
    super_name: Optional[str]
    module: str
    flags: Tuple[str, ...]
    default_signal: Optional[str]

    def is_a(self, base: str) -> bool:
        """True when ``base`` is this class or an ancestor."""
        ...


class QtClassTable:
    """Read-only, process-wide, loaded lazily on first use (budget: 25 ms CPU,
    once per process). Thread-safe for reads."""

    @classmethod
    def shared(cls) -> "QtClassTable":
        ...

    @property
    def qt_version(self) -> str:
        ...

    def class_info(self, class_name: str) -> Optional[ClassInfo]:
        """None for unknown classes. Custom widgets resolve through their
        ``extends`` (callers use ``effective_class``)."""
        ...

    def chain(self, class_name: str) -> Tuple[ClassInfo, ...]:
        """Leaf first, QObject last."""
        ...

    def properties(self, class_name: str) -> Tuple[PropertyInfo, ...]:
        """All properties across the chain, ``rank`` order."""
        ...

    def property_info(self, class_name: str, name: str) -> Optional[PropertyInfo]:
        """O(1) after first lookup for the class."""
        ...

    def property_rank(self, class_name: str, name: str, *, dynamic: bool) -> Tuple[int, int, str]:
        """Sort key for inserting a new ``<property>`` entry: ``(group, rank, name)``.
        group 0 = known Qt property (rank from the table), 1 = other dynamic
        property, 2 = ``cbcs*`` logic property (rank from
        ``engine.logic.storage.LOGIC_PROPERTY_ORDER``). Unknown non-dynamic names
        sort in group 1 by name."""
        ...

    def enum_info(self, qualified: str) -> Optional[EnumInfo]:
        """By enum type (``Qt::AlignmentFlag``) or flag type (``Qt::Alignment``)."""
        ...

    def signals(self, class_name: str) -> Tuple[str, ...]:
        """All signals across the chain, normalised signatures, chain order."""
        ...

    def slots(self, class_name: str) -> Tuple[str, ...]:
        ...

    def effective_class(self, class_name: str, extends_of: "Optional[str]" = None) -> str:
        """``class_name`` if known, else ``extends_of`` if known, else ``QWidget``."""
        ...
