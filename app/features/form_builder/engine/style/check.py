"""The check of a style sheet (UX-STYLE-004, D11). Qt-free.

Two layers. The engine layer is ``parse_sheet``: the shape of the text, with
a line and a place for each finding. The Qt layer is a verdict the caller
brings (``qtside/style/probe.py`` sets the text on a hidden widget and reports
whether Qt could read it). Qt's verdict is final in both directions:

* Qt cannot read the sheet and the engine found no error: "Qt can't read this
  style sheet." with no line.
* Qt reads the sheet and the engine found an error: the sheet applies, so the
  finding is shown as a warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.style.sheet import ERROR, WARNING, Problem, Sheet, parse_sheet

OK = "ok"
LOOKS_RIGHT = "Looks right"
QT_CANT_READ = "Qt can't read this style sheet."


@dataclass(frozen=True)
class Check:
    """``status`` is ``ok``, ``warning`` (the sheet applies) or ``error`` (it does not).

    ``message`` is the sentence on screen. ``line`` and ``column`` are where a
    click on the status puts the caret (0 when the finding has no place).
    """

    status: str
    message: str
    line: int
    column: int
    problems: Tuple[Problem, ...]
    sheet: Sheet

    @property
    def applies(self) -> bool:
        """True when Qt will use the text, so the canvas may take it."""
        return self.status != ERROR


def check_sheet(text: str, qt_readable: Optional[bool] = None) -> Check:
    sheet = parse_sheet(text)
    problems = list(sheet.problems)
    if qt_readable is True:
        problems = [
            Problem(WARNING, found.kind, found.line, found.column, found.text, found.word) if found.severity == ERROR else found
            for found in problems
        ]
    errors = [found for found in problems if found.severity == ERROR]
    if errors:
        first = errors[0]
        return Check(ERROR, first.sentence, first.line, first.column, tuple(problems), sheet)
    if qt_readable is False:
        return Check(ERROR, QT_CANT_READ, 0, 0, tuple(problems), sheet)
    if problems:
        first = problems[0]
        return Check(WARNING, first.sentence, first.line, first.column, tuple(problems), sheet)
    return Check(OK, LOOKS_RIGHT, 0, 0, (), sheet)
