# pyright: reportAttributeAccessIssue=false
"""UX-M6-003. Process CPU time on the 300-widget reference form.

Selecting a widget with 20 events, a picker keystroke (including processEvents),
stay within 16 ms p95. A commit through to the repainted canvas and inspector
is one discrete action, so its added cost over a bare repaint stays within
50 ms p95, under the 100 ms people notice.
"""

from __future__ import annotations

import json
import os
import time

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps  # noqa: E402
from app.features.form_builder.engine.logic.events_codec import slot_step  # noqa: E402
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
    for index in range(20):
        conns.append(
            "<connection><sender>bigList</sender><signal>sig%d()</signal><receiver>Ref</receiver><slot>close()</slot></connection>"
            % index
        )
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
        inspector.focus_tab(TabId.BEHAVIOR)
        kb.pump()
        page = inspector.behavior
        original = page.paint
        behavior_samples = []

        def timed(view):
            started = time.process_time()
            original(view)
            if getattr(view, "sender_name", "") == "bigList":
                behavior_samples.append(time.process_time() - started)

        page.paint = timed  # type: ignore[method-assign]
        try:
            for _ in range(12):
                select("edit3")
                inspector.flush()
                qapp.processEvents()
                select("bigList")
                inspector.flush()
                qapp.processEvents()
        finally:
            page.paint = original  # type: ignore[method-assign]
        behavior = _p95(behavior_samples)
        print("properties p95 %.2f ms  behavior p95 %.2f ms" % (properties, behavior))
        assert behavior <= 16.0

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
        pumped = _p95(pumps)
        print("processEvents p95 %.2f ms" % pumped)
        assert pumped <= 16.0

        canvas = kb.surface.workbench.canvas
        bares = []
        for _ in range(8):
            started = time.process_time()
            canvas.repaint()
            inspector.repaint()
            qapp.processEvents()
            bares.append(time.process_time() - started)
        bare = _p95(bares)
        one = (slot_step("edit0", "clear()"),)
        commits = []
        for index in range(8):
            steps = one if index % 2 == 0 else ()
            started = time.process_time()
            session.log.execute(SetEventSteps("button0", "clicked", steps, caption="Connect"))
            qapp.processEvents()
            canvas.repaint()
            inspector.repaint()
            qapp.processEvents()
            commits.append(time.process_time() - started)
        added = max(0.0, _p95(commits) - bare)
        print(
            "bare repaint p95 %.2f ms  commit p95 %.2f ms  added %.2f ms  load %s"
            % (bare, _p95(commits), added, os.getloadavg())
        )
        assert added <= 50.0
    finally:
        _close(window, qapp, guard)
