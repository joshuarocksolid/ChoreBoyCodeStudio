# pyright: reportAttributeAccessIssue=false
"""UX-M6-003. Process CPU time on the 300-widget reference form.

Picker keystrokes stay within 16 ms p95, including Qt. Behavior's added share
of a select stays within 16 ms p95 over the Properties-tab flush.
"""

from __future__ import annotations

import json
import os
import time

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.qtside.inspector.pane import TabId  # noqa: E402
from app.features.form_builder.qtside.pickers import open_event_picker  # noqa: E402
from app.features.form_builder.qtside.pickers.flow import PickerSource  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session  # noqa: E402

pytestmark = [pytest.mark.perf, pytest.mark.timeout(180)]


def _p95(samples):
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000.0


def _form() -> str:
    items = []
    conns = []
    for i in range(150):
        items.append('<item><widget class="QLineEdit" name="edit%d"/></item>' % i)
    for i in range(145):
        extra = ""
        if 80 <= i < 120:
            steps = [
                {"do": "slot", "target": "edit%d" % (i % 150), "slot": "clear()"},
                {"do": "slot", "target": "edit%d" % ((i + 1) % 150), "slot": "setFocus()", "on": False},
            ]
            text = json.dumps(steps).replace("&", "&amp;").replace("<", "&lt;")
            extra = '<property name="cbcsOnClicked" stdset="0"><string>%s</string></property>' % text
        items.append(
            '<item><widget class="QPushButton" name="button%d"><property name="text"><string>Button %d</string></property>%s</widget></item>'
            % (i, i, extra)
        )
    for i in range(4):
        items.append('<item><widget class="QLabel" name="label%d"><property name="text"><string>L%d</string></property></widget></item>' % (i, i))
    items.append('<item><widget class="QListWidget" name="bigList"/></item>')
    for i in range(60):
        conns.append(
            "<connection><sender>button%d</sender><signal>clicked()</signal><receiver>edit%d</receiver><slot>clear()</slot></connection>"
            % (i, i)
        )
    for signal in (
        "itemClicked(QListWidgetItem*)",
        "itemActivated(QListWidgetItem*)",
        "currentRowChanged(int)",
        "currentTextChanged(QString)",
    ):
        for n in range(5):
            conns.append(
                "<connection><sender>bigList</sender><signal>%s</signal><receiver>Ref</receiver><slot>close()</slot></connection>"
                % signal
            )
            del n
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Ref</class>\n'
        ' <widget class="QDialog" name="Ref">\n  <layout class="QVBoxLayout" name="verticalLayout">\n%s\n  </layout>\n </widget>\n'
        " <resources/>\n <connections>\n%s\n </connections>\n</ui>\n"
    ) % ("\n".join(items), "\n".join(conns))


def test_behavior_share_and_picker_keystroke(tmp_path, qapp: QApplication) -> None:
    print("load", os.getloadavg())
    window, kb, guard = _session(tmp_path, qapp, _form())
    try:
        session = kb.session
        doc = session.document
        inspector = kb.surface.workbench.inspector

        def select(name: str) -> None:
            session.selection.set((doc.by_name(name)[0],), source=SelectionSource.PROGRAM)

        def measure(tab, name: str):
            inspector.focus_tab(tab)
            kb.pump()
            samples = []
            for _ in range(12):
                select("edit3")
                inspector.flush()
                qapp.processEvents()
                started = time.process_time()
                select(name)
                inspector.flush()
                samples.append(time.process_time() - started)
                qapp.processEvents()
            return _p95(samples)

        properties = measure(TabId.PROPERTIES, "bigList")
        behavior = measure(TabId.BEHAVIOR, "bigList")
        share = max(0.0, behavior - properties)
        print("properties p95 %.2f ms  behavior p95 %.2f ms  share %.2f ms" % (properties, behavior, share))
        assert share <= 16.0

        select("button0")
        inspector.focus_tab(TabId.BEHAVIOR)
        inspector.flush()
        qapp.processEvents()
        host = inspector.findChild(QWidget, "formBuilder.events.first") or inspector
        picker = open_event_picker(host, PickerSource("button0", "clicked"), "")
        qapp.processEvents()
        picker._press("filter", "own action")
        picker._press("enter")
        qapp.processEvents()
        texts = ("e", "ed", "edi", "edit", "edit1", "edit", "edi", "ed", "e", "")
        for text in texts:
            picker.search.setText(text)
            picker.repaint()
            qapp.processEvents()
        samples = []
        pumps = []
        for text in texts * 3:
            started = time.process_time()
            picker.search.setText(text)
            picker.repaint()
            painted = time.process_time()
            qapp.processEvents()
            pumps.append(time.process_time() - started)
            samples.append(painted - started)
        keystroke = _p95(samples)
        print(
            "picker keystroke p95 %.2f ms (setText + repaint)  processEvents p95 %.2f ms  load %s"
            % (keystroke, _p95(pumps), os.getloadavg())
        )
        assert keystroke <= 16.0
    finally:
        _close(window, qapp, guard)
