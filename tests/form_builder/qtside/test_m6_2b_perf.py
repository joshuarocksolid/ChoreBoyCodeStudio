# pyright: reportAttributeAccessIssue=false
"""UX-M6-003 for the method page, the gesture, and a window-file save.

Process CPU time, 40 runs, on the 300-widget reference form and a 2,000-line
window file of 150 methods. p95 is the high sample (index ``int(n * 0.95)``).
The clean-tab path saves the window file. The dirty-tab path does not.
"""

from __future__ import annotations

import gc
import os
import time

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps  # noqa: E402
from app.features.form_builder.engine.logic.events_codec import call_step  # noqa: E402
from app.features.form_builder.integration.handlers import MethodRequest  # noqa: E402
from app.features.form_builder.integration.handlers_code import SERVICE  # noqa: E402
from app.features.form_builder.qtside.pickers import open_method_page  # noqa: E402
from app.qt.QtWidgets import QApplication, QLineEdit  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session  # noqa: E402
from tests.form_builder.qtside.test_m6_m6_1b_perf import _form, _p95  # noqa: E402

pytestmark = [pytest.mark.perf, pytest.mark.timeout(300)]

_RUNS = 40


def _window_source() -> str:
    lines = [
        "from PySide6.QtWidgets import QDialog",
        "",
        "class RefWindow(QDialog):",
        "    def __init__(self, parent=None):",
        "        super().__init__(parent)",
        "        self.ui = Ui_Customer()",
        "        self.ui.setupUi(self)",
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


def _median_ms(samples: list) -> float:
    ordered = sorted(samples)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return ordered[mid] * 1000.0
    return (ordered[mid - 1] + ordered[mid]) * 500.0


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
        gc.collect()
        samples = []
        for index in range(_RUNS):
            started = time.process_time()
            field.setText("print_%d" % index)
            qapp.processEvents()
            samples.append(time.process_time() - started)
        keystroke = _p95(samples)
        print(
            "method keystroke p95 %.2f ms  median %.2f  min %.2f  max %.2f  load %s"
            % (keystroke, _median_ms(samples), min(samples) * 1000, max(samples) * 1000, os.getloadavg())
        )
        assert keystroke <= 16.0
        picker.hide()
        qapp.processEvents()
        # Open the window file first. The timed gestures edit that tab. A dirty
        # tab is not saved, so the shell's Python lint stays out of the sample.
        window._editor_tab_workflow.open_file_at_line(str(path), 1)
        qapp.processEvents()
        from app.qt.QtGui import QTextCursor

        opened = window._workspace_controller.widget_for_path(str(path))
        assert opened is not None
        opened.moveCursor(QTextCursor.MoveOperation.End)
        qapp.processEvents()

        canvas = surface.workbench.canvas
        inspector = surface.workbench.inspector

        def _repaint() -> None:
            canvas.repaint()
            inspector.repaint()
            editor = window._workspace_controller.widget_for_path(str(path))  # type: ignore[attr-defined]
            if editor is not None:
                editor.repaint()
            qapp.processEvents()

        def _one(name: str):
            return SERVICE.make_method(
                surface,
                MethodRequest(
                    "Write code",
                    (SetEventSteps("button0", "clicked", (call_step(name),), caption="Call %s" % name),),
                    name,
                    "",
                    "button0",
                    "clicked",
                ),
            )

        def _added(prefix: str) -> float:
            gc.collect()
            bares = []
            for _ in range(_RUNS):
                started = time.process_time()
                _repaint()
                bares.append(time.process_time() - started)
            for index in range(3):
                out = _one("%s_warm_%d" % (prefix, index))
                assert out.ok, out
            gc.collect()
            gestures = []
            for index in range(_RUNS):
                gc.collect()
                started = time.process_time()
                out = _one("%s_%d" % (prefix, index))
                assert out.ok, out
                _repaint()
                gestures.append(time.process_time() - started)
            bare = _p95(bares)
            gesture = _p95(gestures)
            added = max(0.0, gesture - bare)
            print(
                "%s bare p95 %.2f ms median %.2f  gesture p95 %.2f median %.2f  added %.2f ms  load %s"
                % (prefix, bare, _median_ms(bares), gesture, _median_ms(gestures), added, os.getloadavg())
            )
            return gesture

        # UX-M6-003 "Double-click to a new method with the caret in the code tab:
        # tab already open <= 80 ms" is the budget for this whole gesture (D30).
        # The tab is clean, so each gesture saves it. That is K26's path.
        clean_gesture = _added("clean")
        opened.insertPlainText("\n# scratch\n")
        qapp.processEvents()
        dirty_gesture = _added("dirty")

        bridge = surface.code_bridge
        bridge.notify_saved(str(path))
        qapp.processEvents()
        gc.collect()
        checks = []
        for _ in range(_RUNS):
            started = time.process_time()
            bridge.notify_saved(str(path))
            qapp.processEvents()
            checks.append(time.process_time() - started)
        save_checks = _p95(checks)
        print(
            "save checks p95 %.2f ms  median %.2f  min %.2f  max %.2f  load %s"
            % (save_checks, _median_ms(checks), min(checks) * 1000, max(checks) * 1000, os.getloadavg())
        )
        assert save_checks <= 50.0
        assert dirty_gesture <= 80.0
        assert clean_gesture <= 80.0
    finally:
        _close(window, qapp, guard)
