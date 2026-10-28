"""Cursor drop-down (UX-PED-086).

Registered as an override. ``choices.py`` keeps its baseline editor. A legacy
integer ``cursor`` is shown and left untouched until the person picks a shape,
which writes ``cursorShape``.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.ui4.values import CursorShapeValue, CursorValue
from app.features.form_builder.qtside.inspector.api import (
    MIXED_TEXT,
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    Written,
    mark,
)
from app.features.form_builder.qtside.visual.common import part_name
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QComboBox, QWidget
from app.qt.qt_compat import enum_value

# Friendly label, Qt cursor-shape name. Tooltips show the Qt name.
_SHAPES = (
    ("Arrow", "ArrowCursor"),
    ("Pointing hand", "PointingHandCursor"),
    ("Text (I-beam)", "IBeamCursor"),
    ("Wait", "WaitCursor"),
    ("Busy (arrow and wait)", "BusyCursor"),
    ("Cross", "CrossCursor"),
    ("Up arrow", "UpArrowCursor"),
    ("Resize left\u2013right", "SizeHorCursor"),
    ("Resize up\u2013down", "SizeVerCursor"),
    ("Resize diagonal \u27cb", "SizeFDiagCursor"),
    ("Resize diagonal \u27cd", "SizeBDiagCursor"),
    ("Move", "SizeAllCursor"),
    ("Split horizontal", "SplitHCursor"),
    ("Split vertical", "SplitVCursor"),
    ("Not allowed", "ForbiddenCursor"),
    ("What's this", "WhatsThisCursor"),
    ("Open hand", "OpenHandCursor"),
    ("Closed hand", "ClosedHandCursor"),
    ("Drag copy", "DragCopyCursor"),
    ("Drag move", "DragMoveCursor"),
    ("Drag link", "DragLinkCursor"),
    ("Blank", "BlankCursor"),
)


def _tooltip_role() -> object:
    return getattr(getattr(Qt, "ItemDataRole", Qt), "ToolTipRole")


def _shape_value(qt_name: str) -> Optional[int]:
    owner = getattr(Qt, "CursorShape", Qt)
    shape = getattr(owner, qt_name, None)
    if shape is None:
        return None
    try:
        return int(enum_value(shape))
    except (TypeError, ValueError):
        return None


def friendly_for(value: object) -> str:
    if isinstance(value, CursorShapeValue):
        for label, qt_name in _SHAPES:
            if qt_name == value.name:
                return label
        return value.name
    if isinstance(value, CursorValue):
        for label, qt_name in _SHAPES:
            if _shape_value(qt_name) == value.value:
                return label
        return str(value.value)
    return ""


class CursorEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._combo = QComboBox(parent)
        self._combo.setObjectName("formBuilder.cursorShape")
        self._combo.setAccessibleName(part_name(host.label or "Cursor", "shape"))
        role = _tooltip_role()
        for label, qt_name in _SHAPES:
            self._combo.addItem(label, qt_name)
            self._combo.setItemData(self._combo.count() - 1, qt_name, role)
        self._combo.activated.connect(self._commit)
        self._stored: object = None

    @property
    def widget(self) -> QWidget:
        return self._combo

    def show(self, value: RowValue) -> None:
        mark(self._combo, value)
        self._stored = value.value if isinstance(value, Written) else None
        self._combo.blockSignals(True)
        if isinstance(value, Mixed):
            if self._combo.itemText(0) != MIXED_TEXT:
                self._combo.insertItem(0, MIXED_TEXT, "")
            self._combo.setCurrentIndex(0)
        else:
            if self._combo.itemText(0) == MIXED_TEXT:
                self._combo.removeItem(0)
            if not isinstance(value, Written):
                self._combo.setCurrentIndex(-1)
            else:
                label = friendly_for(self._stored)
                index = self._combo.findText(label)
                self._combo.setCurrentIndex(index if index >= 0 else 0)
        self._combo.blockSignals(False)

    def _commit(self, index: int) -> None:
        if index < 0:
            return
        qt_name = self._combo.itemData(index)
        if not isinstance(qt_name, str) or not qt_name:
            return
        if isinstance(self._stored, CursorShapeValue) and self._stored.name == qt_name:
            return
        self._host.commit(CursorShapeValue(qt_name))


def shapes() -> Tuple[Tuple[str, str], ...]:
    return _SHAPES


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(CursorShapeValue.ELEMENT), CursorEditor, baseline=False)
    registrar.editor(EditorKey(CursorValue.ELEMENT), CursorEditor, baseline=False)
