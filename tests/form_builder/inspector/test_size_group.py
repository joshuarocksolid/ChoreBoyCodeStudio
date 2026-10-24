# pyright: reportAttributeAccessIssue=false
"""Size group: paint project(), commit plan(), agree with the selection chip."""

from __future__ import annotations

from typing import Optional, Tuple

import pytest

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.sizing import chip_words, project
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.qtside.canvas.core.frame import Chip
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import NOT_SET_TEXT
from app.features.form_builder.qtside.realize import Realizer
from app.features.form_builder.qtside.sizing_live import selection_facts
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.qtside.support import form, realize

pytestmark = pytest.mark.usefixtures("qapp")

_LINE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>240</height></rect></property>
  <layout class="QVBoxLayout" name="column">
   <item>
    <widget class="QLineEdit" name="email">
     <property name="text"><string>name@example.com</string></property>
    </widget>
   </item>
  </layout>
""",
)

_BUTTON = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>240</height></rect></property>
  <widget class="QPushButton" name="ok">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
""",
)

_TIPS = {
    "Hug": "As big as its content needs, and no bigger.",
    "Fill": "Takes the spare room the layout gives it.",
    "Fixed": "Exactly this many pixels.",
}

_FILL = frozenset(("Expanding", "MinimumExpanding", "Ignored"))


class _Host:
    def canvas_pressed(self) -> None:
        return None

    def narrate(self, sentence: str) -> None:
        return None

    def hover_changed(self, node: object) -> None:
        return None

    def zoom_changed(self, label: str) -> None:
        return None

    def open_problem(self, node: object) -> None:
        return None

    def open_layout_popover(self, node: object) -> None:
        return None


def test_a_line_edit_with_no_size_policy_outlines_its_class_default() -> None:
    session, realizer = realize(_LINE)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    canvas: Optional[FormCanvas] = None
    parent: Optional[QWidget] = None
    try:
        window, pane = _inspector(session, realizer)
        canvas, parent = _canvas(session, realizer)
        email = _id(session, "email")
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.flush()
        _pump()
        widget = realizer.widget_for(email)
        assert widget is not None
        facts = selection_facts(session.document, (email,), realizer)
        panel = project(facts)
        words = chip_words(panel)
        assert words == _class_default_words(widget)
        assert all(word for word in words)
        group = _group(pane)
        for axis, word in (("width", words[0]), ("height", words[1])):
            assert word is not None
            _assert_outlined(group, axis, word)
        for word, tip in _TIPS.items():
            assert _named(group, QToolButton, "%s width" % word).toolTip() == tip
        captions = [
            label.text()
            for label in group.findChildren(QLabel)
            if label.objectName() == "formBuilder.rowDefault"
        ]
        assert panel.horizontal.caption in captions
        assert panel.vertical.caption in captions
        shown = " \u00d7 ".join(word for word in words if word)
        chips = [
            item
            for item in canvas.overlay().items
            if isinstance(item, Chip) and item.role == "select"
        ]
        assert len(chips) == 1, [getattr(item, "text", type(item).__name__) for item in canvas.overlay().items]
        assert shown in chips[0].text, chips[0].text
    finally:
        _close(window, pane, canvas, parent, realizer, session)


def test_fill_on_a_hugging_button_is_one_undo_of_expanding() -> None:
    session, realizer = realize(_BUTTON)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    try:
        window, pane = _inspector(session, realizer)
        ok = _id(session, "ok")
        session.selection.set((ok,), source=SelectionSource.PROGRAM)
        pane.flush()
        _pump()
        before = len(session.log.entries())
        fill = _named(_group(pane), QToolButton, "Fill width")
        _reveal(pane, fill)
        assert fill.isVisible()
        QTest.mouseClick(fill, _left())
        pane.flush()
        _pump()
        assert len(session.log.entries()) == before + 1
        assert 'hsizetype="Expanding"' in session.text()
        assert session.log.undo()
        pane.flush()
        assert len(session.log.entries()) == before
        assert session.document.node(ok).value("sizePolicy") is None
        widget = realizer.widget_for(ok)
        assert widget is not None
        words = chip_words(project(selection_facts(session.document, (ok,), realizer)))
        assert words[0] is not None
        _assert_outlined(_group(pane), "width", words[0])
    finally:
        _close(window, pane, None, None, realizer, session)


def test_reset_removes_a_minimum_from_the_file() -> None:
    session, realizer = realize(_LINE)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    try:
        window, pane = _inspector(session, realizer)
        session.selection.set((_id(session, "email"),), source=SelectionSource.PROGRAM)
        pane.flush()
        _pump()
        spin = _named(_group(pane), QSpinBox, "At least width")
        assert spin.keyboardTracking() is False
        edit = spin.lineEdit()
        assert edit is not None
        edit.setFocus()
        edit.selectAll()
        QTest.keyClicks(edit, "40")
        QTest.keyClick(edit, Qt.Key_Return)
        pane.flush()
        _pump()
        assert "<width>40</width>" in session.text()
        reset = pane.findChild(QToolButton, "formBuilder.sizeReset.minimum")
        assert reset is not None
        _reveal(pane, reset)
        assert reset.isVisible()
        QTest.mouseClick(reset, _left())
        pane.flush()
        _pump()
        assert "minimumSize" not in session.text()
    finally:
        _close(window, pane, None, None, realizer, session)


def test_uncommitted_minimum_text_reverts_without_writing() -> None:
    session, realizer = realize(_LINE)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    try:
        window, pane = _inspector(session, realizer)
        session.selection.set((_id(session, "email"),), source=SelectionSource.PROGRAM)
        pane.flush()
        spin = _named(_group(pane), QSpinBox, "At least width")
        edit = spin.lineEdit()
        assert edit is not None
        spin.setFocus()
        _pump()
        edit.setText("12")
        assert pane.properties.focused_row_dirty()
        pane.properties.revert_focused_row()
        assert edit.text() == NOT_SET_TEXT
        assert not pane.properties.focused_row_dirty()
        assert "minimumSize" not in session.text()
    finally:
        _close(window, pane, None, None, realizer, session)


def test_spin_line_edits_have_accessible_names() -> None:
    session, realizer = realize(_LINE)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    try:
        window, pane = _inspector(session, realizer)
        session.selection.set((_id(session, "email"),), source=SelectionSource.PROGRAM)
        pane.flush()
        at_least = _named(_group(pane), QSpinBox, "At least width")
        at_edit = at_least.lineEdit()
        assert at_edit is not None
        assert at_edit.accessibleName() == "At least width"
        row = pane.findChild(QWidget, "formBuilder.row.maxLength")
        assert row is not None
        length = row.findChild(QSpinBox)
        assert length is not None
        length_edit = length.lineEdit()
        assert length_edit is not None
        assert length_edit.accessibleName()
        assert length_edit.accessibleName() == length.accessibleName()
    finally:
        _close(window, pane, None, None, realizer, session)


def test_outlined_segments_use_the_focus_width_in_the_accent() -> None:
    session, realizer = realize(_LINE)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    try:
        window, pane = _inspector(session, realizer)
        pane.apply_chrome(
            chrome_from_values(
                window="#f3f3f3",
                panel="#ffffff",
                text="#1f1f1f",
                muted="#5c5c5c",
                faint="#6b6b6b",
                border="#c8c8c8",
                accent="#ff00aa",
                row_hover="#eef3fb",
                input_bg="#ffffff",
                error="#b00020",
                focus_width=2,
            )
        )
        sheet = pane.styleSheet()
        outlined = sheet.find('[fbOutlined="true"]')
        checked = sheet.find('QToolButton[fbSegment="true"]:checked')
        assert outlined >= 0
        assert "2px solid #ff00aa" in sheet
        assert checked > outlined
    finally:
        _close(window, pane, None, None, realizer, session)


def test_qt_names_show_the_live_policy_under_why() -> None:
    session, realizer = realize(_LINE)
    window: Optional[QWidget] = None
    pane: Optional[InspectorPane] = None
    try:
        window, pane = _inspector(session, realizer)
        email = _id(session, "email")
        session.selection.set((email,), source=SelectionSource.PROGRAM)
        pane.flush()
        widget = realizer.widget_for(email)
        assert widget is not None
        policy = widget.sizePolicy()
        action = _qt_names(pane)
        action.setChecked(True)
        label = _group(pane).findChild(QLabel, "formBuilder.rowQtName")
        assert label is not None
        expected = "(%s \u00d7 %s)" % (
            _policy_name(policy.horizontalPolicy()),
            _policy_name(policy.verticalPolicy()),
        )
        assert label.isVisible()
        assert label.text() == expected
        why = _group(pane).findChild(QLabel, "formBuilder.sizeWhy")
        assert why is not None
        assert why.isVisible()
        assert why.accessibleName() == "Why is it this size?"
    finally:
        _close(window, pane, None, None, realizer, session)


def _inspector(session: FormSession, realizer: Realizer) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    layout = QVBoxLayout(window)
    layout.addWidget(pane)
    window.resize(980, 860)
    window.show()
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setActiveWindow(window)
    pane.flush()
    _pump()
    return window, pane


def _canvas(session: FormSession, realizer: Realizer) -> Tuple[FormCanvas, QWidget]:
    parent = QWidget()
    parent.resize(960, 720)
    canvas = FormCanvas(session, realizer, _Host(), parent)
    canvas.resize(960, 720)
    parent.show()
    _pump()
    return canvas, parent


def _group(pane: QWidget) -> QWidget:
    found = pane.findChild(QWidget, "formBuilder.sizeGroup")
    assert found is not None
    return found


def _named(root: QWidget, kind: type, access: str) -> QWidget:
    found = [widget for widget in root.findChildren(kind) if widget.accessibleName() == access]
    assert len(found) == 1, access
    return found[0]


def _assert_outlined(group: QWidget, axis: str, word: str) -> None:
    chosen = _named(group, QToolButton, "%s %s" % (word, axis))
    assert chosen.property("fbOutlined") == "true"
    assert chosen.isChecked() is False
    for other in ("Hug", "Fill", "Fixed"):
        if other == word:
            continue
        sibling = _named(group, QToolButton, "%s %s" % (other, axis))
        assert sibling.property("fbOutlined") == "false"
        assert sibling.isChecked() is False


def _reveal(pane: QWidget, widget: QWidget) -> None:
    scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    assert scroll is not None
    scroll.ensureWidgetVisible(widget)
    _pump()


def _id(session: FormSession, name: str) -> NodeId:
    found = session.document.by_name(name)
    assert len(found) == 1
    return found[0]


def _qt_names(pane: InspectorPane) -> object:
    button = pane.findChild(QToolButton, "formBuilder.inspectorMenu")
    assert button is not None
    menu = button.menu()
    assert menu is not None
    for action in menu.actions():
        if action.text() == "Qt names":
            return action
    raise AssertionError("Qt names")


def _class_default_words(widget: QWidget) -> Tuple[str, str]:
    policy = widget.sizePolicy()
    return (
        _class_default_word(policy.horizontalPolicy()),
        _class_default_word(policy.verticalPolicy()),
    )


def _class_default_word(value: object) -> str:
    if _policy_name(value) in _FILL:
        return "Fill"
    return "Hug"


def _policy_name(value: object) -> str:
    name = getattr(value, "name", None)
    text = name if isinstance(name, str) and name else str(value)
    if "::" in text:
        text = text.rsplit("::", 1)[-1]
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _left() -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")


def _pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(4):
        app.processEvents()


def _close(
    window: Optional[QWidget],
    pane: Optional[InspectorPane],
    canvas: Optional[FormCanvas],
    parent: Optional[QWidget],
    realizer: Realizer,
    session: FormSession,
) -> None:
    if canvas is not None:
        canvas.dispose()
    if pane is not None:
        pane.dispose()
    realizer.dispose()
    session.dispose()
    if window is not None:
        window.close()
    if parent is not None:
        parent.close()
