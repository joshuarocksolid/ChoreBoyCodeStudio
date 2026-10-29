"""The form inspector's settings groups: Code, Translation and Free placement (UX-FSET-001 ... 006).

They are added through the form-group slot and show while the form is
selected. Each row edits one field of the ``<ui>`` element through
``SetFormSetting`` or ``SetFormGrid``; each change is one undo step named
"Change form setting: {label in lower case}", and a row's reset removes the
field. A row whose field is in the file shows the changed bar and Reset, as
every inspector row does (UX-INSP-006).

The slot has no "collapsed" flag yet, so each body collapses its group the
first time it is built and refreshes itself when the group is opened.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.form_fields import (
    CHANGE_PREFIX,
    GRID_STEP_DEFAULT,
    GRID_STEP_MAX,
    GRID_STEP_MIN,
    LEGACY_FIELDS,
    NAME_REFUSAL,
    REMOVE_LEGACY,
    SetFormGrid,
    SetFormSetting,
    form_grid,
    function_name_ok,
    grid_is_default,
    has_free_container,
    include_lines,
    lower_label,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.schema import LayoutDefault, LayoutFunction
from app.features.form_builder.qtside.inspector.api import GroupBody, GroupHost, Registrar, set_style_flag
from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

CODE = "code"
TRANSLATION = "translation"
FREE = "freePlacement"

CAPTION_GAPS = "Used by layouts that don't set their own."
CAPTION_FUNCTIONS = "Python code calls these functions for gaps and margins instead of numbers."
CAPTION_INCLUDES = "Used by C++ code. Python ignores these lines; they are kept for Qt Designer."
CAPTION_KEPT_CODE = "Kept for Qt Designer and C++ code."
CAPTION_KEPT = "Kept for Qt Designer."
CAPTION_IDS = "Each text uses its translation ID instead of the English text."
CAPTION_LEGACY = "Kept as is. Newer forms don't use it."
CAPTION_FREE = "Only for containers without a layout. Alt+arrows move by one step."
STEP_REFUSAL = "Use a step from %d to %d pixels." % (GRID_STEP_MIN, GRID_STEP_MAX)

#: What a new "Default gaps" writes: a gap and a margin of 8 pixels, the builder's own grid.
DEFAULT_GAP = 8
DEFAULT_MARGIN = 8

_LABEL_W = 90


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


class _Guard(QObject):
    """Keeps the wheel for scrolling the inspector unless the control has focus."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel and isinstance(watched, QWidget) and not watched.hasFocus():
            event.ignore()
            return True
        return False


class _Edit(QLineEdit):
    """A line edit where Esc puts the stored text back."""

    def __init__(self, parent: QWidget, on_revert: Callable[[], None]) -> None:
        super().__init__(parent)
        self._on_revert = on_revert

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == _key("Key_Escape") and self.isModified():
            self._on_revert()
            event.accept()
            return
        super().keyPressEvent(event)


class _Button(QPushButton):
    """A push button that Enter presses as well as Space (UX-FSET-004: Tab to [Remove], Enter)."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (_key("Key_Return"), _key("Key_Enter")):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class SettingRow(QWidget):
    """The shell of one row: bar, label, editor slot, Reset and a caption line."""

    def __init__(self, body: "_Body", key: str, label: str, caption: str = "", *, stacked: bool = False) -> None:
        super().__init__(body.root)
        self.body = body
        self.key = key
        self.label_text = label
        self.setObjectName("formBuilder.formSetting.%s" % key)
        self._changed = False
        self._guard = _Guard(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(2)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self._bar = QFrame(self)
        self._bar.setObjectName("formBuilder.rowChanged")
        self._bar.setFixedWidth(2)
        self._bar.setMinimumHeight(18)
        line.addWidget(self._bar, 0)
        self._label = QLabel(label, self)
        self._label.setWordWrap(True)
        if stacked:
            # A wide editor (the include lines) gets the full row, under its label (UX-PED-002).
            line.addWidget(self._label, 1, Qt.AlignmentFlag.AlignTop)
        else:
            self._label.setFixedWidth(_LABEL_W)
            line.addWidget(self._label, 0, Qt.AlignmentFlag.AlignTop)
        self.slot = QWidget(self)
        self.slot_layout = QVBoxLayout(self.slot)
        self.slot_layout.setContentsMargins(0, 0, 0, 0)
        self.slot_layout.setSpacing(2)
        if not stacked:
            line.addWidget(self.slot, 1)
        self._reset = QToolButton(self)
        self._reset.setObjectName("formBuilder.rowReset")
        self._reset.setProperty("fbFlat", "true")
        self._reset.setText("↺")
        self._reset.setFixedSize(16, 16)
        self._reset.setAccessibleName("Reset %s" % label)
        self._reset.setToolTip("Reset: remove this setting from the file")
        self._reset.clicked.connect(self._reset_clicked)
        self._reset.hide()
        line.addWidget(self._reset, 0, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(line)
        if stacked:
            outer.addWidget(self.slot)
        self._note = QLabel(caption, self)
        self._note.setObjectName("formBuilder.rowNote")
        self._note.setWordWrap(True)
        self._note.setContentsMargins(8, 0, 0, 0)
        self._note.setVisible(bool(caption))
        outer.addWidget(self._note)
        self._caption = caption
        self._error = ""

    # -- helpers for subclasses ------------------------------------------------
    def guard(self, widget: QWidget) -> QWidget:
        widget.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        widget.installEventFilter(self._guard)
        return widget

    def add(self, widget: QWidget) -> None:
        self.slot_layout.addWidget(widget)

    def set_changed(self, changed: bool) -> None:
        self._changed = changed
        flag = "true" if changed else "false"
        set_style_flag(self._bar, "fbChanged", flag)
        set_style_flag(self._label, "fbChanged", flag)
        self._reset.setVisible(changed)

    @property
    def changed(self) -> bool:
        return self._changed

    def show_error(self, text: str) -> None:
        self._error = text
        if text:
            self._note.setObjectName("formBuilder.rowError")
            self._note.setText(text)
            self._note.show()
        else:
            self._note.setObjectName("formBuilder.rowNote")
            self._note.setText(self._caption)
            self._note.setVisible(bool(self._caption))
        style = self._note.style()
        style.unpolish(self._note)
        style.polish(self._note)

    @property
    def error(self) -> str:
        return self._error

    def write(self, *commands: object) -> bool:
        """Run ``commands`` as one step named for this row. Shows a refusal under the row."""
        refusal = self.body.host.run(CHANGE_PREFIX + lower_label(self.label_text), commands)  # type: ignore[arg-type]
        self.show_error(refusal or "")
        return refusal is None

    def _reset_clicked(self) -> None:
        refusal = self.body.host.run("Reset %s" % self.label_text, self.reset_commands())
        self.show_error(refusal or "")

    # -- to override -----------------------------------------------------------
    def reset_commands(self) -> list:
        return []

    def load(self, doc: UiDocument) -> None:
        raise NotImplementedError

    def first_focus(self) -> Optional[QWidget]:
        return None


class _TextRow(SettingRow):
    """A text field (``author``, ``exportmacro``, ``comment`` ...). ``named`` checks a Python name."""

    def __init__(self, body: "_Body", field: str, label: str, caption: str = "", *, named: bool = False) -> None:
        super().__init__(body, field, label, caption)
        self.field = field
        self._named = named
        self.edit = _Edit(self, self._revert)
        self.edit.setObjectName("formBuilder.formSetting.%s.edit" % field)
        self.edit.setAccessibleName("Form setting: %s" % label)
        self.edit.editingFinished.connect(self._finished)
        self.edit.textEdited.connect(lambda _text: self.show_error(""))
        self.add(self.edit)
        self._stored = ""

    def load(self, doc: UiDocument) -> None:
        value = doc.ui.field(self.field)
        self._stored = value if isinstance(value, str) else ""
        self.set_changed(isinstance(value, str) and value != "")
        if not (self.edit.hasFocus() and self.edit.isModified()):
            self.edit.setText(self._stored)
            self.edit.setModified(False)

    def first_focus(self) -> Optional[QWidget]:
        return self.edit

    def reset_commands(self) -> list:
        return [SetFormSetting(self.field, None, "Reset %s" % self.label_text)]

    def _revert(self) -> None:
        self.edit.setText(self._stored)
        self.edit.setModified(False)
        self.show_error("")

    def _finished(self) -> None:
        text = self.edit.text()
        if text == self._stored:
            self.edit.setModified(False)
            return
        if self._named and text.strip() and not function_name_ok(text.strip()):
            self.show_error(NAME_REFUSAL)
            return
        if self.write(SetFormSetting(self.field, text.strip() if self._named else text)):
            self.edit.setModified(False)


class _CheckRow(SettingRow):
    """A yes or no field stored as ``"true"`` (and removed when off)."""

    def __init__(self, body: "_Body", field: str, label: str, caption: str = "") -> None:
        super().__init__(body, field, label, caption)
        self.field = field
        self.box = self.guard(QCheckBox(self))  # type: ignore[assignment]
        self.box.setObjectName("formBuilder.formSetting.%s.check" % field)
        self.box.setAccessibleName("Form setting: %s" % label)
        self.box.toggled.connect(self._toggled)
        self.add(self.box)

    def load(self, doc: UiDocument) -> None:
        value = doc.ui.field(self.field)
        self.set_changed(value is not None)
        self.box.blockSignals(True)
        self.box.setChecked(value == "true")
        self.box.blockSignals(False)

    def first_focus(self) -> Optional[QWidget]:
        return self.box

    def reset_commands(self) -> list:
        return [SetFormSetting(self.field, None, "Reset %s" % self.label_text)]

    def _toggled(self, on: bool) -> None:
        if not self.write(SetFormSetting(self.field, "true" if on else None)):
            self.load(self.body.host.document)


class _GapsRow(SettingRow):
    """"Default gaps": a check box and the gap and margin numbers (``layoutdefault``)."""

    def __init__(self, body: "_Body") -> None:
        super().__init__(body, "layoutdefault", "Default gaps", CAPTION_GAPS)
        self.box = self.guard(QCheckBox(self))  # type: ignore[assignment]
        self.box.setObjectName("formBuilder.formSetting.layoutdefault.check")
        self.box.setAccessibleName("Form setting: Default gaps")
        self.box.toggled.connect(self._toggled)
        self.add(self.box)
        grid = QWidget(self)
        cells = QGridLayout(grid)
        cells.setContentsMargins(0, 0, 0, 0)
        cells.setHorizontalSpacing(6)
        cells.setVerticalSpacing(2)
        self.gap = self._spin("Gap")
        self.margin = self._spin("Margin")
        for row, (name, spin) in enumerate((("Gap", self.gap), ("Margin", self.margin))):
            cells.addWidget(QLabel(name, grid), row, 0)
            cells.addWidget(spin, row, 1)
        cells.setColumnStretch(1, 1)
        self.numbers = grid
        self.add(grid)

    def _spin(self, name: str) -> QSpinBox:
        spin = self.guard(QSpinBox(self))  # type: ignore[assignment]
        spin.setObjectName("formBuilder.formSetting.layoutdefault.%s" % name.lower())
        spin.setAccessibleName("Form setting: Default gaps, %s" % name.lower())
        spin.setRange(-1, 999)
        spin.setSpecialValueText("—")
        spin.setSuffix(" px")
        spin.editingFinished.connect(self._numbers_done)
        return spin  # type: ignore[return-value]

    def load(self, doc: UiDocument) -> None:
        value = doc.ui.field("layoutdefault")
        on = isinstance(value, LayoutDefault)
        self._stored = value if on else None
        self.set_changed(on)
        self.box.blockSignals(True)
        self.box.setChecked(on)
        self.box.blockSignals(False)
        self.numbers.setEnabled(on)
        for spin, number in ((self.gap, value.spacing if on else None), (self.margin, value.margin if on else None)):  # type: ignore[union-attr]
            if not spin.hasFocus():
                spin.blockSignals(True)
                spin.setValue(-1 if number is None else number)
                spin.blockSignals(False)

    def first_focus(self) -> Optional[QWidget]:
        return self.box

    def reset_commands(self) -> list:
        return [SetFormSetting("layoutdefault", None, "Reset Default gaps")]

    def _toggled(self, on: bool) -> None:
        value = LayoutDefault(DEFAULT_GAP, DEFAULT_MARGIN) if on else None
        if not self.write(SetFormSetting("layoutdefault", value)):
            self.load(self.body.host.document)

    def _numbers_done(self) -> None:
        spacing = self.gap.value()
        margin = self.margin.value()
        value = LayoutDefault(None if spacing < 0 else spacing, None if margin < 0 else margin)
        if value == self._stored:
            return
        if not self.write(SetFormSetting("layoutdefault", value)):
            self.load(self.body.host.document)


class _FunctionsRow(SettingRow):
    """"Gap functions": a check box and two function names (``layoutfunction``)."""

    def __init__(self, body: "_Body") -> None:
        super().__init__(body, "layoutfunction", "Gap functions", CAPTION_FUNCTIONS)
        self._armed = False
        self.box = self.guard(QCheckBox(self))  # type: ignore[assignment]
        self.box.setObjectName("formBuilder.formSetting.layoutfunction.check")
        self.box.setAccessibleName("Form setting: Gap functions")
        self.box.toggled.connect(self._toggled)
        self.add(self.box)
        grid = QWidget(self)
        cells = QGridLayout(grid)
        cells.setContentsMargins(0, 0, 0, 0)
        cells.setHorizontalSpacing(6)
        cells.setVerticalSpacing(2)
        self._stored: Optional[LayoutFunction] = None
        self.gap = self._edit("Gap")
        self.margin = self._edit("Margin")
        for row, (name, edit) in enumerate((("Gap", self.gap), ("Margin", self.margin))):
            cells.addWidget(QLabel(name, grid), row, 0)
            cells.addWidget(edit, row, 1)
        cells.setColumnStretch(1, 1)
        self.names = grid
        self.add(grid)

    def _edit(self, name: str) -> QLineEdit:
        edit = _Edit(self, self._revert)
        edit.setObjectName("formBuilder.formSetting.layoutfunction.%s" % name.lower())
        edit.setAccessibleName("Form setting: Gap functions, %s function" % name.lower())
        edit.setPlaceholderText("%s_for" % name.lower())
        edit.editingFinished.connect(self._done)
        edit.textEdited.connect(lambda _text: self.show_error(""))
        return edit

    def load(self, doc: UiDocument) -> None:
        value = doc.ui.field("layoutfunction")
        stored = value if isinstance(value, LayoutFunction) else None
        self._stored = stored
        on = stored is not None or self._armed
        self.set_changed(stored is not None)
        self.box.blockSignals(True)
        self.box.setChecked(on)
        self.box.blockSignals(False)
        self.names.setEnabled(on)
        for edit, text in ((self.gap, stored.spacing if stored else ""), (self.margin, stored.margin if stored else "")):
            if not (edit.hasFocus() and edit.isModified()):
                edit.setText(text or "")
                edit.setModified(False)

    def first_focus(self) -> Optional[QWidget]:
        return self.box

    def reset_commands(self) -> list:
        self._armed = False
        return [SetFormSetting("layoutfunction", None, "Reset Gap functions")]

    def _revert(self) -> None:
        self.show_error("")
        self.load(self.body.host.document)

    def _toggled(self, on: bool) -> None:
        # With no names yet there is nothing to write: the check box only opens the fields.
        self._armed = on
        if not on and self._stored is not None:
            if not self.write(SetFormSetting("layoutfunction", None)):
                self._armed = True
        self.load(self.body.host.document)
        if on:
            self.gap.setFocus()

    def _done(self) -> None:
        gap = self.gap.text().strip()
        margin = self.margin.text().strip()
        stored = self._stored or LayoutFunction()
        if (gap or None) == stored.spacing and (margin or None) == stored.margin:
            return
        for name in (gap, margin):
            if name and not function_name_ok(name):
                self.show_error(NAME_REFUSAL)
                return
        value = LayoutFunction(gap or None, margin or None)
        if self.write(SetFormSetting("layoutfunction", value)):
            self.gap.setModified(False)
            self.margin.setModified(False)


class _IncludesRow(SettingRow):
    """"Extra includes": one line each with Local or Global and a name (``includes``)."""

    def __init__(self, body: "_Body") -> None:
        super().__init__(body, "includes", "Extra includes", CAPTION_INCLUDES, stacked=True)
        self._lines: Tuple[Tuple[str, str], ...] = ()
        self.column = QWidget(self)
        self.column_layout = QVBoxLayout(self.column)
        self.column_layout.setContentsMargins(0, 0, 0, 0)
        self.column_layout.setSpacing(2)
        self.add(self.column)
        self.add_button = _Button("Add include", self)
        self.add_button.setObjectName("formBuilder.formSetting.includes.add")
        self.add_button.setAccessibleName("Form setting: Extra includes, add a line")
        self.add_button.clicked.connect(lambda _checked=False: self.add_line())
        self.add(self.add_button)
        self._widgets: List[QWidget] = []

    def load(self, doc: UiDocument, force: bool = False) -> None:
        lines = include_lines(doc)
        self.set_changed(bool(lines))
        if not force:
            if lines == self._lines and len(self._widgets) == len(lines):
                return
            typing = any(child.hasFocus() for child in self.column.findChildren(QLineEdit))
            if typing and len(self._widgets) >= len(lines):
                return
        self._lines = lines
        for widget in self._widgets:
            self.column_layout.removeWidget(widget)
            # A field that loses focus as it goes must not report a second edit.
            for field in widget.findChildren(QLineEdit):
                field.blockSignals(True)
            widget.setParent(None)  # type: ignore[call-overload]
            widget.deleteLater()
        self._widgets = []
        for index, (location, text) in enumerate(lines):
            line = self._line(index, location, text)
            self.column_layout.addWidget(line)
            self._widgets.append(line)

    def first_focus(self) -> Optional[QWidget]:
        return self.add_button

    def reset_commands(self) -> list:
        return [SetFormSetting("includes", (), "Reset Extra includes")]

    def _line(self, index: int, location: str, text: str) -> QWidget:
        row = QWidget(self.column)
        row.setObjectName("formBuilder.formSetting.includes.line%d" % index)
        box = QHBoxLayout(row)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        combo = self.guard(QComboBox(row))
        combo.setObjectName("formBuilder.formSetting.includes.where%d" % index)
        combo.setAccessibleName("Form setting: Extra includes, line %d, place" % (index + 1))
        combo.addItem("Local", "local")
        combo.addItem("Global", "global")
        combo.setCurrentIndex(0 if location == "local" else 1)
        combo.activated.connect(lambda _i, at=index, c=combo: self._place(at, c))  # type: ignore[attr-defined]
        box.addWidget(combo, 0)
        edit = _Edit(row, self._reload)
        edit.setObjectName("formBuilder.formSetting.includes.name%d" % index)
        edit.setAccessibleName("Form setting: Extra includes, line %d" % (index + 1))
        edit.setText(text)
        edit.editingFinished.connect(lambda at=index, e=edit: self._renamed(at, e))
        box.addWidget(edit, 1)
        drop = QToolButton(row)
        drop.setObjectName("formBuilder.formSetting.includes.delete%d" % index)
        drop.setProperty("fbFlat", "true")
        drop.setText("×")
        drop.setAccessibleName("Delete include line %d" % (index + 1))
        drop.clicked.connect(lambda _checked=False, at=index: self._delete(at))
        box.addWidget(drop, 0)
        return row

    def _reload(self) -> None:
        self.load(self.body.host.document, force=True)

    def _store(self, lines: Tuple[Tuple[str, str], ...]) -> bool:
        ok = self.write(SetFormSetting("includes", lines))
        self._reload()
        return ok

    def _place(self, index: int, combo: QComboBox) -> None:
        lines = list(self._lines)
        if index < len(lines):
            lines[index] = (str(combo.currentData()), lines[index][1])
            self._store(tuple(lines))

    def _renamed(self, index: int, edit: QLineEdit) -> None:
        lines = list(self._lines)
        if index >= len(lines) or edit.text().strip() == lines[index][1]:
            return
        if not edit.text().strip():
            del lines[index]
        else:
            lines[index] = (lines[index][0], edit.text().strip())
        self._store(tuple(lines))

    def _delete(self, index: int) -> None:
        lines = list(self._lines)
        if index < len(lines):
            del lines[index]
            self._store(tuple(lines))

    def add_line(self, location: str = "local", text: str = "") -> None:
        """Add a line. An empty name is not stored, so the new line waits for its name."""
        if text.strip():
            self._store(self._lines + ((location, text.strip()),))
            return
        index = len(self._widgets)
        line = self._line(index, location, "")
        self.column_layout.addWidget(line)
        self._widgets.append(line)
        pending = line.findChild(QLineEdit)
        if pending is not None:
            pending.setFocus()
            pending.editingFinished.disconnect()
            pending.editingFinished.connect(lambda e=pending, w=line: self._first_name(w, e))

    def _first_name(self, line: QWidget, edit: QLineEdit) -> None:
        text = edit.text().strip()
        if not text:
            return
        combo = line.findChild(QComboBox)
        where = str(combo.currentData()) if combo is not None else "local"
        self._store(self._lines + ((where, text),))


class _LegacyRow(SettingRow):
    """"Older file setting": the ``stdsetdef`` or ``stdSetDef`` attribute, kept as is, with a Remove button."""

    def __init__(self, body: "_Body", field: str) -> None:
        super().__init__(body, field, "Older file setting", CAPTION_LEGACY)
        self.field = field
        self.value = QLabel(self)
        self.value.setObjectName("formBuilder.formSetting.%s.value" % field)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.value.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        self.add(self.value)
        self.remove = _Button("Remove", self)
        self.remove.setObjectName("formBuilder.formSetting.%s.remove" % field)
        self.remove.setAccessibleName("Remove older file setting")
        self.remove.clicked.connect(lambda _checked=False: self._remove())
        self.add(self.remove)

    def load(self, doc: UiDocument) -> None:
        value = doc.ui.field(self.field)
        present = isinstance(value, str)
        self.setVisible(present)
        if present:
            self.value.setText('%s = "%s"' % (self.field, value))

    def _remove(self) -> None:
        refusal = self.body.host.run(REMOVE_LEGACY, [SetFormSetting(self.field, None, REMOVE_LEGACY)])
        self.show_error(refusal or "")


class _StepRow(SettingRow):
    """"Step across" or "Step down": 2 to 100 pixels; the default is not stored."""

    def __init__(self, body: "_Body", part: str, label: str) -> None:
        super().__init__(body, "grid.%s" % part, label)
        self.part = part
        self.spin = self.guard(QSpinBox(self))  # type: ignore[assignment]
        self.spin.setObjectName("formBuilder.formSetting.grid.%s" % part)
        self.spin.setAccessibleName("Form setting: %s" % label)
        self.spin.setRange(GRID_STEP_MIN, GRID_STEP_MAX)
        self.spin.setSuffix(" px")
        self.spin.editingFinished.connect(self._done)
        self.add(self.spin)

    def load(self, doc: UiDocument) -> None:
        grid = form_grid(doc)
        value = grid.across if self.part == "across" else grid.down
        self.set_changed(not grid_is_default(doc, self.part))
        if not self.spin.hasFocus():
            self.spin.blockSignals(True)
            self.spin.setValue(value)
            self.spin.blockSignals(False)

    def first_focus(self) -> Optional[QWidget]:
        return self.spin

    def reset_commands(self) -> list:
        return [SetFormGrid(self.part, None, "Reset %s" % self.label_text)]

    def _done(self) -> None:
        grid = form_grid(self.body.host.document)
        if self.spin.value() == (grid.across if self.part == "across" else grid.down):
            return
        if not self.write(SetFormGrid(self.part, self.spin.value(), CHANGE_PREFIX + lower_label(self.label_text))):
            self.load(self.body.host.document)


class _GridCheckRow(SettingRow):
    """"Show grid" or "Snap to grid": on is the default, so only off is stored."""

    def __init__(self, body: "_Body", part: str, label: str) -> None:
        super().__init__(body, "grid.%s" % part, label)
        self.part = part
        self.box = self.guard(QCheckBox(self))  # type: ignore[assignment]
        self.box.setObjectName("formBuilder.formSetting.grid.%s" % part)
        self.box.setAccessibleName("Form setting: %s" % label)
        self.box.toggled.connect(self._toggled)
        self.add(self.box)

    def load(self, doc: UiDocument) -> None:
        grid = form_grid(doc)
        self.set_changed(not grid_is_default(doc, self.part))
        self.box.blockSignals(True)
        self.box.setChecked(grid.show if self.part == "show" else grid.snap)
        self.box.blockSignals(False)

    def first_focus(self) -> Optional[QWidget]:
        return self.box

    def reset_commands(self) -> list:
        return [SetFormGrid(self.part, None, "Reset %s" % self.label_text)]

    def _toggled(self, on: bool) -> None:
        if not self.write(SetFormGrid(self.part, on, CHANGE_PREFIX + lower_label(self.label_text))):
            self.load(self.body.host.document)


# --------------------------------------------------------------------------- bodies


class _Body:
    """A group body: a column of rows, rebuilt from the document after every change."""

    def __init__(self, host: GroupHost, parent: QWidget, key: str, title: str, lead: str = "") -> None:
        self.host = host
        self.key = key
        self.root = QWidget(parent)
        self.root.setObjectName("formBuilder.formSettings.%s" % key)
        self.layout = QVBoxLayout(self.root)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.rows: List[SettingRow] = []
        if lead:
            note = QLabel(lead, self.root)
            note.setObjectName("formBuilder.rowNote")
            note.setWordWrap(True)
            self.layout.addWidget(note)
        self._collapse(parent, key)

    @property
    def widget(self) -> QWidget:
        return self.root

    def add(self, row: SettingRow) -> SettingRow:
        self.rows.append(row)
        self.layout.addWidget(row)
        return row

    def show(self, rows: tuple) -> None:
        del rows
        doc = self.host.document
        for row in self.rows:
            row.load(doc)

    def first_focus(self) -> Optional[QWidget]:
        for row in self.rows:
            target = row.first_focus()
            if target is not None and row.isVisibleTo(self.root):
                return target
        return None

    def _collapse(self, parent: QWidget, key: str) -> None:
        """Closed by default (UX-FSET-001); opening it refreshes the rows, which are not painted while closed."""
        group = parent.parentWidget()
        toggle = group.findChild(QToolButton, "formBuilder.group.%s" % key) if group is not None else None
        if toggle is None:
            return
        toggle.toggled.connect(lambda opened: self._opened(toggle) if opened else None)
        if toggle.isChecked():
            toggle.click()

    def _opened(self, toggle: QToolButton) -> None:
        """Fill the rows, then have the inspector relink its Tab stops, which now include them."""
        self.show(())
        page = toggle.parentWidget()
        while page is not None and not hasattr(page, "request_rebuild"):
            page = page.parentWidget()
        if page is not None:
            page.request_rebuild()


class CodeBody(_Body):
    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        super().__init__(host, parent, CODE, "Code")
        self.add(_TextRow(self, "author", "Author"))
        self.add(_GapsRow(self))
        self.add(_FunctionsRow(self))
        self.add(_TextRow(self, "pixmapfunction", "Picture function", named=True))
        self.add(_IncludesRow(self))
        self.add(_TextRow(self, "exportmacro", "Export macro", CAPTION_KEPT_CODE))
        self.add(_TextRow(self, "comment", "Comment", CAPTION_KEPT_CODE))
        for field in LEGACY_FIELDS:
            self.add(_LegacyRow(self, field))


class TranslationBody(_Body):
    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        super().__init__(host, parent, TRANSLATION, "Translation")
        self.add(_CheckRow(self, "idbasedtr", "Translate by ID", CAPTION_IDS))
        self.add(_TextRow(self, "language", "Code language", CAPTION_KEPT))
        self.add(_TextRow(self, "displayname", "Display name", CAPTION_KEPT))


class FreeBody(_Body):
    def __init__(self, host: GroupHost, parent: QWidget) -> None:
        super().__init__(host, parent, FREE, "Free placement", CAPTION_FREE)
        self.add(_GridCheckRow(self, "show", "Show grid"))
        self.add(_StepRow(self, "across", "Step across"))
        self.add(_StepRow(self, "down", "Step down"))
        self.add(_GridCheckRow(self, "snap", "Snap to grid"))


def _applies_free(document: UiDocument, *_ignored: object) -> bool:
    return has_free_container(document)


def register(registrar: Registrar) -> None:
    del registrar


def register_form_groups(registry: object) -> None:
    # After the Pictures (120) and Button groups (140) sections.
    registry.add(CODE, "Code", lambda host, parent: CodeBody(host, parent), order=150)  # type: ignore[attr-defined]
    registry.add(  # type: ignore[attr-defined]
        TRANSLATION, "Translation", lambda host, parent: TranslationBody(host, parent), order=160
    )
    registry.add(  # type: ignore[attr-defined]
        FREE, "Free placement", lambda host, parent: FreeBody(host, parent), order=170, applies=_applies_free
    )
