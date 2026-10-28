# pyright: reportAttributeAccessIssue=false
"""Visual property editors: font, colour, brush, gradient, palette, cursor."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.values import (
    BrushValue,
    ColorValue,
    CursorShapeValue,
    FontValue,
    GradientValue,
    PaletteValue,
)
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.visual.color_picker import ColorPicker
from app.features.form_builder.qtside.theme.chrome import chrome_from_values
from app.qt.QtCore import QBuffer, QIODevice, Qt
from app.qt.QtGui import QColor, QFontMetrics, QPalette
from app.qt.QtTest import QTest
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from tests.form_builder.qtside.support import realize

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


@pytest.fixture(autouse=True)
def _private_recent_colours(tmp_path):
    """Recent colours go to a scratch settings root, never the user's."""
    from app.features.form_builder.integration.editor_memory import use_state_root

    use_state_root(str(tmp_path))
    yield
    use_state_root(None)

_CHROME = chrome_from_values(
    window="#f3f3f3",
    panel="#ffffff",
    text="#1f1f1f",
    muted="#5c5c5c",
    faint="#6b6b6b",
    border="#c8c8c8",
    accent="#0060c0",
    row_hover="#eef3fb",
    input_bg="#ffffff",
    error="#b00020",
    focus_width=1,
)

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="title">
     <property name="text"><string>Title</string></property>
     <property name="color">
      <color><red>255</red><green>0</green><blue>0</blue></color>
     </property>
     <property name="brush">
      <brush brushstyle="LinearGradientPattern">
       <gradient type="LinearGradient" spread="PadSpread" coordinatemode="ObjectBoundingMode" startx="0" starty="0" endx="1" endy="0">
        <gradientstop position="0"><color><red>0</red><green>0</green><blue>0</blue></color></gradientstop>
        <gradientstop position="1"><color><red>255</red><green>255</green><blue>255</blue></color></gradientstop>
       </gradient>
      </brush>
     </property>
     <property name="cursor"><cursor>13</cursor></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="other">
     <property name="text"><string>Other</string></property>
     <property name="color">
      <color><red>0</red><green>0</green><blue>255</blue></color>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_REFERENCES = (
    "Sans Serif, 12 pt, Bold",
    "Solid #1A7F37",
    "Busy (arrow and wait)",
    "12 colours changed",
    "#1A7F37",
    "Default (13 pt)",
)
_ELIDED = (
    "Pattern: Dense 4, #000000",
    "Linear gradient, 3 colours",
)


def _pane(qapp: QApplication, text: str = _FORM, width: int = 1400):
    session, realizer = realize(text)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.apply_chrome(_CHROME)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane)
    window.resize(width, 900)
    window.show()
    qapp.setActiveWindow(window)
    qapp.processEvents()
    pane.set_group_expanded(GroupId.ALL, True)
    pane.set_group_expanded(GroupId.APPEARANCE, True)
    pane.flush()
    return window, pane, session, realizer


def _close(window, pane, realizer, session, qapp: QApplication) -> None:
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()
    qapp.processEvents()


def _select(session, *names: str) -> None:
    ids = tuple(session.document.by_name(name)[0] for name in names)
    session.selection.set(ids, source=SelectionSource.PROGRAM)


def _widget(name: str) -> QWidget:
    found = [
        widget
        for widget in QApplication.allWidgets()
        if widget.objectName() == name and widget.isVisible()
    ]
    assert found, name
    return found[-1]


def _open_row(pane: QWidget, name: str, qapp: QApplication) -> QPushButton:
    row = pane.findChild(QWidget, name)
    assert row is not None, name
    summary = row.findChild(QPushButton, "formBuilder.summary")
    assert summary is not None
    summary.click()
    qapp.processEvents()
    return summary


def _done(qapp: QApplication) -> None:
    _widget("formBuilder.popoverDone").click()
    qapp.processEvents()


def _press(widget: QWidget, key: object, modifier: object = Qt.KeyboardModifier.NoModifier) -> None:
    QTest.keyClick(widget, key, modifier)  # type: ignore[arg-type]


def _load(xml: str) -> QWidget:
    buffer = QBuffer()
    buffer.setData(xml.encode("utf-8"))
    buffer.open(QIODevice.ReadOnly)
    widget = QUiLoader().load(buffer)
    assert widget is not None
    return widget


def _role(name: str) -> object:
    return getattr(getattr(QPalette, "ColorRole", QPalette), name)


@pytest.mark.parity("R3-159")
def test_font_parts_round_trip_and_reset(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        _open_row(pane, "formBuilder.row.font", qapp)
        family = _widget("formBuilder.fontFamily")
        line = family.lineEdit()
        assert line is not None
        assert family.hasFocus() or line.hasFocus()
        bold = _widget("formBuilder.fontBold")
        bold.click()
        qapp.processEvents()
        size = _widget("formBuilder.fontSize")
        size.setFocus()
        _press(size, Qt.Key.Key_Up)
        qapp.processEvents()
        more = next(button for button in QApplication.allWidgets() if isinstance(button, QToolButton) and button.isVisible() and button.text() == "More \u25b8")
        more.click()
        qapp.processEvents()
        weight = _widget("formBuilder.fontWeight")
        assert isinstance(weight, QComboBox)
        weight.setCurrentIndex(weight.findData("Bold"))
        weight.activated.emit(weight.currentIndex())
        qapp.processEvents()
        stored = session.document.node(session.document.by_name("title")[0]).prop("font")
        assert stored is not None and isinstance(stored.value, FontValue)
        assert stored.value.bold is True
        assert stored.value.pointsize is not None
        assert stored.value.fontweight == "Bold"
        assert stored.value.family is None
        reset = next(button for button in QApplication.allWidgets() if button.accessibleName() == "Font: reset bold" and button.isVisible())
        reset.click()
        qapp.processEvents()
        stored = session.document.node(session.document.by_name("title")[0]).prop("font")
        assert stored is not None and isinstance(stored.value, FontValue)
        assert stored.value.bold is None
        assert stored.value.pointsize is not None
        _done(qapp)
        xml = session.text()
        assert "<bold>" not in xml
        assert "<pointsize>" in xml
        loaded = _load(xml)
        label = loaded.findChild(QLabel, "title")
        assert label is not None
        assert label.font().pointSize() == stored.value.pointsize
        assert "<fontweight>Bold</fontweight>" in xml
        assert label.font().bold() is True
        _open_row(pane, "formBuilder.row.font", qapp)
        _widget("formBuilder.popoverReset").click()
        qapp.processEvents()
        assert session.document.node(session.document.by_name("title")[0]).prop("font") is None
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-160")
def test_colour_with_and_without_alpha_round_trips(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        summary = _open_row(pane, "formBuilder.row.color", qapp)
        assert "FF0000" in summary.toolTip() or "FF0000" in summary.text()
        field = _widget("formBuilder.colorHex")
        assert isinstance(field, QLineEdit)
        field.setText("#1A7F37")
        _press(field, Qt.Key.Key_Return)
        qapp.processEvents()
        pane.flush()
        plain = session.text()
        assert "<red>26</red>" in plain
        assert "<alpha>" not in plain
        _open_row(pane, "formBuilder.row.color", qapp)
        field = _widget("formBuilder.colorHex")
        field.setText("#1A7F3780")
        _press(field, Qt.Key.Key_Return)
        qapp.processEvents()
        pane.flush()
        xml = session.text()
        assert 'alpha="128"' in xml
        summary = pane.findChild(QWidget, "formBuilder.row.color").findChild(QPushButton, "formBuilder.summary")
        assert summary is not None and "50 %" in (summary.toolTip() or summary.text())
        loaded = _load(xml)
        assert loaded.findChild(QLabel, "title") is not None
        _open_row(pane, "formBuilder.row.color", qapp)
        _widget("formBuilder.popoverReset").click()
        qapp.processEvents()
        assert session.document.node(session.document.by_name("title")[0]).prop("color") is None
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-161")
def test_brush_pattern_and_each_gradient_round_trip(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        _open_row(pane, "formBuilder.row.brush", qapp)
        pattern = next(button for button in QApplication.allWidgets() if isinstance(button, QToolButton) and button.text() == "Pattern" and button.isVisible())
        pattern.click()
        qapp.processEvents()
        choices = _widget("formBuilder.brushPattern")
        assert isinstance(choices, QComboBox)
        choices.setCurrentIndex(choices.findData("Dense4Pattern"))
        choices.activated.emit(choices.currentIndex())
        qapp.processEvents()
        _done(qapp)
        xml = session.text()
        assert 'brushstyle="Dense4Pattern"' in xml
        node = session.document.node(session.document.by_name("title")[0])
        stored = node.prop("brush")
        assert stored is not None and isinstance(stored.value, BrushValue)
        assert stored.value.brushstyle == "Dense4Pattern"
        _open_row(pane, "formBuilder.row.brush", qapp)
        for label, kind, spread, fill in (
            ("Linear", "LinearGradient", "PadSpread", "ObjectBoundingMode"),
            ("Radial", "RadialGradient", "RepeatSpread", "LogicalMode"),
            ("Conical", "ConicalGradient", "ReflectSpread", "StretchToDeviceMode"),
        ):
            next(button for button in QApplication.allWidgets() if isinstance(button, QToolButton) and button.text() == "Gradient" and button.isVisible()).click()
            qapp.processEvents()
            kind_box = _widget("formBuilder.gradientType")
            spread_box = _widget("formBuilder.gradientSpread")
            fill_box = _widget("formBuilder.gradientFill")
            assert isinstance(kind_box, QComboBox)
            kind_box.setCurrentIndex(kind_box.findText(label))
            kind_box.activated.emit(kind_box.currentIndex())
            spread_box.setCurrentIndex(spread_box.findData(spread))
            spread_box.activated.emit(spread_box.currentIndex())
            fill_box.setCurrentIndex(fill_box.findData(fill))
            fill_box.activated.emit(fill_box.currentIndex())
            qapp.processEvents()
        _done(qapp)
        xml = session.text()
        assert 'type="ConicalGradient"' in xml
        assert 'spread="ReflectSpread"' in xml
        assert 'coordinatemode="StretchToDeviceMode"' in xml
        assert "," not in xml.split("position=", 1)[-1][:24]
        loaded = _load(xml)
        label_widget = loaded.findChild(QLabel, "title")
        assert label_widget is not None
        _open_row(pane, "formBuilder.row.brush", qapp)
        _widget("formBuilder.popoverReset").click()
        qapp.processEvents()
        assert session.document.node(session.document.by_name("title")[0]).prop("brush") is None
    finally:
        _close(window, pane, realizer, session, qapp)


def test_gradient_bar_keys_click_drag_and_escape(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        original = session.text()
        _open_row(pane, "formBuilder.row.brush", qapp)
        bar = _widget("formBuilder.gradientBar")
        bar.setFocus()
        qapp.processEvents()
        assert bar.width() > 40
        _press(bar, Qt.Key.Key_Right)
        _press(bar, Qt.Key.Key_Left)
        _press(bar, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
        qapp.processEvents()
        _press(bar, Qt.Key.Key_Insert)
        qapp.processEvents()
        stored = session.document.node(session.document.by_name("title")[0]).prop("brush")
        assert stored is not None and isinstance(stored.value, BrushValue)
        assert stored.value.gradient is not None and len(stored.value.gradient.stops) == 3
        _press(bar, Qt.Key.Key_Delete)
        qapp.processEvents()
        stored = session.document.node(session.document.by_name("title")[0]).prop("brush")
        assert stored is not None and isinstance(stored.value, BrushValue)
        assert stored.value.gradient is not None and len(stored.value.gradient.stops) == 2
        _press(bar, Qt.Key.Key_Delete)
        qapp.processEvents()
        refusal = _widget("formBuilder.rowError")
        assert "at least two colours" in refusal.text()
        QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.rect().center())
        qapp.processEvents()
        stored = session.document.node(session.document.by_name("title")[0]).prop("brush")
        assert stored is not None and isinstance(stored.value, BrushValue)
        assert stored.value.gradient is not None and len(stored.value.gradient.stops) == 3
        QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=bar.rect().center())
        QTest.mouseMove(bar, bar.rect().center() + bar.rect().topLeft())  # keep a move
        away = bar.rect().center()
        away.setY(bar.height() + 40)
        QTest.mouseMove(bar, away)
        QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=away)
        qapp.processEvents()
        _press(bar, Qt.Key.Key_Escape)
        qapp.processEvents()
        assert session.text() == original
        assert len(session.log.entries()) == 0 or session.log.undo() is False
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-162")
def test_palette_one_role_and_each_state(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        _open_row(pane, "formBuilder.row.palette", qapp)
        roles = _widget("formBuilder.paletteRoles")
        roles.setFocus()
        _press(roles, Qt.Key.Key_Down)
        _press(roles, Qt.Key.Key_Return)
        qapp.processEvents()
        field = _widget("formBuilder.colorHex")
        field.setFocus()
        field.setText("#1A7F37")
        _press(field, Qt.Key.Key_Return)
        qapp.processEvents()
        _press(field, Qt.Key.Key_Escape)
        qapp.processEvents()
        assert _widget("formBuilder.paletteRoles").isVisible()
        states = _widget("formBuilder.paletteStates")
        states.setChecked(True)
        qapp.processEvents()
        _done(qapp)
        xml = session.text()
        for group in ("active", "inactive", "disabled"):
            assert "<%s>" % group in xml
            assert 'role="WindowText"' in xml
        loaded = _load(xml)
        label = loaded.findChild(QLabel, "title")
        assert label is not None
        colour = label.palette().color(_role("WindowText"))
        assert (colour.red(), colour.green(), colour.blue()) == (26, 127, 55)
        label_text = session.log.undo_label()
        assert label_text is not None and label_text.startswith("Change palette of ")
        assert len(session.log.entries()) == 1
        _open_row(pane, "formBuilder.row.palette", qapp)
        _widget("formBuilder.popoverReset").click()
        qapp.processEvents()
        assert session.document.node(session.document.by_name("title")[0]).prop("palette") is None
    finally:
        _close(window, pane, realizer, session, qapp)


def test_palette_start_from_colour_asks_before_replacing(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        _open_row(pane, "formBuilder.row.palette", qapp)
        roles = _widget("formBuilder.paletteRoles")
        roles.setFocus()
        _press(roles, Qt.Key.Key_Return)
        qapp.processEvents()
        field = _widget("formBuilder.colorHex")
        field.setText("#010203")
        _press(field, Qt.Key.Key_Return)
        qapp.processEvents()
        _press(QApplication.focusWidget(), Qt.Key.Key_Escape)
        qapp.processEvents()
        start = next(button for button in QApplication.allWidgets() if isinstance(button, QPushButton) and button.text().startswith("Start from a colour") and button.isVisible())
        start.click()
        qapp.processEvents()
        use = next(button for button in QApplication.allWidgets() if isinstance(button, QPushButton) and button.text() == "Use this colour" and button.isVisible())
        use.click()
        qapp.processEvents()
        prompt = next(label for label in QApplication.allWidgets() if isinstance(label, QLabel) and "Replace the" in label.text())
        assert "colours you set?" in prompt.text()
        replace = next(button for button in QApplication.allWidgets() if isinstance(button, QPushButton) and button.text() == "Replace" and button.isVisible())
        replace.click()
        qapp.processEvents()
        _done(qapp)
        stored = session.document.node(session.document.by_name("title")[0]).prop("palette")
        assert stored is not None and isinstance(stored.value, PaletteValue)
        assert stored.value.active
        assert len(session.log.entries()) == 1
    finally:
        _close(window, pane, realizer, session, qapp)


@pytest.mark.parity("R3-163")
def test_legacy_cursor_stays_until_a_shape_is_chosen(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        before = session.text()
        _select(session, "title")
        pane.flush()
        assert "<cursor>13</cursor>" in session.text()
        assert session.text() == before
        combo = pane.findChild(QComboBox, "formBuilder.cursorShape")
        assert combo is not None
        assert combo.currentText() == "Pointing hand"
        assert combo.itemData(combo.currentIndex(), Qt.ItemDataRole.ToolTipRole) == "PointingHandCursor"
        index = combo.findText("Cross")
        combo.setCurrentIndex(index)
        combo.activated.emit(index)
        qapp.processEvents()
        pane.flush()
        xml = session.text()
        assert "<cursorShape>CrossCursor</cursorShape>" in xml
        assert "<cursor>13</cursor>" not in xml
        loaded = _load(xml)
        label = loaded.findChild(QLabel, "title")
        assert label is not None
        from app.qt.qt_compat import enum_value
        assert int(enum_value(label.cursor().shape())) == int(enum_value(Qt.CursorShape.CrossCursor))
        row = pane.findChild(QWidget, "formBuilder.row.cursor")
        assert row is not None
        reset = row.findChild(QToolButton, "formBuilder.rowReset")
        assert reset is not None
        reset.click()
        qapp.processEvents()
        pane.flush()
        assert "<cursorShape>" not in session.text()
        assert "<cursor>13</cursor>" not in session.text()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_recent_colours_are_shared_most_recent_first_and_capped(qapp: QApplication, tmp_path) -> None:
    from app.features.form_builder.integration.editor_memory import active_store, use_state_root

    use_state_root(str(tmp_path))
    try:
        holder = QWidget()
        first = ColorPicker(holder, on_color=lambda _color: None, on_invalid=lambda _message: None)
        second = ColorPicker(holder, on_color=lambda _color: None, on_invalid=lambda _message: None)
        holder.show()
        for number in range(13):
            field = first.findChild(QLineEdit, "formBuilder.colorHex")
            assert field is not None
            field.setText("#%02X0000" % number)
            _press(field, Qt.Key.Key_Return)
        recent = active_store().recent()
        assert len(recent) == 12
        assert recent[0] == "#0C0000"
        assert recent[-1] == "#010000"
        other = ColorPicker(holder, on_color=lambda _color: None, on_invalid=lambda _message: None)
        swatches = other.findChildren(QWidget, "formBuilder.colorRecentSwatch")
        assert [swatch.toolTip() for swatch in swatches] == list(recent)
        assert second.findChild(QWidget, "formBuilder.colorRecent") is not None
    finally:
        use_state_root(None)


def test_summaries_and_colour_square_fit_236(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp, width=264)
    try:
        pane.setFixedWidth(264)
        qapp.processEvents()
        _select(session, "title")
        pane.flush()
        scroll = pane.findChild(QScrollArea)
        if scroll is not None:
            assert scroll.horizontalScrollBar().maximum() == 0
        summary = pane.findChild(QPushButton, "formBuilder.summary")
        assert summary is not None
        metrics = QFontMetrics(summary.font())
        for text in _REFERENCES:
            advance = metrics.horizontalAdvance(text + " \u25be")
            summary.setMinimumWidth(132)
            summary.setMaximumWidth(132)
            summary.set_summary(text)
            qapp.processEvents()
            assert advance <= summary.width(), "%s needs %d in %d" % (text, advance, summary.width())
            assert text in summary.text()
        for text in _ELIDED:
            summary.set_summary(text)
            qapp.processEvents()
            assert summary.toolTip() == text
            assert metrics.horizontalAdvance(text + " \u25be") > summary.width()
        _open_row(pane, "formBuilder.row.color", qapp)
        square = _widget("formBuilder.colorSquare")
        assert (square.width(), square.height()) == (212, 120)
        popover = _widget("formBuilder.rowPopover")
        assert popover.width() <= 320
    finally:
        _close(window, pane, realizer, session, qapp)


def test_multi_select_colour_shows_mixed_and_writes_both(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title", "other")
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.color")
        assert row is not None
        summary = row.findChild(QPushButton, "formBuilder.summary")
        assert summary is not None
        assert "Mixed" in summary.text() or summary.toolTip() == "Mixed" or "Mixed" in summary.toolTip()
        summary.click()
        qapp.processEvents()
        field = _widget("formBuilder.colorHex")
        field.setText("#1A7F37")
        _press(field, Qt.Key.Key_Return)
        qapp.processEvents()
        pane.flush()
        assert len(session.log.entries()) == 1
        for name in ("title", "other"):
            stored = session.document.node(session.document.by_name(name)[0]).prop("color")
            assert stored is not None and isinstance(stored.value, ColorValue)
            assert (stored.value.red, stored.value.green, stored.value.blue) == (26, 127, 55)
    finally:
        _close(window, pane, realizer, session, qapp)


def test_gradient_and_palette_bytes_match_across_locales(tmp_path) -> None:
    script = r"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import (
    BrushValue, ColorRole, ColorValue, GradientStop, GradientValue, PaletteValue,
)
text = '''<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><widget class="QLabel" name="title"/></ui>
'''
session = FormSession.open(text, path="/tmp/cbcs-locale.ui", scope=FormScope(kind="external", ui_path="/tmp/cbcs-locale.ui"))
node = session.document.by_name("title")[0]
gradient = GradientValue(
    type="LinearGradient", spread="PadSpread", coordinatemode="ObjectBoundingMode",
    startx=0.0, starty=0.0, endx=1.0, endy=0.0,
    stops=(
        GradientStop(0.0, ColorValue(0, 0, 0)),
        GradientStop(0.5, ColorValue(26, 127, 55)),
        GradientStop(1.0, ColorValue(255, 255, 255)),
    ),
)
brush = BrushValue(brushstyle="LinearGradientPattern", gradient=gradient)
colour = ColorValue(26, 127, 55)
role = ColorRole("WindowText", BrushValue(brushstyle="SolidPattern", color=colour))
palette = PaletteValue(active=(role,), inactive=(role,), disabled=(role,))
session.log.execute(SetProperty(node, "brush", brush))
session.log.execute(SetProperty(node, "palette", palette))
print(session.text())
session.dispose()
"""
    env_base = os.environ.copy()
    env_base["PYTHONPATH"] = os.pathsep.join(sys.path)
    env_base["QT_QPA_PLATFORM"] = "offscreen"
    env_base["PYTHONNOUSERSITE"] = "1"
    blobs = []
    for locale_name, seed in (("C", "0"), ("de_DE.UTF-8", "1")):
        env = dict(env_base)
        env["LC_ALL"] = locale_name
        env["LANG"] = locale_name
        env["PYTHONHASHSEED"] = seed
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and "locale" in (result.stderr or "").lower():
            pytest.skip("locale %s is not installed" % locale_name)
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        blobs.append(result.stdout)
    assert blobs[0] == blobs[1]
    assert "0,5" not in blobs[0]
    assert 'position="0.500000000000000"' in blobs[0]


def test_palette_state_edit_writes_only_that_group(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        before = session.text()
        _open_row(pane, "formBuilder.row.palette", qapp)
        _widget("formBuilder.paletteStates").setChecked(True)
        qapp.processEvents()
        pane.flush()
        # Showing the states changes no colour, so nothing is written.
        assert session.text() == before
        swatch = next(
            widget
            for widget in QApplication.allWidgets()
            if widget.accessibleName() == "Palette: Disabled" and widget.isVisible()
            and widget.parentWidget() is not None
            and any(label.text() == "Window text" for label in widget.parentWidget().findChildren(QLabel))
        )
        QTest.mouseClick(swatch, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        field = _widget("formBuilder.colorHex")
        field.setText("#FF0000")
        _press(field, Qt.Key.Key_Return)
        qapp.processEvents()
        _press(field, Qt.Key.Key_Escape)
        qapp.processEvents()
        _done(qapp)
        stored = session.document.node(session.document.by_name("title")[0]).prop("palette")
        assert stored is not None and isinstance(stored.value, PaletteValue)
        assert [role.role for role in stored.value.disabled] == ["WindowText"]
        assert stored.value.active == () and stored.value.inactive == ()
        loaded = _load(session.text())
        label = loaded.findChild(QLabel, "title")
        assert label is not None
        group = getattr(QPalette, "ColorGroup", QPalette)
        disabled = label.palette().color(group.Disabled, _role("WindowText"))
        active = label.palette().color(group.Active, _role("WindowText"))
        assert (disabled.red(), disabled.green(), disabled.blue()) == (255, 0, 0)
        assert (active.red(), active.green(), active.blue()) != (255, 0, 0)
    finally:
        _close(window, pane, realizer, session, qapp)


def test_gradient_type_change_writes_that_types_geometry_and_sorted_stops(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        _open_row(pane, "formBuilder.row.brush", qapp)
        kind = _widget("formBuilder.gradientType")
        assert isinstance(kind, QComboBox)
        kind.setCurrentIndex(kind.findText("Radial"))
        kind.activated.emit(kind.currentIndex())
        qapp.processEvents()
        bar = _widget("formBuilder.gradientBar")
        bar.setFocus()
        _press(bar, Qt.Key.Key_Insert)
        qapp.processEvents()
        _done(qapp)
        stored = session.document.node(session.document.by_name("title")[0]).prop("brush")
        assert stored is not None and isinstance(stored.value, BrushValue)
        gradient = stored.value.gradient
        assert isinstance(gradient, GradientValue)
        assert (gradient.centralx, gradient.centraly, gradient.radius, gradient.focalx, gradient.focaly) == (
            0.5, 0.5, 0.5, 0.5, 0.5,
        )
        assert gradient.startx is None and gradient.endx is None
        positions = [stop.position for stop in gradient.stops]
        assert positions == sorted(positions) and len(positions) == 3
    finally:
        _close(window, pane, realizer, session, qapp)


def test_brush_style_switch_refits_popover_and_patterns_draw_32_by_16(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        _open_row(pane, "formBuilder.row.brush", qapp)
        popover = _widget("formBuilder.rowPopover")
        gradient_height = popover.height()
        next(button for button in QApplication.allWidgets() if isinstance(button, QToolButton) and button.text() == "Pattern" and button.isVisible()).click()
        qapp.processEvents()
        # Leaving Gradient hides the stop bar and its fields; the popover shrinks
        # to its content instead of spreading the gap between the rows.
        assert popover.height() < gradient_height
        assert popover.height() <= popover.sizeHint().height() + 1
        choices = _widget("formBuilder.brushPattern")
        assert isinstance(choices, QComboBox)
        assert (choices.iconSize().width(), choices.iconSize().height()) == (32, 16)
    finally:
        _close(window, pane, realizer, session, qapp)


def _luminance(colour: QColor) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(colour.red()) + 0.7152 * channel(colour.green()) + 0.0722 * channel(colour.blue())


def test_written_summaries_stay_readable_on_the_buttons_own_background(qapp: QApplication) -> None:
    dark = chrome_from_values(
        window="#1f2328",
        panel="#262c33",
        text="#e9ecef",
        muted="#adb5bd",
        faint="#8b949e",
        border="#3d444d",
        accent="#4c8dff",
        row_hover="#2d333b",
        input_bg="#1f2328",
        error="#ff6b6b",
        focus_width=1,
    )
    window, pane, session, realizer = _pane(qapp)
    try:
        pane.apply_chrome(dark)
        _select(session, "title")
        pane.flush()
        qapp.processEvents()
        group = getattr(QPalette, "ColorRole", QPalette)
        for name in ("color", "brush"):
            row = pane.findChild(QWidget, "formBuilder.row." + name)
            assert row is not None
            summary = row.findChild(QPushButton, "formBuilder.summary")
            assert summary is not None
            text = _luminance(summary.palette().color(group.ButtonText))
            back = _luminance(summary.palette().color(group.Button))
            light, deep = max(text, back), min(text, back)
            # A written value is never painted in a colour picked without
            # knowing the button it sits on (WCAG AA for normal text).
            assert (light + 0.05) / (deep + 0.05) >= 4.5, name
    finally:
        _close(window, pane, realizer, session, qapp)


def test_palette_summary_counts_one_colour_in_the_singular(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        _open_row(pane, "formBuilder.row.palette", qapp)
        roles = _widget("formBuilder.paletteRoles")
        roles.setFocus()
        _press(roles, Qt.Key.Key_Return)
        qapp.processEvents()
        field = _widget("formBuilder.colorHex")
        field.setText("#1A7F37")
        _press(field, Qt.Key.Key_Return)
        qapp.processEvents()
        _press(field, Qt.Key.Key_Escape)
        qapp.processEvents()
        _done(qapp)
        pane.flush()
        row = pane.findChild(QWidget, "formBuilder.row.palette")
        assert row is not None
        summary = row.findChild(QPushButton, "formBuilder.summary")
        assert summary is not None
        assert summary.toolTip() == "1 colour changed" or summary.text().startswith("1 colour changed")
    finally:
        _close(window, pane, realizer, session, qapp)


def test_brush_row_swatch_paints_the_gradient(qapp: QApplication) -> None:
    window, pane, session, realizer = _pane(qapp)
    try:
        _select(session, "title")
        pane.flush()
        qapp.processEvents()
        row = pane.findChild(QWidget, "formBuilder.row.brush")
        assert row is not None
        swatch = next(child for child in row.findChildren(QWidget) if child.width() == 16 and child.height() == 16)
        image = swatch.grab().toImage()
        ratio = image.width() // 16 or 1
        left = QColor(image.pixel(3 * ratio, 8 * ratio))
        right = QColor(image.pixel(12 * ratio, 8 * ratio))
        # The written brush runs black to white, left to right (UX-PED-083).
        assert left.lightness() < 110 < right.lightness()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_popover_check_boxes_read_on_the_dark_popover(qapp: QApplication) -> None:
    dark = chrome_from_values(
        window="#1f2328", panel="#262c33", text="#e9ecef", muted="#adb5bd", faint="#8b949e",
        border="#3d444d", accent="#4c8dff", row_hover="#2d333b", input_bg="#1f2328",
        error="#ff6b6b", focus_width=1,
    )
    from app.qt.QtWidgets import QCheckBox

    window, pane, session, realizer = _pane(qapp)
    try:
        pane.apply_chrome(dark)
        _select(session, "title")
        pane.flush()
        role = getattr(QPalette, "ColorRole", QPalette)
        panel = QColor("#262c33")
        for row, text in (("formBuilder.row.font", "Kerning"), ("formBuilder.row.palette", "Show each state")):
            _open_row(pane, row, qapp)
            box = next(w for w in QApplication.allWidgets() if isinstance(w, QCheckBox) and w.text() == text)
            ink = box.palette().color(role.WindowText)
            light, deep = sorted((_luminance(ink), _luminance(panel)), reverse=True)
            assert (light + 0.05) / (deep + 0.05) >= 4.5, text
            _done(qapp)
    finally:
        _close(window, pane, realizer, session, qapp)
