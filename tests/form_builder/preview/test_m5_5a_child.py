# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalCall=false, reportIndexIssue=false
"""The preview child's side of Preview options (M5.5a, UX-PREV-001, UX-PREV-004, UX-PREV-005).

An in-process ``ChildSession`` with a recording writer: no process, no pipes. The child
keeps one QApplication, so each test puts the style and font back.
"""

from __future__ import annotations

import uuid
from typing import List

import pytest

from app.features.form_builder.engine.ipc.protocol import (
    Appearance,
    CloseView,
    LoadForm,
    Response,
    SetAppearance,
    ViewClosed,
    encode_frame,
)
from app.features.form_builder.qtside.preview.child.session import ChildSession
from app.qt.QtCore import Qt
from app.qt.QtGui import QFont
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QStyleFactory

pytestmark = [pytest.mark.unit]

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>900</width><height>700</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item><widget class="QLabel" name="titleLabel"><property name="text"><string>Hello</string></property></widget></item>
   <item><widget class="QLineEdit" name="nameEdit"/></item>
  </layout>
 </widget>
</ui>
"""


class _Writer:
    def __init__(self) -> None:
        self.sent: List[object] = []

    def send(self, message: object) -> None:
        self.sent.append(message)

    def responses(self) -> List[Response]:
        return [item for item in self.sent if isinstance(item, Response)]


@pytest.fixture
def session(qapp: QApplication):  # type: ignore[no-untyped-def]
    style = qapp.style().objectName()
    font = QFont(qapp.font())
    writer = _Writer()
    child = ChildSession(writer, qapp)
    yield child, writer
    for view_id in list(child._views):  # noqa: SLF001
        child._views.pop(view_id).widget.deleteLater()  # noqa: SLF001
    qapp.setStyle(QStyleFactory.create(style))
    qapp.setFont(font)
    qapp.removeEventFilter(child._user_close)  # noqa: SLF001


def _send(child: ChildSession, message: object) -> None:
    child._handle_line(encode_frame(message))  # noqa: SLF001


def _load(child: ChildSession, appearance: Appearance, view_id: str = "v1") -> None:
    _send(
        child,
        LoadForm(
            request_id=uuid.uuid4().hex,
            view_id=view_id,
            form_path="/tmp/invoice.ui",
            module_name="ui_preview",
            module_source=None,
            ui_xml=_UI,
            project_root=None,
            sys_path=(),
            appearance=appearance,
            keep_values=False,
            revision=1,
        ),
    )


@pytest.mark.parity("R3-178", "R3-179")
def test_a_screen_profile_sets_the_title_the_font_and_clamps_the_window(session, qapp) -> None:  # type: ignore[no-untyped-def]
    child, writer = session
    appearance = Appearance(
        title="Preview · invoice.ui · Small screen",
        screen_width=1024,
        screen_height=600,
        font_family="Courier",
        font_point_size=17.0,
    )
    _load(child, appearance)
    answer = writer.responses()[-1]
    assert answer.ok, answer.detail
    assert answer.result["title"] == "Preview · invoice.ui · Small screen"
    assert answer.result["size"] == [900, 600]
    view = child._views["v1"].widget  # noqa: SLF001
    assert view.windowTitle() == "Preview · invoice.ui · Small screen"
    qapp.processEvents()
    assert view.font().pointSizeF() == 17.0
    assert "Fusion" in answer.result["styles"]
    # A 200% screen is half as many logical pixels.
    _send(
        child,
        SetAppearance(
            request_id="s1",
            view_id="v1",
            appearance=Appearance(title="Preview · invoice.ui", screen_width=1024, screen_height=600, scale=2.0),
        ),
    )
    assert writer.responses()[-1].result["size"] == [512, 300]
    # Back to a big screen: the form's own size returns.
    _send(
        child,
        SetAppearance(
            request_id="s2", view_id="v1", appearance=Appearance(screen_width=1920, screen_height=1080)
        ),
    )
    assert writer.responses()[-1].result["size"] == [900, 700]


@pytest.mark.parity("R3-178")
def test_set_appearance_changes_the_style_of_an_open_window_without_a_new_load(session) -> None:  # type: ignore[no-untyped-def]
    child, writer = session
    other = next((name for name in QStyleFactory.keys() if name.lower() == "windows"), None)
    if other is None:
        pytest.skip("this runtime has no second style")
    _load(child, Appearance(style="Fusion"))
    assert writer.responses()[-1].result["style"].lower() == "fusion"
    widget = child._views["v1"].widget  # noqa: SLF001
    _send(child, SetAppearance(request_id="s3", view_id="v1", appearance=Appearance(style=other)))
    answer = writer.responses()[-1]
    assert answer.ok and answer.result["style"].lower() == "windows"
    assert child._views["v1"].widget is widget  # noqa: SLF001


@pytest.mark.parity("R3-177")
def test_esc_on_the_preview_window_closes_it_and_the_editor_is_told(session, qapp) -> None:  # type: ignore[no-untyped-def]
    child, writer = session
    _load(child, Appearance())
    widget = child._views["v1"].widget  # noqa: SLF001
    field = widget.findChild(QLineEdit, "nameEdit")
    field.setFocus()
    qapp.processEvents()
    QTest.keyClick(field, Qt.Key.Key_Escape)
    qapp.processEvents()
    closed = [item for item in writer.sent if isinstance(item, ViewClosed)]
    assert [(item.view_id, item.reason) for item in closed] == [("v1", "user")]
    assert "v1" not in child._views  # noqa: SLF001


def test_a_host_close_is_one_view_closed_not_two(session) -> None:  # type: ignore[no-untyped-def]
    child, writer = session
    _load(child, Appearance())
    _send(child, CloseView(request_id="c1", view_id="v1"))
    closed = [item for item in writer.sent if isinstance(item, ViewClosed)]
    assert [item.reason for item in closed] == ["host"]


def test_other_keys_leave_the_window_open(session, qapp) -> None:  # type: ignore[no-untyped-def]
    child, writer = session
    _load(child, Appearance())
    widget = child._views["v1"].widget  # noqa: SLF001
    label = widget.findChild(QLabel, "titleLabel")
    QTest.keyClick(label, Qt.Key.Key_A)
    QTest.keyClick(widget.findChild(QLineEdit, "nameEdit"), Qt.Key.Key_Escape, Qt.KeyboardModifier.ShiftModifier)
    qapp.processEvents()
    assert "v1" in child._views  # noqa: SLF001
    assert not [item for item in writer.sent if isinstance(item, ViewClosed)]
