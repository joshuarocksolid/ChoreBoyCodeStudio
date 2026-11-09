"""Condition and value builder widgets. They edit a model, never a second store."""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from app.qt.QtCore import QDate, QEvent, QObject, QSize, Qt
from app.qt.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.qtside.formula.builder.model import (
    Arithmetic,
    Atom,
    Condition,
    IfThen,
    Model,
    Row,
    Simple,
    Value,
    family_of,
    picker_label,
    write_formula,
)
from app.features.form_builder.qtside.formula.builder.words import speak
from app.features.form_builder.qtside.theme.chrome import FormChrome, link_ink

_KEY_PRESS = enum_value(getattr(getattr(QEvent, "Type", QEvent), "KeyPress"))
_FOCUS_IN = enum_value(getattr(getattr(QEvent, "Type", QEvent), "FocusIn"))
_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_ESC = enum_value(Qt.Key.Key_Escape)
_TAB = enum_value(Qt.Key.Key_Tab)
_BACKTAB = enum_value(Qt.Key.Key_Backtab)
_SPACE = enum_value(Qt.Key.Key_Space)
_UP = enum_value(Qt.Key.Key_Up)
_DOWN = enum_value(Qt.Key.Key_Down)
_ALT = enum_value(Qt.KeyboardModifier.AltModifier)
_CTRL = enum_value(Qt.KeyboardModifier.ControlModifier)
_ELIDE = getattr(getattr(Qt, "TextElideMode", Qt), "ElideRight")
_ROLE = enum_value(getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole"))
_NO_FOCUS = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
_MENUS = {
    "yesno": (("checked", "is checked"), ("unchecked", "is not checked")),
    "text": (
        ("eq", "is"),
        ("ne", "is not"),
        ("blank", "is blank"),
        ("not_blank", "is not blank"),
        ("contains", "contains"),
        ("starts", "starts with"),
    ),
    "number": (
        ("eq", "is"),
        ("ne", "is not"),
        ("lt", "is less than"),
        ("le", "is at most"),
        ("gt", "is more than"),
        ("ge", "is at least"),
        ("between", "is between"),
    ),
    "date": (("lt", "is before"), ("gt", "is after"), ("today", "is today"), ("blank", "is blank")),
    "time": (("lt", "is before"), ("gt", "is after"), ("blank", "is blank")),
    "datetime": (("lt", "is before"), ("gt", "is after"), ("today", "is today"), ("blank", "is blank")),
    "choice": (("eq", "is"), ("one_of", "is one of")),
}
_NO_VALUE = frozenset({"checked", "unchecked", "blank", "not_blank", "today"})
_OPS = (("+", "+"), ("-", "−"), ("*", "×"), ("/", "÷"))
_SHAPES = (
    ("simple", "A field or number"),
    ("arith", "A calculation (+ − × ÷)"),
    ("if", "If … then … otherwise"),
)
_NUMBER = "\x00number"
_ONE_LINE = 200
_ALIGN_LEFT = getattr(getattr(Qt, "AlignmentFlag", Qt), "AlignLeft")


def _prefix(prefix: str, value: str) -> bool:
    return value.casefold().startswith(prefix.casefold())


def _hold_height(widget: QWidget) -> None:
    """Keep a row from being crushed to nothing when the inspector is short."""

    policy = widget.sizePolicy()
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    policy.setHorizontalPolicy(getattr(names, "Preferred"))
    policy.setVerticalPolicy(getattr(names, "Minimum"))
    widget.setSizePolicy(policy)


def _can_shrink(widget: QWidget) -> None:
    """Let a row get narrower than its text. The closed text elides."""

    policy = widget.sizePolicy()
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    policy.setHorizontalPolicy(getattr(names, "Ignored"))
    widget.setSizePolicy(policy)
    widget.setMinimumWidth(0)


def _hug(button: QPushButton) -> None:
    """A left-aligned control that hugs its words, the way "+ Add check" does."""

    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    button.setSizePolicy(getattr(names, "Maximum"), getattr(names, "Fixed"))
    button.setCursor(getattr(getattr(Qt, "CursorShape", Qt), "PointingHandCursor"))


def _rehome(button: QWidget, parent: QWidget, layout: QHBoxLayout) -> None:
    old = button.parentWidget()
    if old is not None and old.layout() is not None:
        old.layout().removeWidget(button)
    button.setParent(parent)
    layout.addWidget(button)


def paint(widget: QWidget, chrome: FormChrome) -> None:
    focus = chrome.focus_width if chrome.focus_width > 0 else 1
    ink = chrome.accent or chrome.text
    link = link_ink(chrome)
    widget.setStyleSheet(
        "QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPushButton {"
        " color: %s; background: %s; border: 1px solid %s; }"
        "QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,"
        " QDateEdit:focus, QPushButton:focus { border: %dpx solid %s; }"
        "QPushButton[fbLink=\"true\"] { color: %s; background: transparent; border: none;"
        " padding: 0; text-decoration: underline; text-align: left; }"
        "QPushButton[fbLink=\"true\"]:focus { border: %dpx solid %s; }"
        "QLabel { color: %s; background: transparent; }"
        "QLabel[fbCaption=\"true\"] { color: %s; background: transparent; }"
        "QFrame[fbRule=\"true\"] { background: %s; border: none; min-height: 1px; max-height: 1px; }"
        "QListWidget { color: %s; background: %s; border: 1px solid %s; }"
        % (
            chrome.text,
            chrome.input,
            chrome.border,
            focus,
            ink,
            link,
            focus,
            ink,
            chrome.text,
            chrome.faint or chrome.muted or chrome.text,
            chrome.border,
            chrome.text,
            chrome.popup or chrome.input,
            chrome.popup_border or chrome.border,
        )
    )


class FieldPicker(QWidget):
    """A filterable list. The line shows "Qty · Whole number" and stores the object name."""

    def __init__(
        self,
        busy: Callable[[], bool],
        on_change: Callable[[], None],
        parent: QWidget,
        extra: Sequence[Tuple[str, str]] = (),
    ) -> None:
        super().__init__(parent)
        self._busy = busy
        self._on_change = on_change
        self._extra = tuple(extra)
        self._on_extra: Optional[Callable[[str], None]] = None
        self._env: Optional[FormulaEnv] = None
        self._name = ""
        self._label = ""
        self._loading = False
        _can_shrink(self)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.edit = QLineEdit(self)
        _can_shrink(self.edit)
        self.edit.setAccessibleName("Field")
        self.edit.setPlaceholderText("Field")
        self.list = QListWidget(self)
        self.list.setFocusPolicy(_NO_FOCUS)
        self.list.setMinimumWidth(0)
        self.list.hide()
        column.addWidget(self.edit)
        column.addWidget(self.list)
        self.edit.textEdited.connect(self._edited)
        self.edit.installEventFilter(self)

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self._env = env

    def set_object_name(self, name: str) -> None:
        self.edit.setObjectName(name)

    def name(self) -> str:
        return self._name

    def pending(self) -> bool:
        return bool(self.edit.text().strip()) and not self._name

    def set_name(self, name: str) -> None:
        self._loading = True
        self._name = name
        self._label = picker_label(self._env, name) if self._env is not None and name else name
        self.edit.setText(self._label)
        self.edit.setToolTip(self._label)
        self.list.hide()
        self._loading = False
        self._elide()

    def close_popup(self) -> bool:
        if not self.list.isVisible():
            return False
        self.list.hide()
        return True

    def focus_edit(self) -> None:
        self.edit.setFocus()

    def eventFilter(self, watched: QObject, event: object) -> bool:  # noqa: N802
        if watched is not self.edit:
            return super().eventFilter(watched, event)  # type: ignore[arg-type]
        if enum_value(event.type()) == _FOCUS_IN:  # type: ignore[attr-defined]
            self._elide()
            return False
        if enum_value(event.type()) != _KEY_PRESS:  # type: ignore[attr-defined]
            return super().eventFilter(watched, event)  # type: ignore[arg-type]
        key = enum_value(event.key())  # type: ignore[attr-defined]
        mods = enum_value(event.modifiers())  # type: ignore[attr-defined]
        if mods & _CTRL:
            return False
        if key == _ESC and self.list.isVisible():
            self.list.hide()
            return True
        if key == _DOWN and mods & _ALT:
            self._show(self.edit.text(), all_rows=True)
            return True
        if key == _DOWN and self.list.count():
            self._show(self.edit.text(), all_rows=not self.list.isVisible())
            self._move(1)
            return True
        if key == _UP and self.list.isVisible():
            self._move(-1)
            return True
        if key in _ENTER and self.list.isVisible() and self.list.count():
            self._accept()
            return True
        if key == _TAB and self.list.isVisible() and self.list.count():
            self._accept()
            return True
        return False

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._elide()

    def _edited(self, text: str) -> None:
        if self._loading or self._busy():
            return
        if text.strip() != self._label:
            self._name = ""
        self._label = ""
        self._show(text, all_rows=False)
        self._on_change()

    def _show(self, text: str, all_rows: bool) -> None:
        env = self._env
        self.list.clear()
        if env is None:
            self.list.hide()
            return
        query = "" if all_rows else text.strip()
        if query == self._label:
            query = ""
        matched = []
        for name in env.widgets:
            facts = env.widgets[name]
            display = facts.display or name
            if query and not _prefix(query, name) and not _prefix(query, display):
                continue
            # A caption label and the field it names both match "qty". The field
            # comes first. Down still reaches the label.
            label_penalty = 1 if (facts.class_name or "").rsplit(".", 1)[-1] == "QLabel" else 0
            name_hit = 0 if query and _prefix(query, name) else 1
            matched.append((label_penalty, name_hit, name.casefold(), name))
        matched.sort()
        for _penalty, _hit, _folded, name in matched:
            label = picker_label(env, name)
            item = QListWidgetItem(label)
            item.setData(_ROLE, name)
            item.setToolTip(label)
            self.list.addItem(item)
        for key, label in self._extra:
            item = QListWidgetItem(label)
            item.setData(_ROLE, key)
            item.setToolTip(label)
            self.list.addItem(item)
        if self.list.count() == 0:
            self.list.hide()
            return
        self.list.setCurrentRow(0)
        rows = min(4, self.list.count())
        self.list.setFixedHeight(max(24, rows * max(18, self.list.sizeHintForRow(0))))
        self.list.show()

    def _move(self, step: int) -> None:
        if not self.list.count():
            return
        row = self.list.currentRow()
        self.list.setCurrentRow(max(0, min(self.list.count() - 1, row + step)))

    def _accept(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        name = item.data(_ROLE)
        if not isinstance(name, str):
            return
        if name.startswith("\x00"):
            self.list.hide()
            if self._on_extra is not None:
                self._on_extra(name)
            return
        self.set_name(name)
        self._on_change()

    def _elide(self) -> None:
        if not self._label:
            return
        # A focused field still shows the start of its name. Filtering shows the typed text.
        if self.edit.hasFocus() and not self._name and self.edit.text().strip() != self._label:
            return
        room = max(1, self.edit.contentsRect().width() - 8)
        shown = self.edit.fontMetrics().elidedText(self._label, _ELIDE, room)
        if self.edit.text() != shown:
            self._loading = True
            self.edit.setText(shown)
            self._loading = False
        tip = self._label if shown != self._label else ""
        if self.edit.toolTip() != tip:
            self.edit.setToolTip(tip)


class _Combo(QComboBox):
    """A menu whose closed text elides, with the full words in the tooltip.

    The line is read-only. Up and Down change the choice. Letters do nothing,
    so the only typing in the builder is the field filter.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._floor = 36
        self.setMinimumWidth(self._floor)
        self.setEditable(True)
        policy = getattr(QComboBox, "NoInsert", None)
        if policy is None:
            policy = getattr(getattr(QComboBox, "InsertPolicy", QComboBox), "NoInsert", None)
        if policy is not None:
            self.setInsertPolicy(policy)  # type: ignore[arg-type]
        self._full = ""
        edit = self.lineEdit()
        if edit is not None:
            edit.setReadOnly(True)
            edit.installEventFilter(self)
        self.currentIndexChanged.connect(lambda _index: self._sync())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        base = QComboBox.minimumSizeHint(self)
        return QSize(self._floor, max(22, base.height()))

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSizeHint()

    def eventFilter(self, watched: QObject, event: object) -> bool:  # noqa: N802
        edit = self.lineEdit()
        if watched is not edit or enum_value(event.type()) != _KEY_PRESS:  # type: ignore[attr-defined]
            return super().eventFilter(watched, event)  # type: ignore[arg-type]
        key = enum_value(event.key())  # type: ignore[attr-defined]
        mods = enum_value(event.modifiers())  # type: ignore[attr-defined]
        if mods & _CTRL:
            return False
        if key == _DOWN and mods & _ALT:
            self.showPopup()
            return True
        if key == _DOWN:
            self.setCurrentIndex(min(self.count() - 1, self.currentIndex() + 1))
            return True
        if key == _UP:
            self.setCurrentIndex(max(0, self.currentIndex() - 1))
            return True
        if key in _ENTER or key in (_ESC, _TAB, _BACKTAB):
            return False
        if key == _SPACE:
            self.showPopup()
            return True
        return True

    def set_items(self, rows: Sequence[Tuple[str, str]], key: str) -> None:
        self.blockSignals(True)
        self.clear()
        for item_key, label in rows:
            self.addItem(label, item_key)
        index = self.findData(key)
        self.setCurrentIndex(index if index >= 0 else 0)
        self.blockSignals(False)
        self._sync()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._sync()

    def _sync(self) -> None:
        index = self.currentIndex()
        self._full = self.itemText(index) if index >= 0 else ""
        self.setToolTip(self._full)
        edit = self.lineEdit()
        if edit is None or self.width() <= 0:
            return
        room = max(1, edit.contentsRect().width() - 8)
        shown = edit.fontMetrics().elidedText(self._full, _ELIDE, room)
        edit.setText(shown)


def _spin(parent: QWidget) -> QDoubleSpinBox:
    box = QDoubleSpinBox(parent)
    box.setRange(-1000000000, 1000000000)
    box.setDecimals(0)
    box.setMinimumWidth(0)
    return box


def _decimal_places(text: str) -> int:
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1].rstrip("0"))


def _advance(widget: QWidget, text: str) -> int:
    metrics = widget.fontMetrics()
    advance = getattr(metrics, "horizontalAdvance", None)
    if advance is not None:
        return int(advance(text))
    return int(metrics.boundingRect(text).width())


class _OpCombo(_Combo):
    """A fixed-width operator. Wide enough for ÷ and the arrow, never a sliver."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._lock()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._lock()

    def _lock(self) -> None:
        floor = _advance(self, "÷") + 30
        if floor == self._floor and self.width() == floor:
            return
        self._floor = floor
        self.setFixedWidth(floor)
        self.setMinimumWidth(floor)
        self.updateGeometry()


def _spell(box: QDoubleSpinBox) -> str:
    text = ("%.4f" % box.value()).rstrip("0").rstrip(".")
    if text in ("", "-0", "-"):
        return "0"
    return text


class ValueBox(QWidget):
    """The value beside a comparison, or one arithmetic term."""

    def __init__(self, busy: Callable[[], bool], on_change: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self._busy = busy
        self._on_change = on_change
        self._family = "text"
        self._op = "eq"
        self.setMinimumWidth(0)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        self.kind = _Combo(self)
        self.kind.setAccessibleName("Value kind")
        self.text = QLineEdit(self)
        self.text.setAccessibleName("Value")
        self.text.setMinimumWidth(0)
        self.low = _spin(self)
        self.low.setAccessibleName("Low")
        self.high = _spin(self)
        self.high.setAccessibleName("High")
        self.date = QDateEdit(self)
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setAccessibleName("Date")
        self.date.setMinimumWidth(0)
        self.field = FieldPicker(busy, on_change, self)
        self._editors: Tuple[QWidget, ...] = (self.kind, self.text, self.low, self.high, self.date, self.field)
        for editor in self._editors:
            line.addWidget(editor, 1)
        self.text.textEdited.connect(self._changed)
        self.low.valueChanged.connect(self._changed)
        self.high.valueChanged.connect(self._changed)
        self.date.dateChanged.connect(self._changed)
        self.kind.currentIndexChanged.connect(self._changed)
        self.hide_all()

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self.field.set_env(env)

    def hide_all(self) -> None:
        for editor in self._editors:
            editor.hide()

    def show_for(
        self,
        family: str,
        op: str,
        values: Sequence[Atom],
        *,
        prefer_field: bool = False,
    ) -> None:
        self._family = family
        self._op = op
        self.hide_all()
        if op in _NO_VALUE:
            return
        if op == "between":
            self.low.show()
            self.high.show()
            self._set_spin(self.low, values[0] if values else None)
            self._set_spin(self.high, values[1] if len(values) > 1 else None)
            return
        if op == "one_of":
            self.text.setAccessibleName("Choices")
            self.text.setPlaceholderText("Choices")
            self.text.show()
            self.text.setText(", ".join(item.text for item in values))
            return
        self.text.setAccessibleName("Value")
        self.text.setPlaceholderText("Value")
        use_field = prefer_field or bool(values) and values[0].kind == "field"
        if family == "number":
            self._kind_items((("number", "Number"), ("field", "Field")), "field" if use_field else "number")
            self._show_number(values, use_field)
            return
        if family in ("date", "time", "datetime"):
            self._kind_items((("date", "Date"), ("field", "Field")), "field" if use_field else "date")
            self._show_date(values, use_field)
            return
        self._kind_items((("text", "Text"), ("field", "Field")), "field" if use_field else "text")
        if use_field:
            self.field.show()
            self.field.set_name(values[0].text if values else "")
        else:
            self.text.show()
            self.text.setText(values[0].text if values and values[0].kind == "text" else "")

    def atoms(self) -> Optional[Tuple[Atom, ...]]:
        op = self._op
        if op in _NO_VALUE:
            return ()
        if op == "between":
            return (Atom("number", _spell(self.low)), Atom("number", _spell(self.high)))
        if op == "one_of":
            parts = tuple(piece.strip() for piece in self.text.text().split(",") if piece.strip())
            if not parts:
                return None
            return tuple(Atom("text", piece) for piece in parts)
        chosen = self.kind.currentData()
        if chosen == "field":
            if not self.field.name():
                return None
            return (Atom("field", self.field.name()),)
        if chosen == "number":
            return (Atom("number", _spell(self.low)),)
        if chosen == "date":
            day = self.date.date()
            return (Atom("date", "%04d-%02d-%02d" % (day.year(), day.month(), day.day())),)
        return (Atom("text", self.text.text()),)

    def close_popup(self) -> bool:
        return self.field.close_popup()

    def _kind_items(self, rows: Sequence[Tuple[str, str]], current: str) -> None:
        self.kind.show()
        self.kind.set_items(rows, current)

    def _show_number(self, values: Sequence[Atom], use_field: bool) -> None:
        if use_field:
            self.field.show()
            self.field.set_name(values[0].text if values else "")
            return
        self.low.show()
        self._set_spin(self.low, values[0] if values else None)

    def _show_date(self, values: Sequence[Atom], use_field: bool) -> None:
        if use_field:
            self.field.show()
            self.field.set_name(values[0].text if values else "")
            return
        self.date.show()
        if values and values[0].kind == "date":
            year, month, day = values[0].text.split("-")
            self.date.setDate(QDate(int(year), int(month), int(day)))

    def _set_spin(self, box: QDoubleSpinBox, atom: Optional[Atom]) -> None:
        text = atom.text if atom is not None and atom.kind == "number" else "0"
        box.blockSignals(True)
        box.setDecimals(_decimal_places(text))
        try:
            box.setValue(float(text))
        except ValueError:
            box.setValue(0)
        box.blockSignals(False)

    def _changed(self, *_args: object) -> None:
        if self._busy():
            return
        chosen = self.kind.currentData()
        if self.kind.isVisible() and chosen == "field" and not self.field.isVisible():
            self.low.hide()
            self.text.hide()
            self.date.hide()
            self.field.show()
        elif self.kind.isVisible() and chosen == "number" and not self.low.isVisible():
            self.field.hide()
            self.low.show()
        elif self.kind.isVisible() and chosen == "date" and not self.date.isVisible():
            self.field.hide()
            self.date.show()
        elif self.kind.isVisible() and chosen == "text" and not self.text.isVisible():
            self.field.hide()
            self.text.show()
        self._on_change()


class _CondRow(QWidget):
    def __init__(self, busy: Callable[[], bool], on_change: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self._busy = busy
        self._on_change = on_change
        self._env: Optional[FormulaEnv] = None
        self._wide = False
        self.setMinimumWidth(0)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(2)
        self.rule = QFrame(self)
        self.rule.setProperty("fbRule", True)
        self.rule.setFixedHeight(1)
        self.rule.hide()
        self.field = FieldPicker(busy, self._field_changed, self)
        self.cmp = _Combo(self)
        self.cmp.setAccessibleName("Comparison")
        self.value = ValueBox(busy, on_change, self)
        self.remove = QPushButton("×", self)
        self.remove.setProperty("fbIcon", True)
        self.remove.setAccessibleName("Remove this condition")
        self.remove.setToolTip("Remove this condition")
        self.remove.setFixedSize(22, 22)
        self._indent = QWidget(self)
        self._indent.setFixedWidth(12)
        self._grid.addWidget(self.rule, 0, 0, 1, 4)
        self._place(False)
        self.cmp.currentIndexChanged.connect(self._op_changed)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = super().minimumSizeHint()
        # The wide layout's hint must not lock the inspector open. 236 px wraps.
        return QSize(min(hint.width(), 96), hint.height())

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        wide = self.width() >= _ONE_LINE
        if wide != self._wide:
            self._place(wide)

    def set_divided(self, divided: bool) -> None:
        self.rule.setVisible(divided)

    def _place(self, wide: bool) -> None:
        """One line when the row is wide enough. Otherwise the comparison sits 12 px under the field."""

        self._wide = wide
        grid = self._grid
        for widget in (self.field, self.cmp, self.value, self.remove, self._indent):
            grid.removeWidget(widget)
        if wide:
            self._indent.hide()
            grid.addWidget(self.field, 1, 0)
            grid.addWidget(self.cmp, 1, 1)
            grid.addWidget(self.value, 1, 2)
            grid.addWidget(self.remove, 1, 3)
            grid.setColumnStretch(0, 2)
            grid.setColumnMinimumWidth(0, 0)
        else:
            grid.addWidget(self.field, 1, 0, 1, 4)
            grid.addWidget(self._indent, 2, 0)
            grid.addWidget(self.cmp, 2, 1)
            grid.addWidget(self.value, 2, 2)
            grid.addWidget(self.remove, 2, 3)
            self._indent.show()
            grid.setColumnStretch(0, 0)
            grid.setColumnMinimumWidth(0, 12)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 0)

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self.field.set_env(env)
        self.value.set_env(env)
        self._env = env

    def set_prefix(self, prefix: str) -> None:
        self.setObjectName(prefix)
        self.field.set_object_name(prefix + ".field")
        self.cmp.setObjectName(prefix + ".cmp")

    def load(self, row: Row) -> None:
        self.field.set_name(row.field)
        self._fill_menu(row.op)
        family = family_of(self._env, row.field) if self._env is not None and row.field else "text"
        self.value.show_for(family, row.op, row.values)

    def blank(self) -> bool:
        return not self.field.name() and not self.field.pending()

    def build(self) -> Optional[Row]:
        if self.field.pending():
            return None
        name = self.field.name()
        if not name:
            return None
        op = self.cmp.currentData()
        if not isinstance(op, str) or not op:
            return None
        atoms = self.value.atoms()
        if atoms is None:
            return None
        return Row(name, op, atoms)

    def close_popup(self) -> bool:
        return self.field.close_popup() or self.value.close_popup()

    def _field_changed(self) -> None:
        if not self._busy():
            kept = self.cmp.currentData()
            self._fill_menu(kept if isinstance(kept, str) else "")
            op = self.cmp.currentData()
            family = family_of(self._env, self.field.name()) if self._env is not None else "text"
            self.value.show_for(family or "text", op if isinstance(op, str) else "eq", ())
        self._on_change()

    def _op_changed(self, _index: int) -> None:
        if self._busy():
            return
        op = self.cmp.currentData()
        family = family_of(self._env, self.field.name()) if self._env is not None else "text"
        self.value.show_for(family or "text", op if isinstance(op, str) else "eq", ())
        self._sync_value()
        self._on_change()

    def _fill_menu(self, op: str) -> None:
        family = "text"
        if self._env is not None and self.field.name():
            family = family_of(self._env, self.field.name()) or "text"
        rows = _MENUS.get(family, _MENUS["text"])
        wanted = op if any(key == op for key, _label in rows) else rows[0][0]
        self.cmp.set_items(rows, wanted)
        shown = self.cmp.itemText(max(0, self.cmp.currentIndex())) or "is checked"
        floor = max(72, _advance(self.cmp, shown) + 28)
        self.cmp._floor = floor
        self.cmp.setMinimumWidth(floor)
        self._sync_value()

    def _sync_value(self) -> None:
        op = self.cmp.currentData()
        self.value.setVisible(isinstance(op, str) and op not in _NO_VALUE)


class ConditionForm(QWidget):
    def __init__(self, busy: Callable[[], bool], on_change: Callable[[], None], prefix: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._busy = busy
        self._on_change = on_change
        self._prefix = prefix
        self._env: Optional[FormulaEnv] = None
        self._rows: List[_CondRow] = []
        self.setMinimumWidth(0)
        _hold_height(self)
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(2)
        self.join = _Combo(self)
        self.join.setObjectName(prefix + ".join")
        self.join.setAccessibleName("all of")
        self.join.set_items((("and", "all of"), ("or", "any of")), "and")
        self.join.currentIndexChanged.connect(lambda _index: on_change())
        self._head = QWidget(self)
        self._head_row = QHBoxLayout(self._head)
        self._head_row.setContentsMargins(0, 0, 0, 0)
        self._head_row.setSpacing(8)
        self._head_row.addWidget(self.join, 1)
        self.add = QPushButton("+ condition", self)
        self.add.setObjectName(prefix + ".add")
        self.add.setAccessibleName("+ condition")
        self.add.setProperty("fbLink", True)
        self.add.setFlat(True)
        _hug(self.add)
        self.add.clicked.connect(self._add_blank)
        self._column.addWidget(self._head)
        self._column.addWidget(self.add, 0, _ALIGN_LEFT)

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self._env = env
        for row in self._rows:
            row.set_env(env)

    def load(self, model: Condition) -> None:
        self.join.set_items((("and", "all of"), ("or", "any of")), model.join)
        while self._rows:
            self._drop(self._rows[-1], notify=False)
        rows = model.rows or (Row("", "checked"),)
        for row in rows:
            self._append(row)

    def draft_model(self) -> Optional[Condition]:
        built: List[Row] = []
        for row in self._rows:
            if row.blank():
                continue
            one = row.build()
            if one is None:
                return None
            built.append(one)
        join = self.join.currentData()
        return Condition(join if isinstance(join, str) else "and", tuple(built))

    def focus_first(self) -> None:
        if self._rows:
            self._rows[0].field.focus_edit()
        else:
            self.join.setFocus()

    def close_popup(self) -> bool:
        return any(row.close_popup() for row in self._rows)

    def _add_blank(self) -> None:
        if self._busy():
            return
        self._append(Row("", "eq"))
        self._rows[-1].field.focus_edit()
        self._on_change()

    def _append(self, row: Row) -> None:
        widget = _CondRow(self._busy, self._on_change, self)
        widget.set_env(self._env)
        widget.set_prefix("%s.row.%d" % (self._prefix, len(self._rows)))
        widget.load(row)
        widget.remove.clicked.connect(lambda widget=widget: self._remove(widget))
        if len(self._rows) == 0:
            widget.remove.hide()
        self._rows.append(widget)
        self._column.insertWidget(self._column.count() - 1, widget)
        self._sync_remove()

    def _remove(self, widget: _CondRow) -> None:
        if len(self._rows) <= 1:
            return
        self._drop(widget, notify=True)

    def _drop(self, widget: _CondRow, notify: bool) -> None:
        if widget in self._rows:
            self._rows.remove(widget)
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()
        self._sync_remove()
        if notify:
            self._on_change()

    def adopt_switch(self, button: QWidget) -> None:
        _rehome(button, self._head, self._head_row)

    def release_switch(self, button: QWidget) -> None:
        if button.parentWidget() is self._head:
            self._head_row.removeWidget(button)

    def _sync_remove(self) -> None:
        show = len(self._rows) > 1
        for index, row in enumerate(self._rows):
            row.remove.setVisible(show)
            row.set_divided(index > 0)


def _branch(caption: str, widget: QWidget, parent: QWidget) -> QWidget:
    """A caption in faint type, with its block indented 12 px underneath."""

    block = QWidget(parent)
    _hold_height(block)
    column = QVBoxLayout(block)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(2)
    label = QLabel(caption, block)
    label.setProperty("fbCaption", True)
    font = label.font()
    if font.pointSize() > 0:
        font.setPointSize(max(8, font.pointSize() - 1))
    label.setFont(font)
    body = QWidget(block)
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(12, 0, 0, 0)
    body_layout.setSpacing(0)
    body_layout.addWidget(widget)
    column.addWidget(label)
    column.addWidget(body)
    return block


def _is_decimal_field(env: Optional[FormulaEnv], name: str) -> int:
    """Decimal places to show beside a decimal field. Whole numbers stay plain."""

    if env is None or not name:
        return 0
    facts = env.widgets.get(name)
    if facts is None:
        return 0
    leaf = (facts.class_name or "").rsplit(".", 1)[-1]
    kind = (facts.kind or "").casefold()
    if leaf != "QDoubleSpinBox" and kind not in ("number", "money", "percent", "decimal"):
        return 0
    return max(0, int(facts.decimals))


class TermSlot(QWidget):
    """One field, or a plain number. The list ends with "A number…"."""

    def __init__(self, busy: Callable[[], bool], on_change: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._number = False
        self._places = 0
        self.setMinimumWidth(0)
        self.field = FieldPicker(busy, on_change, self, extra=((_NUMBER, "A number…"),))
        self.field._on_extra = self._pick_number
        self.spin = _spin(self)
        self.spin.setAccessibleName("Number")
        self.back = QPushButton("×", self)
        self.back.setProperty("fbIcon", True)
        self.back.setAccessibleName("Use a field instead")
        self.back.setToolTip("Use a field instead")
        self.back.setFixedSize(22, 22)
        self.back.clicked.connect(lambda: self._use_field(True))
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        line.addWidget(self.field, 1)
        line.addWidget(self.spin, 1)
        line.addWidget(self.back)
        self.spin.valueChanged.connect(lambda *_args: on_change())
        self._use_field(False)

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self.field.set_env(env)

    def load_atom(self, atom: Optional[Atom], paired: int = 0) -> None:
        if atom is not None and atom.kind == "number":
            self._places = _decimal_places(atom.text)
            self._show_number(atom.text, paired)
            return
        self._use_field(False)
        self.field.set_name(atom.text if atom is not None else "")

    def apply_paired(self, places: int) -> None:
        if not self._number:
            return
        self.spin.blockSignals(True)
        self.spin.setDecimals(max(self._places, places))
        self.spin.blockSignals(False)

    def atoms(self) -> Optional[Tuple[Atom, ...]]:
        if self._number:
            return (Atom("number", _spell(self.spin)),)
        if not self.field.name():
            return None if self.field.pending() else ()
        return (Atom("field", self.field.name()),)

    def close_popup(self) -> bool:
        return self.field.close_popup()

    def _pick_number(self, _key: str) -> None:
        self._places = 0
        self._show_number("0", 0)
        self._on_change()

    def _show_number(self, text: str, paired: int) -> None:
        self._number = True
        self.field.hide()
        self.field.close_popup()
        self.spin.blockSignals(True)
        self.spin.setDecimals(max(_decimal_places(text), paired))
        try:
            self.spin.setValue(float(text))
        except ValueError:
            self.spin.setValue(0)
        self.spin.blockSignals(False)
        self.spin.show()
        self.back.show()

    def _use_field(self, notify: bool) -> None:
        self._number = False
        self.spin.hide()
        self.back.hide()
        self.field.show()
        self.field.set_name("")
        if notify and not self.field._busy():
            self._on_change()


class _Term(QWidget):
    def __init__(self, busy: Callable[[], bool], on_change: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        self.op = _OpCombo(self)
        self.op.setAccessibleName("Operator")
        self.op.set_items(_OPS, "+")
        self.value = TermSlot(busy, on_change, self)
        line.addWidget(self.op)
        line.addWidget(self.value, 1)
        self.op.currentIndexChanged.connect(lambda _index: on_change())

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self.value.set_env(env)

    def close_popup(self) -> bool:
        return self.value.close_popup()


class ValueForm(QWidget):
    def __init__(
        self,
        busy: Callable[[], bool],
        on_change: Callable[[], None],
        prefix: str,
        parent: QWidget,
        *,
        allow_if: bool,
    ) -> None:
        super().__init__(parent)
        self._busy = busy
        self._on_change = on_change
        self._prefix = prefix
        self._allow_if = allow_if
        self._env: Optional[FormulaEnv] = None
        self._terms: List[_Term] = []
        self.setMinimumWidth(0)
        _hold_height(self)
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(2)
        shapes = _SHAPES if allow_if else _SHAPES[:2]
        self.shape = _Combo(self)
        self.shape.setObjectName(prefix + ".shape")
        self.shape.setAccessibleName("Shape")
        self.shape.set_items(shapes, "simple")
        self._head = QWidget(self)
        self._head_row = QHBoxLayout(self._head)
        self._head_row.setContentsMargins(0, 0, 0, 0)
        self._head_row.setSpacing(8)
        self._head_row.addWidget(self.shape, 1)
        self.simple = TermSlot(busy, on_change, self)
        self._arith = QWidget(self)
        arith_column = QVBoxLayout(self._arith)
        arith_column.setContentsMargins(0, 0, 0, 0)
        arith_column.setSpacing(2)
        self._arith_column = arith_column
        self.add = QPushButton("+ term", self._arith)
        self.add.setObjectName(prefix + ".add")
        self.add.setAccessibleName("+ term")
        self.add.setProperty("fbLink", True)
        self.add.setFlat(True)
        _hug(self.add)
        self.add.clicked.connect(self._add_term)
        arith_column.addWidget(self.add, 0, _ALIGN_LEFT)
        self._if: Optional[QWidget] = None
        self.test: Optional[ConditionForm] = None
        self.then_value: Optional[ValueForm] = None
        self.other: Optional[ValueForm] = None
        if allow_if:
            self._if = QWidget(self)
            _hold_height(self._if)
            if_column = QVBoxLayout(self._if)
            if_column.setContentsMargins(0, 0, 0, 0)
            if_column.setSpacing(6)
            self.test = ConditionForm(busy, on_change, prefix + ".if", self._if)
            self.then_value = ValueForm(busy, on_change, prefix + ".then", self._if, allow_if=False)
            self.other = ValueForm(busy, on_change, prefix + ".else", self._if, allow_if=False)
            self.test.setObjectName(prefix + ".if")
            self.then_value.setObjectName(prefix + ".then")
            self.other.setObjectName(prefix + ".else")
            for caption, widget in (
                ("If", self.test),
                ("Then", self.then_value),
                ("Otherwise", self.other),
            ):
                if_column.addWidget(_branch(caption, widget, self._if))
        self._column.addWidget(self._head)
        self._column.addWidget(self.simple)
        self._column.addWidget(self._arith)
        if self._if is not None:
            self._column.addWidget(self._if)
        self.shape.currentIndexChanged.connect(lambda _index: self._show_shape(True))
        self._show_shape(False)

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self._env = env
        self.simple.set_env(env)
        if self.test is not None:
            self.test.set_env(env)
        if self.then_value is not None:
            self.then_value.set_env(env)
        if self.other is not None:
            self.other.set_env(env)
        for term in self._terms:
            term.set_env(env)

    def load(self, model: Value) -> None:
        if isinstance(model, IfThen) and self.test is not None and self.then_value is not None and self.other is not None:
            self.shape.set_items(_SHAPES, "if")
            self.test.load(model.test)
            self.then_value.load(model.then_value)
            self.other.load(model.other)
        elif isinstance(model, Arithmetic):
            shapes = _SHAPES if self._allow_if else _SHAPES[:2]
            self.shape.set_items(shapes, "arith")
            self._load_arith(model)
        else:
            shapes = _SHAPES if self._allow_if else _SHAPES[:2]
            self.shape.set_items(shapes, "simple")
            atom = model.atom if isinstance(model, Simple) else Atom("field", "")
            self.simple.load_atom(atom if atom.text else None, self._paired_decimals())
        self._show_shape(False)

    def adopt_switch(self, button: QWidget) -> None:
        _rehome(button, self._head, self._head_row)

    def release_switch(self, button: QWidget) -> None:
        if button.parentWidget() is self._head:
            self._head_row.removeWidget(button)

    def _paired_decimals(self) -> int:
        best = 0
        for term in self._terms:
            got = term.value.atoms()
            if not got or got[0].kind != "field":
                continue
            best = max(best, _is_decimal_field(self._env, got[0].text))
        return best

    def draft_model(self) -> Optional[Value]:
        kind = self.shape.currentData()
        if kind == "if" and self.test is not None and self.then_value is not None and self.other is not None:
            test = self.test.draft_model()
            then_value = self.then_value.draft_model()
            other = self.other.draft_model()
            if test is None or then_value is None or other is None:
                return None
            if not test.rows or isinstance(then_value, IfThen) or isinstance(other, IfThen):
                return None
            if not write_formula(then_value) or not write_formula(other):
                return None
            return IfThen(test, then_value, other)
        if kind == "arith":
            atoms: List[Atom] = []
            ops: List[str] = []
            for index, term in enumerate(self._terms):
                got = term.value.atoms()
                if not got:
                    return None
                atoms.append(got[0])
                if index:
                    op = term.op.currentData()
                    if not isinstance(op, str):
                        return None
                    ops.append(op)
            if len(atoms) < 2:
                return None
            return Arithmetic(tuple(atoms), tuple(ops))
        atoms = self.simple.atoms()
        if not atoms:
            if self.simple.field.pending():
                return None
            return Simple(Atom("field", ""))
        return Simple(atoms[0])

    def focus_first(self) -> None:
        self.shape.setFocus()

    def close_popup(self) -> bool:
        closed = self.simple.close_popup()
        if self.test is not None:
            closed = self.test.close_popup() or closed
        if self.then_value is not None:
            closed = self.then_value.close_popup() or closed
        if self.other is not None:
            closed = self.other.close_popup() or closed
        return any(term.close_popup() for term in self._terms) or closed

    def _show_shape(self, notify: bool) -> None:
        kind = self.shape.currentData()
        self.simple.setVisible(kind == "simple")
        self._arith.setVisible(kind == "arith")
        if self._if is not None:
            self._if.setVisible(kind == "if")
        if kind == "arith" and len(self._terms) < 2 and not self._busy():
            self._ensure_terms(2)
        if notify and not self._busy():
            self._on_change()

    def _ensure_terms(self, count: int) -> None:
        while len(self._terms) < count and len(self._terms) < 4:
            term = _Term(self._busy, self._term_changed, self._arith)
            term.set_env(self._env)
            term.setObjectName("%s.term.%d" % (self._prefix, len(self._terms)))
            term.op.setObjectName("%s.op.%d" % (self._prefix, len(self._terms)))
            term.value.field.set_object_name("%s.term.%d.field" % (self._prefix, len(self._terms)))
            if len(self._terms) == 0:
                term.op.hide()
            self._terms.append(term)
            self._arith_column.insertWidget(self._arith_column.count() - 1, term)
        self.add.setEnabled(len(self._terms) < 4)

    def _term_changed(self) -> None:
        places = self._paired_decimals()
        for term in self._terms:
            term.value.apply_paired(places)
        self._on_change()

    def _add_term(self) -> None:
        if self._busy() or len(self._terms) >= 4:
            return
        self._ensure_terms(len(self._terms) + 1)
        self._on_change()

    def _load_arith(self, model: Arithmetic) -> None:
        while self._terms:
            term = self._terms.pop()
            term.setParent(None)
            term.deleteLater()
        self._ensure_terms(len(model.atoms))
        paired = 0
        for atom in model.atoms:
            if atom.kind == "field":
                paired = max(paired, _is_decimal_field(self._env, atom.text))
        for index, atom in enumerate(model.atoms):
            term = self._terms[index]
            term.value.load_atom(atom, paired)
            if index:
                term.op.set_items(_OPS, model.ops[index - 1])


class FormulaBuilder(QWidget):
    """The State row's builder. ``draft`` is None while a row is half filled."""

    def __init__(self, on_change: Callable[[], None], parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.builder")
        self.setMinimumWidth(0)
        _hold_height(self)
        self._on_change = on_change
        self._busy_flag = False
        self._env: Optional[FormulaEnv] = None
        self._kind = "condition"
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        self.condition = ConditionForm(self.busy, self._changed, "formBuilder.builder.cond", self)
        self.value = ValueForm(self.busy, self._changed, "formBuilder.builder", self, allow_if=True)
        column.addWidget(self.condition)
        column.addWidget(self.value)
        self.value.hide()

    def busy(self) -> bool:
        return self._busy_flag

    def set_env(self, env: Optional[FormulaEnv]) -> None:
        self._env = env
        self.condition.set_env(env)
        self.value.set_env(env)

    def load(self, model: Model, kind: str) -> None:
        self._busy_flag = True
        self._kind = kind
        try:
            self.set_env(self._env)
            if kind == "condition" and isinstance(model, Condition):
                self.condition.load(model)
                self.condition.show()
                self.value.hide()
            elif kind == "value" and not isinstance(model, Condition):
                self.value.load(model)
                self.value.show()
                self.condition.hide()
        finally:
            self._busy_flag = False

    def adopt_switch(self, button: QWidget) -> None:
        if self._kind == "value":
            self.condition.release_switch(button)
            self.value.adopt_switch(button)
        else:
            self.value.release_switch(button)
            self.condition.adopt_switch(button)

    def release_switch(self, button: QWidget) -> None:
        self.condition.release_switch(button)
        self.value.release_switch(button)

    def spoken(self) -> str:
        if self._env is None:
            return ""
        model = self.condition.draft_model() if self._kind == "condition" else self.value.draft_model()
        if model is None:
            return ""
        return speak(model, self._env)

    def draft(self) -> Optional[str]:
        """The formula, "" when the builder is empty, or None when a row is unfinished."""

        if self._kind == "condition":
            model = self.condition.draft_model()
        else:
            found = self.value.draft_model()
            model = found
        if model is None:
            return None
        return write_formula(model)

    def focus_first(self) -> None:
        if self._kind == "value":
            self.value.focus_first()
        else:
            self.condition.focus_first()

    def close_popups(self) -> bool:
        return self.condition.close_popup() or self.value.close_popup()

    def apply_chrome(self, chrome: FormChrome) -> None:
        paint(self, chrome)

    def _changed(self) -> None:
        if not self._busy_flag:
            self._on_change()
