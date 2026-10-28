"""Spin fields that refuse a bad number instead of clamping it.

Up and Down step by one. Shift or Page steps by ten. A value the field cannot
turn into a number stays on screen and the editor reports it.
"""

from __future__ import annotations

from typing import Callable, Optional, Union

from app.features.form_builder.qtside.inspector.editors._editor_kit import (
    MINUS,
    project_locale,
    qt_align,
    qt_key,
    qt_mod,
    yield_form_undo,
)
from app.qt.QtGui import QValidator
from app.qt.QtWidgets import QDoubleSpinBox, QLineEdit, QSpinBox, QWidget

NumberCallback = Callable[[Union[int, float]], None]
TextCallback = Callable[[str], None]
CloseCallback = Callable[[], None]

_INT32 = (-2147483648, 2147483647)
_PAGE = (
    qt_key("Key_PageUp"),
    qt_key("Key_PageDown"),
    qt_key("Key_Up"),
    qt_key("Key_Down"),
)


def format_int(number: int) -> str:
    text = str(int(number))
    if text.startswith("-"):
        return MINUS + text[1:]
    return text


def parse_int(text: str) -> Optional[int]:
    raw = text.strip().replace(MINUS, "-").replace(",", "").replace(" ", "").replace("\u202f", "")
    if not raw or raw == "-":
        return None
    if any(mark in raw for mark in (".", "e", "E")):
        return None
    try:
        return int(raw, 10)
    except ValueError:
        return None


def format_real(number: float, places: int, *, strip: bool) -> str:
    text = "%.*f" % (places, float(number))
    if strip and "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-", "-0"):
        text = "0"
    mark = str(project_locale().decimalPoint())
    if mark != ".":
        text = text.replace(".", mark)
    if text.startswith("-"):
        text = MINUS + text[1:]
    return text


def parse_real(text: str) -> Optional[float]:
    raw = text.strip().replace(MINUS, "-").replace(" ", "").replace("\u202f", "")
    mark = str(project_locale().decimalPoint())
    if mark != ".":
        raw = raw.replace(mark, ".")
    raw = raw.replace(",", "")
    if not raw or raw in ("-", ".", "-."):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _tabular(widget: QWidget) -> None:
    font = widget.font()
    setter = getattr(font, "setFeature", None)
    if not callable(setter):
        return
    try:
        setter("tnum", 1)
    except (TypeError, AttributeError, ValueError):
        return
    widget.setFont(font)


def _right() -> object:
    return qt_align("AlignRight")


def _acceptable() -> object:
    state = getattr(QValidator, "State", QValidator)
    return getattr(state, "Acceptable")


def _shift(event: object) -> bool:
    mods = event.modifiers()  # type: ignore[attr-defined]
    return bool(mods & qt_mod("ShiftModifier"))


class _SpinHooks:
    def __init__(
        self,
        on_number: NumberCallback,
        on_invalid: TextCallback,
        on_reset: CloseCallback,
        on_close: CloseCallback,
    ) -> None:
        self.on_number = on_number
        self.on_invalid = on_invalid
        self.on_reset = on_reset
        self.on_close = on_close


class IntBox(QSpinBox):
    """An integer spin. ``low`` and ``high`` are the refusal limits, not a clamp."""

    def __init__(
        self,
        low: int,
        high: int,
        parent: QWidget,
        hooks: _SpinHooks,
    ) -> None:
        super().__init__(parent)
        self._low = int(low)
        self._high = int(high)
        self._hooks = hooks
        self._can_reset = True
        self._hold: Optional[str] = None
        self._shown = ""
        self._blank = False
        self.setSingleStep(1)
        self.setKeyboardTracking(False)
        self.setGroupSeparatorShown(False)
        self.setAlignment(_right())  # type: ignore[arg-type]
        self.setRange(_INT32[0], _INT32[1])
        _tabular(self)
        line = self.lineEdit()
        line.setAlignment(_right())  # type: ignore[arg-type]
        yield_form_undo(self)
        yield_form_undo(line)
        self.valueChanged.connect(self._stepped)
        self.editingFinished.connect(self._finished)

    def show_number(self, number: int, *, can_reset: bool) -> None:
        self._can_reset = can_reset
        self._hold = None
        self._blank = False
        shown = int(number)
        low = max(_INT32[0], min(self._low, shown))
        high = min(_INT32[1], max(self._high, shown))
        self.blockSignals(True)
        self.setRange(low, high)
        self.setValue(max(low, min(high, shown)))
        self.lineEdit().setPlaceholderText("")
        self.blockSignals(False)
        self._shown = self.lineEdit().text()

    def show_blank(self, placeholder: str, *, can_reset: bool) -> None:
        self._can_reset = can_reset
        self._hold = None
        self._blank = True
        self.blockSignals(True)
        self.lineEdit().setPlaceholderText(placeholder)
        self.lineEdit().clear()
        self.blockSignals(False)
        self._shown = ""

    def is_blank(self) -> bool:
        """Mixed or no value: the field shows its placeholder, not a number."""
        return self._blank and not self.lineEdit().text().strip()

    def showEvent(self, event: object) -> None:  # noqa: N802
        # A spin box refills its text from value() when it is shown, which
        # turned "Mixed" into the last selection's number.
        super().showEvent(event)  # type: ignore[arg-type]
        if self._blank:
            self.blockSignals(True)
            self.lineEdit().clear()
            self.blockSignals(False)

    def is_dirty(self) -> bool:
        return self.lineEdit().text() != self._shown

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        if key in _PAGE:
            down = key in (qt_key("Key_Down"), qt_key("Key_PageDown"))
            page = key in (qt_key("Key_PageUp"), qt_key("Key_PageDown")) or _shift(event)
            self._hold = None
            self.stepBy(-10 if down and page else -1 if down else 10 if page else 1)
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def validate(self, text: str, pos: int) -> object:  # noqa: N802
        return (_acceptable(), text, pos)

    def fixup(self, text: str) -> str:  # noqa: N802
        return text

    def valueFromText(self, text: str) -> int:  # noqa: N802
        parsed = parse_int(text)
        if parsed is None or parsed < self._low or parsed > self._high:
            self._hold = text
            return int(self.value())
        self._hold = None
        return int(parsed)

    def textFromValue(self, value: int) -> str:  # noqa: N802
        if self._hold is not None:
            return self._hold
        return format_int(int(value))

    def _stepped(self, number: int) -> None:
        self._blank = False
        self._shown = self.lineEdit().text()
        self._hooks.on_number(int(number))

    def _finished(self) -> None:
        text = self.lineEdit().text().strip()
        if text == "":
            if self._can_reset:
                self._hooks.on_reset()
            else:
                self._hooks.on_invalid("Type a number, like 12.")
            self._hooks.on_close()
            return
        if text == self._shown.strip():
            self._hooks.on_close()
            return
        parsed = parse_int(text)
        if parsed is None:
            self._hooks.on_invalid("Type a number, like 12.")
            self._hooks.on_close()
            return
        if parsed < self._low or parsed > self._high:
            self._hooks.on_invalid(
                "Use a number from %s to %s." % (format_int(self._low), format_int(self._high))
            )
            self._hooks.on_close()
            return
        # The typed number equals value(), so the spin sent no valueChanged:
        # a Mixed or empty field typed to the number it last held.
        self._blank = False
        self._shown = self.lineEdit().text()
        self._hooks.on_number(int(parsed))
        self._hooks.on_close()


class RealBox(QDoubleSpinBox):
    """A decimal spin. Trailing zeros drop unless ``strip`` is false."""

    def __init__(
        self,
        parent: QWidget,
        hooks: _SpinHooks,
        *,
        places: int,
        strip: bool,
        low: Optional[float] = None,
        high: Optional[float] = None,
    ) -> None:
        super().__init__(parent)
        self._hooks = hooks
        self._places = places
        self._strip = strip
        self._low = low
        self._high = high
        self._can_reset = True
        self._hold: Optional[str] = None
        self._shown = ""
        self._blank = False
        self.setDecimals(places)
        self.setSingleStep(1)
        self.setKeyboardTracking(False)
        self.setGroupSeparatorShown(False)
        self.setAlignment(_right())  # type: ignore[arg-type]
        self.setRange(-1e12, 1e12)
        self.setLocale(project_locale())
        _tabular(self)
        self.lineEdit().setAlignment(_right())  # type: ignore[arg-type]
        yield_form_undo(self)
        yield_form_undo(self.lineEdit())
        self.valueChanged.connect(self._stepped)
        self.editingFinished.connect(self._finished)

    def show_number(self, number: float, *, can_reset: bool) -> None:
        self._can_reset = can_reset
        self._hold = None
        self._blank = False
        shown = float(number)
        low = -1e12 if shown >= -1e12 else shown
        high = 1e12 if shown <= 1e12 else shown
        self.blockSignals(True)
        self.setRange(low, high)
        self.setValue(shown)
        self.lineEdit().setPlaceholderText("")
        self.blockSignals(False)
        self._shown = self.lineEdit().text()

    def show_blank(self, placeholder: str, *, can_reset: bool) -> None:
        self._can_reset = can_reset
        self._hold = None
        self._blank = True
        self.blockSignals(True)
        self.lineEdit().setPlaceholderText(placeholder)
        self.lineEdit().clear()
        self.blockSignals(False)
        self._shown = ""

    def is_blank(self) -> bool:
        """Mixed or no value: the field shows its placeholder, not a number."""
        return self._blank and not self.lineEdit().text().strip()

    def showEvent(self, event: object) -> None:  # noqa: N802
        # A spin box refills its text from value() when it is shown, which
        # turned "Mixed" into the last selection's number.
        super().showEvent(event)  # type: ignore[arg-type]
        if self._blank:
            self.blockSignals(True)
            self.lineEdit().clear()
            self.blockSignals(False)

    def is_dirty(self) -> bool:
        return self.lineEdit().text() != self._shown

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        if key in _PAGE:
            down = key in (qt_key("Key_Down"), qt_key("Key_PageDown"))
            page = key in (qt_key("Key_PageUp"), qt_key("Key_PageDown")) or _shift(event)
            self._hold = None
            self.stepBy(-10 if down and page else -1 if down else 10 if page else 1)
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def validate(self, text: str, pos: int) -> object:  # noqa: N802
        return (_acceptable(), text, pos)

    def fixup(self, text: str) -> str:  # noqa: N802
        return text

    def valueFromText(self, text: str) -> float:  # noqa: N802
        parsed = parse_real(text)
        if parsed is None or not self._inside(parsed):
            self._hold = text
            return float(self.value())
        self._hold = None
        return float(parsed)

    def textFromValue(self, value: float) -> str:  # noqa: N802
        if self._hold is not None:
            return self._hold
        return format_real(float(value), self._places, strip=self._strip)

    def _inside(self, number: float) -> bool:
        if self._low is not None and number < self._low:
            return False
        if self._high is not None and number > self._high:
            return False
        return True

    def _stepped(self, number: float) -> None:
        self._blank = False
        self._shown = self.lineEdit().text()
        self._hooks.on_number(float(number))

    def _finished(self) -> None:
        text = self.lineEdit().text().strip()
        if text == "":
            if self._can_reset:
                self._hooks.on_reset()
            else:
                self._hooks.on_invalid("Type a number, like 12.")
            self._hooks.on_close()
            return
        if text == self._shown.strip():
            self._hooks.on_close()
            return
        parsed = parse_real(text)
        if parsed is None:
            self._hooks.on_invalid("Type a number, like 12.")
            self._hooks.on_close()
            return
        if not self._inside(parsed):
            self._hooks.on_invalid(
                "Use a number from %s to %s."
                % (
                    format_real(float(self._low or 0), self._places, strip=True),
                    format_real(float(self._high or 0), self._places, strip=True),
                )
            )
            self._hooks.on_close()
            return
        self._blank = False
        self._shown = self.lineEdit().text()
        self._hooks.on_number(float(parsed))
        self._hooks.on_close()


class WideIntBox(QLineEdit):
    """Integers that do not fit in a 32-bit spin (uint above 2**31, 64-bit)."""

    def __init__(
        self,
        low: int,
        high: int,
        parent: QWidget,
        hooks: _SpinHooks,
    ) -> None:
        super().__init__(parent)
        self._low = int(low)
        self._high = int(high)
        self._hooks = hooks
        self._can_reset = True
        self._shown = ""
        self.setAlignment(_right())  # type: ignore[arg-type]
        _tabular(self)
        yield_form_undo(self)
        self.editingFinished.connect(self._finished)

    def show_number(self, number: int, *, can_reset: bool) -> None:
        self._can_reset = can_reset
        self.blockSignals(True)
        self.setPlaceholderText("")
        self.setText(format_int(int(number)))
        self.blockSignals(False)
        self._shown = self.text()

    def show_blank(self, placeholder: str, *, can_reset: bool) -> None:
        self._can_reset = can_reset
        self.blockSignals(True)
        self.setPlaceholderText(placeholder)
        self.clear()
        self.blockSignals(False)
        self._shown = ""

    def is_dirty(self) -> bool:
        return self.text() != self._shown

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        if key in _PAGE:
            down = key in (qt_key("Key_Down"), qt_key("Key_PageDown"))
            page = key in (qt_key("Key_PageUp"), qt_key("Key_PageDown")) or _shift(event)
            delta = -10 if down and page else -1 if down else 10 if page else 1
            parsed = parse_int(self.text())
            if parsed is None:
                event.accept()  # type: ignore[attr-defined]
                return
            nxt = parsed + delta
            if nxt < self._low or nxt > self._high:
                self._hooks.on_invalid(
                    "Use a number from %s to %s." % (format_int(self._low), format_int(self._high))
                )
            else:
                self.setText(format_int(nxt))
                self._shown = self.text()
                self._hooks.on_number(nxt)
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def _finished(self) -> None:
        text = self.text().strip()
        if text == "":
            if self._can_reset:
                self._hooks.on_reset()
            else:
                self._hooks.on_invalid("Type a number, like 12.")
            self._hooks.on_close()
            return
        if text == self._shown.strip():
            self._hooks.on_close()
            return
        parsed = parse_int(text)
        if parsed is None:
            self._hooks.on_invalid("Type a number, like 12.")
            self._hooks.on_close()
            return
        if parsed < self._low or parsed > self._high:
            self._hooks.on_invalid(
                "Use a number from %s to %s." % (format_int(self._low), format_int(self._high))
            )
            self._hooks.on_close()
            return
        self._shown = self.text()
        self._hooks.on_number(parsed)
        self._hooks.on_close()
