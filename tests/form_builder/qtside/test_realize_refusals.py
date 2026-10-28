# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""The realizer restores enum and flag defaults, and reports values Qt refuses (UX-PED-009)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog import DeleteNodes, SetProperty
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.qt.QtCore import Qt
from app.qt.QtWidgets import QDockWidget, QLineEdit, QSpinBox
from tests.form_builder.qtside.support import form, opened

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

FORM = form(
    'class="QWidget" name="Form"',
    """
  <widget class="QLineEdit" name="secret">
   <property name="echoMode"><enum>QLineEdit::Password</enum></property>
  </widget>
  <widget class="QDockWidget" name="dock">
   <property name="allowedAreas"><set>Qt::LeftDockWidgetArea</set></property>
   <widget class="QWidget" name="dockContents"/>
  </widget>
  <widget class="QSpinBox" name="count"/>
""",
)


def test_clearing_an_enum_or_flag_property_restores_the_qt_default_on_the_canvas() -> None:
    with opened(FORM) as (session, realizer):
        secret = session.document.by_name("secret")[0]
        dock = session.document.by_name("dock")[0]
        line = realizer.widget_for(secret)
        panel = realizer.widget_for(dock)
        assert isinstance(line, QLineEdit) and isinstance(panel, QDockWidget)
        assert line.echoMode() == QLineEdit.EchoMode.Password
        session.log.execute(SetProperty(secret, "echoMode", None))
        session.log.execute(SetProperty(dock, "allowedAreas", None))
        assert line.echoMode() == QLineEdit.EchoMode.Normal
        assert panel.allowedAreas() == Qt.DockWidgetArea.AllDockWidgetAreas
        assert realizer.refused(secret, "echoMode") is None


def test_a_value_qt_refuses_is_reported_until_it_is_applied_or_the_widget_goes() -> None:
    with opened(FORM) as (session, realizer):
        count = session.document.by_name("count")[0]
        spin = realizer.widget_for(count)
        assert isinstance(spin, QSpinBox)
        assert realizer.refused(count, "minimum") is None
        session.log.execute(SetProperty(count, "minimum", StringValue("lots")))
        assert realizer.refused(count, "minimum")
        session.log.execute(SetProperty(count, "minimum", NumberValue(3)))
        assert realizer.refused(count, "minimum") is None
        assert spin.minimum() == 3
        session.log.execute(SetProperty(count, "minimum", StringValue("lots")))
        assert realizer.refused(count, "minimum")
        session.log.execute(DeleteNodes((count,)))
        assert realizer.refused(count, "minimum") is None
