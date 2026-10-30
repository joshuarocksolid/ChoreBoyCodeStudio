# pyright: reportAttributeAccessIssue=false
"""UX-M6-003 for the method page, the gesture, and a window-file save.

Process CPU time, 20 runs, on the 300-widget reference form and a 2,000-line
window file of 150 methods. p95 is the high sample (index ``int(n * 0.95)``).
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration.handlers import MethodRequest  # noqa: E402
from app.features.form_builder.integration.handlers_code import SERVICE  # noqa: E402
from app.features.form_builder.qtside.pickers import open_method_page  # noqa: E402
from app.qt.QtWidgets import QApplication, QLineEdit  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session  # noqa: E402
from tests.form_builder.qtside.test_m6_m6_1b_perf import _form, _p95  # noqa: E402

pytestmark = [pytest.mark.perf, pytest.mark.timeout(180)]

_RUNS = 20


def _window_source() -> str:
    lines = [
        "from PySide6.QtWidgets import QDialog",
        "",
        "class RefWindow(QDialog):",
        "    def __init__(self, parent=None):",
        "        super().__init__(parent)",
        "",
    ]
    for index in range(150):
        lines.append("    def method_%d(self):" % index)
        lines.append('        """Method %d."""' % index)
        lines.append("        return %d" % index)
        lines.append("")
    while len(lines) < 2000:
        lines.append("    # padding so the file is 2,000 lines")
    return "\n".join(lines[:2000]) + "\n"


def test_method_page_gesture_and_save_checks(tmp_path, qapp: QApplication) -> None:
    print("load", os.getloadavg())
    window, kb, guard = _session(tmp_path, qapp, _form())
    try:
        path = tmp_path / "shop" / "forms" / "customer_window.py"
        path.write_text(_window_source(), encoding="utf-8")
        assert path.read_text(encoding="utf-8").count("\n") >= 2000
        surface = kb.surface
        host = surface.workbench.inspector
        picker = open_method_page(host, "button0", "clicked")
        qapp.processEvents()
        field = picker.findChild(QLineEdit, "formBuilder.eventPickerMethod")
        assert field is not None
        samples = []
        for index in range(_RUNS):
            started = time.process_time()
            field.setText("print_%d" % index)
            qapp.processEvents()
            samples.append(time.process_time() - started)
        keystroke = _p95(samples)
        print("method keystroke p95 %.2f ms  min %.2f  max %.2f  load %s" % (keystroke, min(samples) * 1000, max(samples) * 1000, os.getloadavg()))
        assert keystroke <= 16.0
        picker.hide()
        qapp.processEvents()

        canvas = surface.workbench.canvas
        inspector = surface.workbench.inspector
        editor = window.focusWidget()
        bares = []
        for _ in range(_RUNS):
            started = time.process_time()
            canvas.repaint()
            inspector.repaint()
            if editor is not None:
                editor.repaint()
            qapp.processEvents()
            bares.append(time.process_time() - started)
        bare = _p95(bares)
        gestures = []
        for index in range(_RUNS):
            started = time.process_time()
            SERVICE.make_method(
                surface,
                MethodRequest("Write code", (), "made_%d" % index, "", "button0", "clicked"),
            )
            canvas.repaint()
            inspector.repaint()
            qapp.processEvents()
            gestures.append(time.process_time() - started)
        added = max(0.0, _p95(gestures) - bare)
        print(
            "bare p95 %.2f ms  gesture p95 %.2f ms  added %.2f ms  load %s"
            % (bare, _p95(gestures), added, os.getloadavg())
        )
        assert added <= 50.0

        bridge = surface.code_bridge
        bridge.notify_saved(str(path))
        qapp.processEvents()
        checks = []
        for _ in range(_RUNS):
            started = time.process_time()
            bridge.notify_saved(str(path))
            qapp.processEvents()
            checks.append(time.process_time() - started)
        save_checks = _p95(checks)
        print("save checks p95 %.2f ms  min %.2f  max %.2f  load %s" % (save_checks, min(checks) * 1000, max(checks) * 1000, os.getloadavg()))
        assert save_checks <= 50.0
    finally:
        _close(window, qapp, guard)
