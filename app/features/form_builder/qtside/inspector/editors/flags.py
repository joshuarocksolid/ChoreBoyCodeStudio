"""Flag sets: a summary button and a popover of checks. One visit is one step."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ui4.values import SetValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    EnumSpec,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import change_label, name_part, payload
from app.features.form_builder.qtside.inspector.editors._enum_words import (
    dock_area_summary,
    friendly,
    radio_groups,
)
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.qt.qt_compat import enum_value
from app.qt.QtCore import QTimer, Qt
from app.qt.QtWidgets import QButtonGroup, QCheckBox, QRadioButton, QWidget

_Check = Tuple[str, QWidget]


class _FlagCheck(QCheckBox):
    """Enter keeps the popover. Space still toggles the box."""

    def __init__(self, text: str, parent: QWidget, on_enter) -> None:  # type: ignore[no-untyped-def]
        super().__init__(text, parent)
        self._on_enter = on_enter

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        keys = getattr(Qt, "Key", Qt)
        if key in (getattr(keys, "Key_Return"), getattr(keys, "Key_Enter")):
            self._on_enter()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class FlagsEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._button = SummaryButton(host.label or "Flags", parent)
        self._button.set_opener(self._open)
        self._popover: Optional[RowPopover] = None
        self._checks: List[_Check] = []
        self._groups: Dict[str, Tuple[str, ...]] = {}
        self._resetting = False
        self._can_reset = False
        self._chosen: Tuple[str, ...] = ()

    @property
    def widget(self) -> QWidget:
        return self._button

    def show(self, value: RowValue) -> None:
        mark(self._button, value)
        self._button.set_row_label(self._host.label or "Flags")
        self._can_reset = isinstance(value, Written) or (isinstance(value, Unset) and value.default is not None)
        mark(self._button, value)
        if isinstance(value, Mixed):
            self._chosen = ()
            self._button.set_summary("Mixed")
            return
        self._chosen = _tails(value)
        self._button.set_summary(_summary(self._spec, self._host, self._chosen))

    def _open(self) -> None:
        enum = self._spec.enum
        if enum is None or (self._popover is not None and not self._popover.closed):
            return
        popover = RowPopover(
            self._host.row_widget,
            self._host,
            row_label=self._host.label or "Flags",
            session_label=change_label(self._host.label),
            qt_name=self._host.qt_name,
            anchor=self._button,
        )
        self._popover = popover
        self._checks = []
        self._groups = {}
        chosen = set(self._chosen)
        visible = _single_bits(enum)
        values = _bit_values(enum)
        mask = 0
        for name in chosen:
            mask |= values.get(name, 0)
        groups = radio_groups(enum.type_name, visible)
        grouped = {name for group in groups for name in group}
        body = popover.body()
        for index, group in enumerate(groups):
            buttons = QButtonGroup(popover)
            buttons.setExclusive(True)
            none = QRadioButton("None", popover)
            none.setChecked(not any(_bit_on(name, chosen, values, mask) for name in group))
            name_part(none, self._host, "none")
            none.clicked.connect(lambda _checked=False, group=group: self._radio(group, ""))
            buttons.addButton(none)
            body.addWidget(none)
            for name in group:
                button = QRadioButton(friendly(enum.type_name, self._host.qt_name, name), popover)
                button.setChecked(_bit_on(name, chosen, values, mask))
                button.setToolTip(name)
                name_part(button, self._host, friendly(enum.type_name, self._host.qt_name, name))
                button.clicked.connect(lambda _checked=False, group=group, name=name: self._radio(group, name))
                buttons.addButton(button)
                body.addWidget(button)
                self._checks.append((name, button))
            self._groups["g%d" % index] = group
        for name in visible:
            if name in grouped:
                continue
            box = _FlagCheck(
                friendly(enum.type_name, self._host.qt_name, name),
                popover,
                popover.done,
            )
            box.setChecked(_bit_on(name, chosen, values, mask))
            box.setToolTip(name)
            name_part(box, self._host, friendly(enum.type_name, self._host.qt_name, name))
            box.toggled.connect(lambda checked, picked=name: self._mark(picked, bool(checked)))
            body.addWidget(box)
            self._checks.append((name, box))
        if self._can_reset:
            popover.set_reset(self._reset)
        popover.open_popover()

    def _single_chosen(self) -> List[str]:
        """The chosen names, with a combined or zero name split into the bits it sets.

        The popover lists single bits only, so a tick or untick after
        ``TextEditorInteraction`` must act on its bits, not on the combined name.
        """
        enum = self._spec.enum
        if enum is None:
            return list(self._chosen)
        values = _bit_values(enum)
        visible = _single_bits(enum)
        mask = 0
        for name in self._chosen:
            mask |= values.get(name, 0)
        out: List[str] = []
        for name in self._chosen:
            value = values.get(name)
            if value is None or (value > 0 and not value & (value - 1)):
                if name not in out:
                    out.append(name)
        for name in visible:
            bit = values.get(name, 0)
            if bit and (mask & bit) == bit and name not in out:
                out.append(name)
        return out

    def _mark(self, name: str, checked: bool) -> None:
        chosen = [item for item in self._single_chosen() if item != name]
        if checked:
            chosen.append(name)
        self._chosen = tuple(chosen)
        QTimer.singleShot(0, self._write)

    def _radio(self, group: Sequence[str], picked: str) -> None:
        chosen = [item for item in self._single_chosen() if item not in group]
        if picked:
            chosen.append(picked)
        self._chosen = tuple(chosen)
        QTimer.singleShot(0, self._write)

    def _write(self) -> None:
        if self._resetting or self._popover is None or self._popover.closed or self._spec.enum is None:
            return
        self._host.commit(
            self._host.enum_value(self._spec.enum, self._chosen),
            session=self._popover.session,
        )
        self._button.set_summary(_summary(self._spec, self._host, self._chosen))

    def _reset(self) -> None:
        self._resetting = True
        popover = self._popover
        if popover is not None and popover.session.has_step():
            popover.session.revert()
        self._host.reset()
        self._resetting = False


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(SetValue.ELEMENT), FlagsEditor)


def _bit_values(enum: EnumSpec) -> Dict[str, int]:
    containers = []
    for key in (enum.type_name, enum.scope):
        found = getattr(Qt, key, None)
        if found is not None and found not in containers:
            containers.append(found)
    values: Dict[str, int] = {}
    for name in enum.names:
        for container in containers:
            item = getattr(container, name, None)
            if item is None:
                continue
            try:
                values[name] = int(enum_value(item))
            except (TypeError, ValueError):
                continue
            break
    return values


def _single_bits(enum: EnumSpec) -> Tuple[str, ...]:
    """Zero and combined enumerators stay out of the list. A written combined name still reads."""
    values = _bit_values(enum)
    if not values:
        return tuple(enum.names)
    shown = []
    for name in enum.names:
        value = values.get(name)
        if value is None or value <= 0 or value & (value - 1):
            continue
        shown.append(name)
    return tuple(shown)


def _bit_on(name: str, chosen: set, values: Dict[str, int], mask: int) -> bool:
    bit = values.get(name, 0)
    if bit and (mask & bit) == bit:
        return True
    return name in chosen


def _tails(value: RowValue) -> Tuple[str, ...]:
    found = payload(value)
    if not isinstance(found, SetValue):
        return ()
    tails = []
    for piece in found.text.split("|"):
        name = piece.strip().split("::")[-1]
        if name and name != "0":
            tails.append(name)
    return tuple(tails)


def _summary(spec: ValueSpec, host: EditorHost, names: Sequence[str]) -> str:
    enum = spec.enum
    if enum is None or not names:
        return "None"
    if enum.type_name == "DockWidgetArea":
        return dock_area_summary(names)
    type_name = enum.type_name
    return ", ".join(friendly(type_name, host.qt_name, name) for name in names)
