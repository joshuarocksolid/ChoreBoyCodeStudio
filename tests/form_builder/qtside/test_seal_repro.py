# pyright: reportAttributeAccessIssue=false
"""Repro (M3.7c review): realizing a form restyles every widget in the app.

`theme.runtime._finish_reseal` clears and re-installs the application style
sheet one turn after each `Realizer.build`. Qt then re-polishes every live
widget, the shell included (~450 ms CPU per build with an idle MainWindow at
load ~70). Building a form must not touch widgets outside the form.
"""

from __future__ import annotations

from typing import List

import pytest

from app.qt.QtCore import QEvent, QObject
from app.qt.QtWidgets import QApplication, QLabel, QSpinBox, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.unit

_SHEET = "QToolTip { color: #101010; background: #f0f0f0; }"
_TEXT = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QSpinBox" name="first"/></item>
  </layout>
""",
)


class _Counter(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.seen: List[int] = []

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.Polish):
            self.seen.append(int(event.type()))
        return False


def _turn(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def test_building_a_form_does_not_restyle_widgets_outside_it() -> None:
    app = QApplication.instance() or QApplication([])
    saved = app.styleSheet()
    app.setStyleSheet(_SHEET)
    shell = QWidget()
    column = QVBoxLayout(shell)
    bystanders = [QLabel("shell"), QSpinBox()]
    for widget in bystanders:
        column.addWidget(widget)
    shell.show()
    _turn(app)
    counter = _Counter()
    for widget in bystanders:
        widget.installEventFilter(counter)
    try:
        with opened(_TEXT) as (_session, _realizer):
            _turn(app)
        assert counter.seen == [], "shell widgets were re-polished %d times" % len(counter.seen)
    finally:
        for widget in bystanders:
            widget.removeEventFilter(counter)
        shell.deleteLater()
        app.setStyleSheet(saved)
