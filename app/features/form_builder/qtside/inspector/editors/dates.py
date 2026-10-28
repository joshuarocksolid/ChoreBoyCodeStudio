"""Date, time and date-time fields in the project locale, with a calendar popover."""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.project.table_form import four_digit_year_format
from app.features.form_builder.engine.ui4.values import DateTimeValue, DateValue, TimeValue, Value
from app.features.form_builder.qtside.inspector.api import (
    MIXED_TEXT,
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import change_label, name_part, payload
from app.features.form_builder.qtside.inspector.editors._number_box import IntBox, _SpinHooks
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover
from app.qt.QtCore import QDate, QDateTime, QLocale, QTime, Qt
from app.qt.QtWidgets import QCalendarWidget, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

_DATE_REFUSAL = "Use a date like 10/28/2026."
_TIME_REFUSAL = "Use a time like 2:30 PM."
_STACK = 300


def _short_date() -> str:
    short = QLocale().dateFormat(getattr(getattr(QLocale, "FormatType", QLocale), "ShortFormat"))
    return four_digit_year_format(str(short))


def _time_format(*, seconds: bool) -> str:
    short = str(QLocale().timeFormat(getattr(getattr(QLocale, "FormatType", QLocale), "ShortFormat")))
    if not seconds:
        return short.replace(":ss", "").replace(" ss", "")
    if "ss" in short:
        return short
    if "AP" in short or "ap" in short:
        return short.replace("AP", ":ss AP").replace("ap", ":ss ap")
    return short + ":ss"


class _Calendar(QCalendarWidget):
    def __init__(self, parent: QWidget, on_pick) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._on_pick = on_pick
        self.setProperty("fbEnterStays", True)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        keys = getattr(Qt, "Key", Qt)
        if key in (getattr(keys, "Key_Return"), getattr(keys, "Key_Enter")):
            self._on_pick()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class _DateLine(QLineEdit):
    def __init__(self, parent: QWidget, on_alt_down) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._on_alt_down = on_alt_down

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = event.key()  # type: ignore[attr-defined]
        mods = event.modifiers()  # type: ignore[attr-defined]
        keys = getattr(Qt, "Key", Qt)
        alt = bool(mods & getattr(getattr(Qt, "KeyboardModifier", Qt), "AltModifier"))
        if alt and key == getattr(keys, "Key_Down"):
            self._on_alt_down()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class DateEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        self._spec = spec
        self._host = host
        self._shown = ""
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._edit = _DateLine(self._root, self._open)
        self._edit.editingFinished.connect(self._commit_line)
        layout.addWidget(self._edit, 1)
        self._open_button = QPushButton("▾", self._root)
        self._open_button.setAutoDefault(False)
        self._open_button.clicked.connect(self._open)
        layout.addWidget(self._open_button, 0)
        self._popover: Optional[RowPopover] = None
        self._calendar: Optional[_Calendar] = None
        self._hour: Optional[IntBox] = None
        self._minute: Optional[IntBox] = None
        self._second: Optional[IntBox] = None

    @property
    def widget(self) -> QWidget:
        return self._root

    def wants_stacked(self, width: int) -> bool:
        return self._spec.element == DateTimeValue.ELEMENT and int(width) < _STACK

    def show(self, value: RowValue) -> None:
        mark(self._edit, value)
        name_part(self._edit, self._host, "value")
        self._open_button.setAccessibleName("%s: open calendar" % (self._host.label or "Date"))
        text = "" if isinstance(value, Mixed) else _format(self._spec.element, payload(value))
        self._shown = text
        self._edit.blockSignals(True)
        self._edit.setText(text)
        self._edit.setPlaceholderText(MIXED_TEXT if isinstance(value, Mixed) else "")
        self._edit.blockSignals(False)

    def is_dirty(self) -> bool:
        return self._edit.text() != self._shown

    def _commit_line(self) -> None:
        text = self._edit.text().strip()
        if text == self._shown.strip():
            return
        parsed = _parse(self._spec.element, text)
        if parsed is None:
            self._host.invalid(_refusal(self._spec.element))
            return
        self._host.commit(parsed)

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        current = _parse(self._spec.element, self._edit.text().strip()) or _today(self._spec.element)
        popover = RowPopover(
            self._host.row_widget,
            self._host,
            row_label=self._host.label or "Date",
            session_label=change_label(self._host.label),
            qt_name=self._host.qt_name,
            anchor=self._open_button,
        )
        self._popover = popover
        body = popover.body()
        if self._spec.element != TimeValue.ELEMENT:
            self._calendar = _Calendar(popover, self._pick_date)
            when = _qdate(current)
            if when is not None:
                self._calendar.setSelectedDate(when)
            body.addWidget(self._calendar)
        if self._spec.element != DateValue.ELEMENT:
            hooks = _SpinHooks(lambda _n: self._commit_time(), self._host.invalid, lambda: None, lambda: None)
            self._hour = IntBox(0, 23, popover, hooks)
            self._minute = IntBox(0, 59, popover, hooks)
            self._second = IntBox(0, 59, popover, hooks)
            hour, minute, second = _clock(current)
            self._hour.show_number(hour, can_reset=False)
            self._minute.show_number(minute, can_reset=False)
            self._second.show_number(second, can_reset=False)
            row = QWidget(popover)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(QLabel("Hour", row))
            layout.addWidget(self._hour, 1)
            layout.addWidget(QLabel("Minute", row))
            layout.addWidget(self._minute, 1)
            layout.addWidget(QLabel("Second", row))
            layout.addWidget(self._second, 1)
            body.addWidget(row)
            name_part(self._hour, self._host, "hour")
            name_part(self._minute, self._host, "minute")
            name_part(self._second, self._host, "second")
        popover.open_popover()

    def _pick_date(self) -> None:
        if self._calendar is None or self._popover is None:
            return
        date = self._calendar.selectedDate()
        value = _with_date(self._spec.element, date.year(), date.month(), date.day(), self._clock_now())
        self._host.commit(value, session=self._popover.session)
        self._shown = _format(self._spec.element, value)
        self._edit.setText(self._shown)
        self._popover.done()

    def _commit_time(self) -> None:
        if self._popover is None or self._hour is None or self._minute is None or self._second is None:
            return
        base = _parse(self._spec.element, self._edit.text().strip()) or _today(self._spec.element)
        value = _with_clock(
            self._spec.element,
            base,
            int(self._hour.value()),
            int(self._minute.value()),
            int(self._second.value()),
        )
        self._host.commit(value, session=self._popover.session)
        self._shown = _format(self._spec.element, value)
        self._edit.setText(self._shown)

    def _clock_now(self) -> Tuple[int, int, int]:
        if self._hour is None or self._minute is None or self._second is None:
            found = _parse(self._spec.element, self._edit.text().strip()) or _today(self._spec.element)
            return _clock(found)
        return (int(self._hour.value()), int(self._minute.value()), int(self._second.value()))


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(DateValue.ELEMENT), DateEditor)
    registrar.editor(EditorKey(TimeValue.ELEMENT), DateEditor)
    registrar.editor(EditorKey(DateTimeValue.ELEMENT), DateEditor)


def _refusal(element: str) -> str:
    if element == TimeValue.ELEMENT:
        return _TIME_REFUSAL
    return _DATE_REFUSAL


def _format(element: str, value: Optional[Value]) -> str:
    if isinstance(value, DateValue):
        date = QDate(value.year, value.month, value.day)
        return str(QLocale().toString(date, _short_date()))
    if isinstance(value, TimeValue):
        time = QTime(value.hour, value.minute, value.second)
        return str(QLocale().toString(time, _time_format(seconds=value.second != 0)))
    if isinstance(value, DateTimeValue):
        when = QDateTime(QDate(value.year, value.month, value.day), QTime(value.hour, value.minute, value.second))
        pattern = _short_date() + " " + _time_format(seconds=value.second != 0)
        return str(QLocale().toString(when, pattern))
    return ""


def _parse(element: str, text: str) -> Optional[Value]:
    if not text:
        return None
    if element == TimeValue.ELEMENT:
        return _parse_time(text)
    if element == DateValue.ELEMENT:
        date = _parse_date(text)
        if date is None:
            return None
        return DateValue(date[0], date[1], date[2])
    parts = text.split()
    if len(parts) < 2:
        return None
    # The time may contain a space before AM/PM.
    date = _parse_date(parts[0])
    if date is None:
        return None
    clock = _parse_time(" ".join(parts[1:]))
    if not isinstance(clock, TimeValue):
        return None
    return DateTimeValue(clock.hour, clock.minute, clock.second, date[0], date[1], date[2])


def _parse_date(text: str) -> Optional[Tuple[int, int, int]]:
    locale = QLocale()
    for pattern in (_short_date(), "M/d/yyyy", "MM/dd/yyyy", "yyyy-MM-dd"):
        date = locale.toDate(text, pattern)
        if date.isValid():
            return (date.year(), date.month(), date.day())
    return None


def _parse_time(text: str) -> Optional[TimeValue]:
    locale = QLocale()
    for pattern in (
        _time_format(seconds=True),
        _time_format(seconds=False),
        "h:mm:ss AP",
        "h:mm AP",
        "HH:mm:ss",
        "HH:mm",
    ):
        time = locale.toTime(text, pattern)
        if time.isValid():
            return TimeValue(time.hour(), time.minute(), time.second())
    return None


def _today(element: str) -> Value:
    now = QDateTime.currentDateTime()
    if element == TimeValue.ELEMENT:
        return TimeValue(now.time().hour(), now.time().minute(), now.time().second())
    if element == DateValue.ELEMENT:
        return DateValue(now.date().year(), now.date().month(), now.date().day())
    return DateTimeValue(
        now.time().hour(),
        now.time().minute(),
        now.time().second(),
        now.date().year(),
        now.date().month(),
        now.date().day(),
    )


def _qdate(value: Value) -> Optional[QDate]:
    if isinstance(value, DateValue):
        return QDate(value.year, value.month, value.day)
    if isinstance(value, DateTimeValue):
        return QDate(value.year, value.month, value.day)
    return None


def _clock(value: Value) -> Tuple[int, int, int]:
    if isinstance(value, (TimeValue, DateTimeValue)):
        return (value.hour, value.minute, value.second)
    return (0, 0, 0)


def _with_date(element: str, year: int, month: int, day: int, clock: Tuple[int, int, int]) -> Value:
    if element == DateValue.ELEMENT:
        return DateValue(year, month, day)
    return DateTimeValue(clock[0], clock[1], clock[2], year, month, day)


def _with_clock(element: str, base: Value, hour: int, minute: int, second: int) -> Value:
    if element == TimeValue.ELEMENT:
        return TimeValue(hour, minute, second)
    if isinstance(base, DateTimeValue):
        return DateTimeValue(hour, minute, second, base.year, base.month, base.day)
    if isinstance(base, DateValue):
        return DateTimeValue(hour, minute, second, base.year, base.month, base.day)
    today = _today(DateTimeValue.ELEMENT)
    assert isinstance(today, DateTimeValue)
    return DateTimeValue(hour, minute, second, today.year, today.month, today.day)
