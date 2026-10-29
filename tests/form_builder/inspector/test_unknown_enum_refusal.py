# pyright: reportAttributeAccessIssue=false
"""An enum name this Qt does not know is saved, and the canvas says it cannot show it (UX-PED-009)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ui4.values import EnumValue
from tests.form_builder.inspector.test_scalar_editors import _FORM, _close, _note, _pane, _row, _select, _xml
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_NOTE = "Saved in the file. The canvas can't show this value."
_LOADED = form(
    'class="QWidget" name="Form"',
    """
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="email">
    <property name="echoMode"><enum>QLineEdit::SomeFutureMode</enum></property>
   </widget></item>
  </layout>
""",
)


def test_an_unknown_enum_in_the_file_is_refused_at_first_build() -> None:
    with opened(_LOADED) as (session, realizer):
        email = session.document.by_name("email")[0]
        assert realizer.refused(email, "echoMode")
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            assert _NOTE in _note(_row(pane, "echoMode"))
        finally:
            _close(window, pane)


def test_an_unknown_enum_set_later_is_refused_and_a_known_one_clears_it() -> None:
    with opened(_FORM) as (session, realizer):
        email = session.document.by_name("email")[0]
        assert realizer.refused(email, "echoMode") is None
        session.log.execute(SetProperty(email, "echoMode", EnumValue("QLineEdit::SomeFutureMode")))
        assert "SomeFutureMode" in _xml(session)
        assert realizer.refused(email, "echoMode")
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "email")
            assert _NOTE in _note(_row(pane, "echoMode"))
        finally:
            _close(window, pane)
        session.log.execute(SetProperty(email, "echoMode", EnumValue("QLineEdit::Password")))
        assert realizer.refused(email, "echoMode") is None
