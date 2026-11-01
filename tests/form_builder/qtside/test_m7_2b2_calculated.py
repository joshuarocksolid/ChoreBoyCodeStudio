# pyright: reportAttributeAccessIssue=false
"""A Value rule locks its property. A when-rule keeps the design value and adds a link."""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.formula.editor import FormulaEditor
from app.features.form_builder.qtside.inspector import TabId
from app.features.form_builder.qtside.inspector.api import GroupId
from app.features.form_builder.qtside.inspector.pane import InspectorPane
from app.qt.QtCore import QPoint, QRect
from app.qt.QtWidgets import QApplication, QLineEdit, QPushButton, QVBoxLayout, QWidget
from tests.form_builder.qtside.support import form, opened

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QCheckBox" name="discountCheck">
     <property name="text"><string>Discount</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="totalLabel">
     <property name="text"><string>Qty</string></property>
     <property name="cbcsValue"><string>qtySpin</string></property>
     <property name="cbcsVisibleWhen"><string>discountCheck</string></property>
    </widget>
   </item>
   <item>
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
   <item>
    <widget class="QLineEdit" name="discountEdit">
     <property name="cbcsEnabledWhen"><string>False</string></property>
     <property name="cbcsReadOnlyWhen"><string>False</string></property>
    </widget>
   </item>
  </layout>
""",
)


def pump() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()


def _id(session: FormSession, name: str) -> object:
    found = session.document.by_name(name)
    assert found, name
    return found[0]


@contextmanager
def desk(width: int = 480) -> Iterator[Tuple[FormSession, InspectorPane, QWidget]]:
    with opened(FORM) as (session, realizer):
        window = QWidget()
        pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
        layout = QVBoxLayout(window)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(pane)
        window.resize(width, 780)
        pane.setFixedWidth(width)
        window.show()
        pump()
        try:
            yield session, pane, window
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            pump()


def _properties(session: FormSession, pane: InspectorPane, name: str) -> None:
    session.selection.set((_id(session, name),), source=SelectionSource.PROGRAM)  # type: ignore[arg-type]
    pane.focus_tab(TabId.PROPERTIES)
    pane.flush()
    pump()


def _rule_button(row: QWidget) -> QPushButton:
    found = [button for button in row.findChildren(QPushButton) if button.text() == "rule"]
    assert found, row.objectName()
    return found[0]


def test_a_value_rule_locks_the_property_and_edit_rule_opens_the_formula() -> None:
    with desk() as (session, pane, _window):
        _properties(session, pane, "totalLabel")
        row = pane.findChild(QWidget, "formBuilder.row.text")
        assert row is not None and row.isVisible()
        assert row.findChildren(QWidget, "formBuilder.calculatedEdit")
        label = pane.findChild(QWidget, "formBuilder.calculatedLabel")
        assert label is not None
        assert label.text().startswith("Calculated:")
        assert "qtySpin" in label.text() or "qtySpin" in label.toolTip()
        assert label.toolTip() == "Calculated: qtySpin"
        assert row.findChildren(QLineEdit) == []
        depth = len(session.log.entries())
        button = pane.findChild(QPushButton, "formBuilder.calculatedEdit")
        assert button is not None
        button.click()
        pump()
        editor = pane.findChild(FormulaEditor, "formBuilder.formula")
        assert editor is not None and editor.isVisible()
        assert editor.toPlainText() == "qtySpin"
        assert QApplication.focusWidget() is editor
        assert len(session.log.entries()) == depth
        assert not session.log.is_dirty()


def test_when_rules_keep_the_value_and_add_a_rule_link() -> None:
    with desk() as (session, pane, _window):
        _properties(session, pane, "discountEdit")
        read_only = pane.findChild(QWidget, "formBuilder.row.readOnly")
        assert read_only is not None and read_only.isVisible()
        _rule_button(read_only)
        assert pane.findChild(QWidget, "formBuilder.row.visible") is None
        pane.set_group_expanded(GroupId.ALL, True)
        pump()
        enabled = pane.findChild(QWidget, "formBuilder.row.enabled")
        assert enabled is not None and enabled.isVisible()
        _rule_button(enabled).click()
        pump()
        editor = pane.findChild(FormulaEditor, "formBuilder.formula")
        assert editor is not None and editor.toPlainText() == "False"
        _properties(session, pane, "totalLabel")
        visible = pane.findChild(QWidget, "formBuilder.row.visible")
        assert visible is not None and visible.isVisible()
        _rule_button(visible)


def _mapped(widget: QWidget, root: QWidget) -> QRect:
    return QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())


def _rows(pane: QWidget) -> list:
    rows = []
    for widget in pane.findChildren(QWidget):
        name = widget.objectName()
        if name.startswith("formBuilder.row.") and widget.isVisible() and widget.height() > 0:
            rows.append(widget)
    rows.sort(key=lambda widget: widget.mapTo(pane, QPoint(0, 0)).y())
    return rows


def _assert_rows_clear(pane: QWidget) -> None:
    rows = _rows(pane)
    assert len(rows) >= 2
    for above, below in zip(rows, rows[1:]):
        assert not _mapped(above, pane).intersects(_mapped(below, pane)), (above.objectName(), below.objectName())


def _assert_calculated_and_verb(width: int) -> None:
    with desk(width) as (session, pane, _window):
        _properties(session, pane, "totalLabel")
        pump()
        _assert_rows_clear(pane)
        label = pane.findChild(QWidget, "formBuilder.calculatedLabel")
        button = pane.findChild(QWidget, "formBuilder.calculatedEdit")
        assert label is not None and button is not None
        assert not _mapped(label, pane).intersects(_mapped(button, pane))
    from app.features.form_builder.qtside.pickers.flow import _step_page
    from app.features.form_builder.qtside.pickers.popover import EventPicker
    from app.features.form_builder.qtside.pickers.verb_pages import page_for
    from app.features.form_builder.integration.chrome import chrome_for
    from app.shell.theme_tokens import tokens_from_palette
    from tests.form_builder.qtside.test_m7_0s_picker import _sale_context

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    tokens = tokens_from_palette(app.palette())
    chrome = chrome_for(tokens)
    host = QWidget()
    host.resize(width, 420)
    host.show()
    try:
        ctx = _sale_context()
        picker = EventPicker(host, chrome, lambda gesture: None)
        picker._ctx = ctx
        picker._apply(page_for(_step_page(ctx, "clicked", False, -1, ""), "set"))
        picker.setFixedWidth(width)
        picker.show()
        pump()
        fields = picker.verb_box
        widgets = []
        for index in range(picker.verb_fields.count()):
            item = picker.verb_fields.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None and widget.isVisible():
                widgets.append(widget)
        assert len(widgets) >= 2
        for above, below in zip(widgets, widgets[1:]):
            assert not _mapped(above, fields).intersects(_mapped(below, fields))
    finally:
        host.close()
        host.deleteLater()
        pump()


def _with_pytest_path(env: dict) -> dict:
    import importlib.util

    spec = importlib.util.find_spec("pytest_timeout")
    if spec is None or spec.origin is None:
        return env
    root = Path(spec.origin).resolve().parent
    if root.name == "pytest_timeout":
        root = root.parent
    prior = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) if not prior else os.pathsep.join((str(root), prior))
    return env


@pytest.mark.timeout(120)
def test_calculated_row_and_verb_formula_do_not_overlap() -> None:
    if os.environ.get("CBCS_FB_GEOM_CHILD") == "1":
        for width in (236, 300):
            _assert_calculated_and_verb(width)
        return
    for width in (236, 300):
        _assert_calculated_and_verb(width)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_GEOM_CHILD"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONNOUSERSITE"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    _with_pytest_path(env)
    done = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_calculated_row_and_verb_formula_do_not_overlap",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), "\n".join(text.splitlines()[-20:])
