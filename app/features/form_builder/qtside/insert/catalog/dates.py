"""UX-CAT-002: Dates and times."""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.qtside.insert.catalog._build import leaf_entry
from app.features.form_builder.qtside.insert.catalog._model import Entry, Registry

CATEGORY = "Dates and times"


def entries() -> Tuple[Entry, ...]:
    return (
        leaf_entry("QDateEdit", "Date edit", "QDateEdit", CATEGORY, "dateEdit",
                   "A date the user types or picks.", ("date", "datepicker", "day"), "date_edit"),
        leaf_entry("QTimeEdit", "Time edit", "QTimeEdit", CATEGORY, "timeEdit",
                   "A time of day.", ("time", "clock"), "time_edit"),
        leaf_entry("QDateTimeEdit", "Date and time edit", "QDateTimeEdit", CATEGORY, "dateTimeEdit",
                   "A date with a time.", ("datetime", "timestamp"), "date_time_edit"),
        leaf_entry("QCalendarWidget", "Calendar", "QCalendarWidget", CATEGORY, "calendarWidget",
                   "A month grid to pick a day.", ("calendar", "month"), "calendar"),
    )


def register(registry: Registry) -> None:
    for entry in entries():
        registry.add(entry)
