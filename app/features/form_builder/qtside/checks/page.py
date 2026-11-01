"""The add-check page. It lives in the Checks section, under the add button."""

from __future__ import annotations

from typing import List, Optional, Tuple, Union

from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.logic.checks import (
    Bound,
    Check,
    FormulaCheck,
    Length,
    OneOf,
    Pattern,
    Preset,
    Range,
    Required,
)
from app.features.form_builder.engine.logic.formula.env import SlotKind
from app.features.form_builder.engine.logic.formula.types import TEXT
from app.features.form_builder.qtside.checks.catalog import (
    bound_target,
    generated_message,
    kind_of,
)
from app.features.form_builder.qtside.formula import FormulaEditor
from app.features.form_builder.qtside.theme.chrome import FormChrome

_ENTER = frozenset({enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)})
_ESC = enum_value(Qt.Key.Key_Escape)
_CTRL = enum_value(Qt.KeyboardModifier.ControlModifier)
_KEY_PRESS = enum_value(getattr(getattr(QEvent, "Type", QEvent), "KeyPress"))
_FIELD_WORDS = ("Message", "Minimum", "Maximum", "Pattern", "Values", "Formula")
_MESSAGE_KINDS = frozenset({"required", "email", "phone", "zip", "length", "pattern", "one_of", "range"})


def _parse_int(text: str) -> Tuple[bool, Optional[int]]:
    stripped = text.strip()
    if not stripped:
        return True, None
    try:
        return True, int(stripped)
    except ValueError:
        return False, None


def _parse_number(text: str) -> Optional[Union[int, float]]:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        if any(ch in stripped for ch in ".eE"):
            return float(stripped)
        return int(stripped)
    except ValueError:
        return None


def _label_width(widget: QWidget) -> int:
    metrics = widget.fontMetrics()
    widest = 0
    for word in _FIELD_WORDS:
        widest = max(widest, int(metrics.horizontalAdvance(word)))
    return widest + 12


class _Keys(QObject):
    """Ctrl+Enter commits and Esc cancels from a line edit. The formula editor does its own."""

    def __init__(self, page: "CheckPage") -> None:
        super().__init__(page)
        self._page = page

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        del watched
        if enum_value(event.type()) != _KEY_PRESS:
            return False
        key = enum_value(event.key())  # type: ignore[attr-defined]
        mods = enum_value(event.modifiers())  # type: ignore[attr-defined]
        if key == _ESC:
            self._page.cancel()
            event.accept()  # type: ignore[attr-defined]
            return True
        if key in _ENTER and bool(mods & _CTRL):
            self._page.commit()
            event.accept()  # type: ignore[attr-defined]
            return True
        return False


class _BoundSide(QWidget):
    """A Between side: a number, or a formula when the text is not a number."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self._line = QLineEdit(self)
        self._line.setMinimumWidth(0)
        self._editor: Optional[FormulaEditor] = None
        self._formula = False
        self._env = None
        self._slot = SlotKind.range_bound(TEXT)
        self._reader = None
        self._chrome: Optional[FormChrome] = None
        self._on_commit = None
        self._on_cancel = None
        self._on_change = None
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._line)
        self._line.textChanged.connect(self._line_changed)

    def set_name(self, name: str) -> None:
        self._line.setObjectName(name)

    def arm(self) -> None:
        self._line.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        editor = self._editor
        if editor is not None:
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def focus_line(self) -> None:
        self.arm()
        if self._formula and self._editor is not None:
            self._editor.setFocus()
            return
        self._line.setFocus()

    def set_context(
        self,
        env: object,
        slot: SlotKind,
        reader: object,
        chrome: Optional[FormChrome],
        on_change: object,
        on_commit: object,
        on_cancel: object,
    ) -> None:
        self._env = env
        self._slot = slot
        self._reader = reader
        self._chrome = chrome
        self._on_change = on_change
        self._on_commit = on_commit
        self._on_cancel = on_cancel
        if self._editor is not None and env is not None:
            self._editor.set_context(env, slot, reader)  # type: ignore[arg-type]
            if chrome is not None:
                self._editor.set_chrome(chrome)

    def show_bound(self, bound: Optional[Bound]) -> None:
        if bound is not None and bound.formula is not None:
            self._show_formula(bound.formula)
            return
        text = "" if bound is None or bound.number is None else str(bound.number)
        self._show_line(text)

    def value(self) -> Optional[Bound]:
        if self._formula and self._editor is not None:
            text = self._editor.toPlainText().strip()
            if not text:
                return None
            return Bound(formula=text)
        text = self._line.text().strip()
        if not text:
            return None
        number = _parse_number(text)
        if number is None:
            return Bound(formula=text)
        return Bound(number=number)

    def has_error(self) -> bool:
        if self._formula and self._editor is not None and self._editor.toPlainText().strip():
            return self._editor.has_error()
        return False

    def _line_changed(self, text: str) -> None:
        stripped = text.strip()
        if stripped and _parse_number(stripped) is None:
            self._show_formula(text)
            return
        if callable(self._on_change):
            self._on_change()

    def _show_line(self, text: str) -> None:
        self._formula = False
        if self._editor is not None:
            self._editor.hide()
        self._line.show()
        self._line.blockSignals(True)
        self._line.setText(text)
        self._line.blockSignals(False)

    def _show_formula(self, text: str) -> None:
        editor = self._ensure_editor()
        self._formula = True
        self._line.hide()
        editor.show()
        editor.show_text(text)
        editor.setFocus()
        if callable(self._on_change):
            self._on_change()

    def _ensure_editor(self) -> FormulaEditor:
        found = self._editor
        if found is not None:
            return found
        editor = FormulaEditor(self)
        editor.set_handlers(self._commit, self._cancel)
        editor.textChanged.connect(self._edited)
        if self._chrome is not None:
            editor.set_chrome(self._chrome)
        if self._env is not None:
            editor.set_context(self._env, self._slot, self._reader)  # type: ignore[arg-type]
        self.layout().addWidget(editor)  # type: ignore[union-attr]
        self._editor = editor
        return editor

    def _edited(self) -> None:
        if callable(self._on_change):
            self._on_change()

    def _commit(self) -> None:
        if callable(self._on_commit):
            self._on_commit()

    def _cancel(self) -> None:
        if callable(self._on_cancel):
            self._on_cancel()


class CheckPage(QWidget):
    """One check. Commit stores it; Cancel writes nothing."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.checks.page")
        self.setMinimumWidth(0)
        names = getattr(QSizePolicy, "Policy", QSizePolicy)
        self.setSizePolicy(getattr(names, "Preferred"), getattr(names, "Minimum"))
        self._keys = _Keys(self)
        self._key = ""
        self._context = None
        self._generated = ""
        self._message_edited = False
        self._filling = False
        self._on_commit = None
        self._on_cancel = None
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(4)
        self._message = self._line("formBuilder.checks.message")
        self._pattern = self._line("formBuilder.checks.pattern")
        self._values = self._line("formBuilder.checks.values")
        self._min_int = self._line("formBuilder.checks.lengthMin")
        self._max_int = self._line("formBuilder.checks.lengthMax")
        self._min_bound = _BoundSide(self)
        self._max_bound = _BoundSide(self)
        self._formula: Optional[FormulaEditor] = None
        self._field_labels: List[QLabel] = []
        self._message_row = self._row("Message", self._message)
        self._pattern_row = self._row("Pattern", self._pattern)
        self._values_row = self._row("Values", self._values)
        self._min_row = self._row("Minimum", self._min_stack())
        self._max_row = self._row("Maximum", self._max_stack())
        self._formula_row = self._row("Formula", self._formula_host())
        self._commit = QPushButton("Commit", self)
        self._commit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._commit.setObjectName("formBuilder.checks.commit")
        self._commit.setAutoDefault(False)
        self._commit.setDefault(False)
        self._cancel = QPushButton("Cancel", self)
        self._cancel.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._cancel.setObjectName("formBuilder.checks.cancel")
        self._cancel.setAutoDefault(False)
        self._cancel.setDefault(False)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        buttons.addWidget(self._commit)
        buttons.addWidget(self._cancel)
        buttons.addStretch(1)
        for row in (
            self._message_row,
            self._min_row,
            self._max_row,
            self._pattern_row,
            self._values_row,
            self._formula_row,
        ):
            self._column.addWidget(row)
        self._column.addLayout(buttons)
        self._commit.clicked.connect(self.commit)
        self._cancel.clicked.connect(self.cancel)
        self._message.textChanged.connect(self._message_changed)
        self._pattern.textChanged.connect(self._inputs_changed)
        self._values.textChanged.connect(self._inputs_changed)
        self._min_int.textChanged.connect(self._inputs_changed)
        self._max_int.textChanged.connect(self._inputs_changed)
        self._min_bound.set_context(None, SlotKind.range_bound(TEXT), None, None, self._inputs_changed, self.commit, self.cancel)
        self._max_bound.set_context(None, SlotKind.range_bound(TEXT), None, None, self._inputs_changed, self.commit, self.cancel)
        self._sync_labels()
        self.hide()

    def set_handlers(self, on_commit: object, on_cancel: object) -> None:
        self._on_commit = on_commit
        self._on_cancel = on_cancel

    def set_chrome(self, chrome: FormChrome) -> None:
        if chrome.text and chrome.input:
            width = chrome.focus_width or 1
            self.setStyleSheet(
                "QLineEdit { color: %s; background: %s; border: 1px solid %s; }"
                "QLineEdit:focus { border: %dpx solid %s; }"
                % (chrome.text, chrome.input, chrome.border, width, chrome.accent or chrome.border)
            )
        slot = self._slot()
        self._min_bound.set_context(
            self._env(), slot, self._reader(), chrome, self._inputs_changed, self.commit, self.cancel
        )
        self._max_bound.set_context(
            self._env(), slot, self._reader(), chrome, self._inputs_changed, self.commit, self.cancel
        )
        editor = self._formula
        if editor is not None:
            editor.set_chrome(chrome)

    def show_new(self, key: str, context: object) -> None:
        self._open(key, context, None)

    def show_edit(self, check: Check, context: object) -> None:
        self._open(kind_of(check), context, check)

    def commit(self) -> None:
        if not self._commit.isEnabled():
            return
        if callable(self._on_commit):
            self._on_commit()

    def cancel(self) -> None:
        if callable(self._on_cancel):
            self._on_cancel()

    def build(self) -> Optional[Check]:
        """The check the fields describe, or None when Commit is not allowed."""
        if not self._ready():
            return None
        return self._check(self._stored_message())

    def _open(self, key: str, context: object, check: Optional[Check]) -> None:
        self._key = key
        self._context = context
        self._filling = True
        self._message_edited = check is not None and getattr(check, "message", None) is not None
        self._clear()
        self._show_rows(key)
        self._fill(check)
        self._filling = False
        self._apply_context()
        self._refresh()
        self.show()
        self._arm_fields()
        self._focus_first()

    def _clear(self) -> None:
        for line in (self._message, self._pattern, self._values, self._min_int, self._max_int):
            line.clear()
        self._min_bound.show_bound(None)
        self._max_bound.show_bound(None)
        if self._formula is not None:
            self._formula.show_text("")

    def _show_rows(self, key: str) -> None:
        self._message_row.setVisible(key in _MESSAGE_KINDS or key == "formula")
        self._min_row.setVisible(key in ("range", "length"))
        self._max_row.setVisible(key in ("range", "length"))
        self._pattern_row.setVisible(key == "pattern")
        self._values_row.setVisible(key == "one_of")
        self._formula_row.setVisible(key == "formula")
        between = key == "range"
        self._min_bound.setVisible(between)
        self._max_bound.setVisible(between)
        self._min_int.setVisible(key == "length")
        self._max_int.setVisible(key == "length")
        if between:
            self._min_bound.set_name("formBuilder.checks.min")
            self._max_bound.set_name("formBuilder.checks.max")
            self._min_int.setObjectName("formBuilder.checks.lengthMin")
            self._max_int.setObjectName("formBuilder.checks.lengthMax")
        else:
            self._min_bound.set_name("formBuilder.checks.boundMin")
            self._max_bound.set_name("formBuilder.checks.boundMax")
            self._min_int.setObjectName("formBuilder.checks.min")
            self._max_int.setObjectName("formBuilder.checks.max")

    def _fill(self, check: Optional[Check]) -> None:
        if check is None:
            return
        if isinstance(check, (Required, Preset, Pattern, OneOf, FormulaCheck, Length, Range)):
            if check.message:
                self._message.setText(check.message)
        if isinstance(check, Pattern):
            self._pattern.setText(check.pattern)
        elif isinstance(check, OneOf):
            self._values.setText(", ".join(str(value) for value in check.values))
        elif isinstance(check, Length):
            if check.min is not None:
                self._min_int.setText(str(check.min))
            if check.max is not None:
                self._max_int.setText(str(check.max))
        elif isinstance(check, Range):
            self._min_bound.show_bound(check.min)
            self._max_bound.show_bound(check.max)
        elif isinstance(check, FormulaCheck):
            self._ensure_formula().show_text(check.formula)

    def _apply_context(self) -> None:
        slot = self._slot()
        chrome = self._chrome()
        self._min_bound.set_context(
            self._env(), slot, self._reader(), chrome, self._inputs_changed, self.commit, self.cancel
        )
        self._max_bound.set_context(
            self._env(), slot, self._reader(), chrome, self._inputs_changed, self.commit, self.cancel
        )
        editor = self._formula
        if editor is not None and self._env() is not None:
            editor.set_context(self._env(), SlotKind.check(), self._reader())  # type: ignore[arg-type]
            if chrome is not None:
                editor.set_chrome(chrome)

    def _arm_fields(self) -> None:
        policy = Qt.FocusPolicy.StrongFocus
        for widget in (
            self._commit,
            self._cancel,
            self._message,
            self._pattern,
            self._values,
            self._min_int,
            self._max_int,
        ):
            widget.setFocusPolicy(policy)
        self._min_bound.arm()
        self._max_bound.arm()
        editor = self._formula
        if editor is not None:
            editor.setFocusPolicy(policy)

    def _focus_first(self) -> None:
        if self._key == "range":
            self._min_bound.focus_line()
            return
        if self._key == "length":
            self._min_int.setFocus()
            return
        if self._key == "pattern":
            self._pattern.setFocus()
            return
        if self._key == "one_of":
            self._values.setFocus()
            return
        if self._key == "formula":
            self._ensure_formula().setFocus()
            return
        self._message.setFocus()

    def _message_changed(self) -> None:
        if self._filling:
            return
        self._message_edited = True
        self._refresh_commit()

    def _inputs_changed(self) -> None:
        if self._filling:
            return
        self._refresh()

    def _refresh(self) -> None:
        probe = self._check(None)
        self._generated = ""
        if probe is not None:
            self._generated = generated_message(
                self._class_name(),
                probe,
                self._kind(),
                label=self._label(),
                object_name=self._object_name(),
            )
        if not self._message_edited:
            self._filling = True
            self._message.setText(self._generated)
            self._filling = False
        self._refresh_commit()

    def _refresh_commit(self) -> None:
        self._commit.setEnabled(self._ready())

    def _ready(self) -> bool:
        key = self._key
        message = self._message.text().strip()
        if key in ("required", "email", "phone", "zip"):
            return bool(message)
        if key == "pattern":
            return bool(self._pattern.text().strip()) and bool(message)
        if key == "one_of":
            return bool(self._one_values()) and bool(message)
        if key == "length":
            low_ok, low = _parse_int(self._min_int.text())
            high_ok, high = _parse_int(self._max_int.text())
            return low_ok and high_ok and (low is not None or high is not None)
        if key == "range":
            if self._min_bound.has_error() or self._max_bound.has_error():
                return False
            return self._min_bound.value() is not None or self._max_bound.value() is not None
        if key == "formula":
            editor = self._formula
            text = editor.toPlainText().strip() if editor is not None else ""
            if not text or not message:
                return False
            return editor is not None and not editor.has_error()
        return False

    def _stored_message(self) -> Optional[str]:
        text = self._message.text()
        if text == self._generated:
            return None
        stripped = text.strip()
        return stripped if stripped else None

    def _check(self, message: Optional[str]) -> Optional[Check]:
        key = self._key
        if key == "required":
            return Required(message)
        if key == "email":
            return Preset("email", message)
        if key == "phone":
            return Preset("phone", message)
        if key == "zip":
            return Preset("zip", message)
        if key == "pattern":
            return Pattern(self._pattern.text(), message)
        if key == "one_of":
            values = self._one_values()
            if message is None and not values:
                return None
            return OneOf(values, message)
        if key == "length":
            low_ok, low = _parse_int(self._min_int.text())
            high_ok, high = _parse_int(self._max_int.text())
            if not low_ok or not high_ok:
                return None
            return Length(low, high, message)
        if key == "range":
            return Range(self._min_bound.value(), self._max_bound.value(), message)
        if key == "formula":
            editor = self._formula
            text = editor.toPlainText() if editor is not None else ""
            return FormulaCheck(text.strip(), message)
        return None

    def _one_values(self) -> Tuple[Union[str, int, float], ...]:
        found = []
        for part in self._values.text().split(","):
            token = part.strip()
            if not token:
                continue
            number = _parse_number(token)
            found.append(token if number is None else number)
        return tuple(found)

    def _line(self, name: str) -> QLineEdit:
        line = QLineEdit(self)
        line.setObjectName(name)
        line.setMinimumWidth(0)
        line.installEventFilter(self._keys)
        return line

    def _row(self, words: str, field: QWidget) -> QWidget:
        row = QWidget(self)
        row.setMinimumWidth(0)
        host = QWidget(row)
        host.setMinimumWidth(0)
        if isinstance(field, QLineEdit):
            host.setFixedHeight(24)
        line = QHBoxLayout(host)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(8)
        label = QLabel(words, host)
        label.setMinimumWidth(0)
        line.addWidget(label)
        line.addWidget(field, 1)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(host)
        self._field_labels.append(label)
        return row

    def _min_stack(self) -> QWidget:
        host = QWidget(self)
        host.setMinimumWidth(0)
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._min_int)
        column.addWidget(self._min_bound)
        return host

    def _max_stack(self) -> QWidget:
        host = QWidget(self)
        host.setMinimumWidth(0)
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._max_int)
        column.addWidget(self._max_bound)
        return host

    def _formula_host(self) -> QWidget:
        host = QWidget(self)
        host.setObjectName("formBuilder.checks.formulaHost")
        host.setMinimumWidth(0)
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        return host

    def _ensure_formula(self) -> FormulaEditor:
        found = self._formula
        if found is not None:
            return found
        editor = FormulaEditor(self._formula_row)
        editor.set_handlers(self.commit, self.cancel)
        editor.textChanged.connect(self._inputs_changed)
        chrome = self._chrome()
        if chrome is not None:
            editor.set_chrome(chrome)
        if self._env() is not None:
            editor.set_context(self._env(), SlotKind.check(), self._reader())  # type: ignore[arg-type]
        host = self._formula_row.findChild(QWidget, "formBuilder.checks.formulaHost")
        if host is not None and host.layout() is not None:
            host.layout().addWidget(editor)
        self._formula = editor
        return editor

    def _sync_labels(self) -> None:
        width = _label_width(self)
        for label in self._field_labels:
            label.setFixedWidth(width)

    def _slot(self) -> SlotKind:
        return SlotKind.range_bound(bound_target(self._class_name(), self._kind()))

    def _class_name(self) -> str:
        return str(getattr(self._context, "class_name", "") or "")

    def _kind(self) -> str:
        return str(getattr(self._context, "kind", "") or "")

    def _label(self) -> str:
        return str(getattr(self._context, "label", "") or "")

    def _object_name(self) -> str:
        return str(getattr(self._context, "object_name", "") or "")

    def _env(self) -> object:
        return getattr(self._context, "env", None)

    def _reader(self) -> object:
        return getattr(self._context, "reader", None)

    def _chrome(self) -> Optional[FormChrome]:
        chrome = getattr(self._context, "chrome", None)
        if isinstance(chrome, FormChrome):
            return chrome
        return None
