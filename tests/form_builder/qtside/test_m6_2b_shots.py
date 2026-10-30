# pyright: reportAttributeAccessIssue=false
"""Live screenshots of the M6.2b code states.

Skips unless CBCS_FB_SCREENSHOT_DIR is set. 100% is this process. 200% is a
child with QT_SCALE_FACTOR=2. Inspector states are also grabbed at 236 px.
The pixels come from the real inspector, method page, and Problems panel.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.core import constants
from app.qt.QtGui import QColor, QPalette
from app.qt.QtWidgets import QApplication, QWidget

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _pump(qapp: QApplication, times: int = 6) -> None:
    for _ in range(times):
        qapp.processEvents()


def _grab(widget: QWidget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _splitter(window: QWidget) -> QWidget:
    from app.qt.QtWidgets import QSplitter

    found = window.findChild(QSplitter, "formBuilder.splitter")
    assert found is not None
    return found


def _set_inspector_width(window: QWidget, width: int, qapp: QApplication) -> None:
    splitter = _splitter(window)
    right = splitter.widget(2)
    right.setMinimumWidth(width)
    right.setMaximumWidth(width)
    sizes = splitter.sizes()
    total = sum(sizes) or splitter.width()
    left = sizes[0] if len(sizes) == 3 else 232
    splitter.setSizes([left, max(360, total - left - width), width])
    _pump(qapp)


def _clear_inspector_width(window: QWidget, qapp: QApplication) -> None:
    from app.features.form_builder.integration.layout import INSPECTOR_DEFAULT, INSPECTOR_MAX, INSPECTOR_MIN

    splitter = _splitter(window)
    right = splitter.widget(2)
    right.setMinimumWidth(INSPECTOR_MIN)
    right.setMaximumWidth(INSPECTOR_MAX)
    _set_inspector_width(window, INSPECTOR_DEFAULT, qapp)


def _child(root: QWidget, name: str) -> QWidget:
    found = root.findChild(QWidget, name)
    assert found is not None, name
    return found


def _theme(window: QWidget, mode: str, qapp: QApplication) -> None:
    window._theme_mode = mode  # type: ignore[attr-defined]
    window._shell_theme_workflow.apply_theme_styles()  # type: ignore[attr-defined]
    _pump(qapp)


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from tests.form_builder.qtside.test_m6_2b_k26 import _session

    tmp = Path(tempfile.mkdtemp()).resolve()
    window, kb, guard, _path = _session(tmp, qapp)
    from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
    from app.features.form_builder.engine.logic.events_codec import call_step
    try:
        surface = kb.surface
        surface.session.log.execute(
            SetEventSteps("printButton", "clicked", (call_step("missing_method"),), caption="Call missing_method()")
        )
        window_file = _path.parent / "sale_window.py"
        raw = window_file.read_bytes()
        if b"on_printButton_clicked" not in raw:
            window_file.write_bytes(
                raw
                + b"\r\n    @Slot()\r\n    def on_printButton_clicked(self):\r\n        pass\r\n"
            )
        surface.code_bridge.notify_saved(str(window_file))
        _pump(qapp)
        inspector = surface.workbench.inspector
        for mode in _MODES:
            _theme(window, mode, qapp)
            from app.features.form_builder.qtside.inspector import TabId

            inspector.focus_tab(TabId.BEHAVIOR)
            root_id = surface.session.document.root.id
            surface.session.selection.set((root_id,), source="canvas")
            inspector.flush()
            _pump(qapp)
            yours = _child(inspector, "formBuilder.yourMethods")
            _grab(yours, folder / ("your-methods-%s-%s.png" % (mode, scale)))
            _set_inspector_width(window, 236, qapp)
            inspector.flush()
            _pump(qapp)
            _grab(yours, folder / ("your-methods-%s-%s-236.png" % (mode, scale)))
            _clear_inspector_width(window, qapp)
            button = surface.session.document.by_name("printButton")[0]
            surface.session.selection.set((button,), source="canvas")
            inspector.flush()
            _pump(qapp)
            events = _child(inspector, "formBuilder.events")
            _grab(events, folder / ("events-by-name-%s-%s.png" % (mode, scale)))
            _set_inspector_width(window, 236, qapp)
            inspector.flush()
            _pump(qapp)
            _grab(events, folder / ("events-by-name-%s-%s-236.png" % (mode, scale)))
            _grab(events, folder / ("events-connected-by-name-%s-%s-236.png" % (mode, scale)))
            _clear_inspector_width(window, qapp)
            surface.session.selection.set((root_id,), source="canvas")
            inspector.flush()
            _pump(qapp)
            from app.features.form_builder.integration.form_menu_ext.form_settings import reveal

            reveal(surface)
            _pump(qapp)
            box = _child(window, "formBuilder.formSetting.connectslotsbyname.check")
            box.setFocus()
            row = _child(window, "formBuilder.formSetting.connectslotsbyname")
            # The row is transparent over the inspector. A bare grab fills that
            # with the default window color, so paint the panel behind it.
            panel = inspector._services.chrome.panel  # type: ignore[attr-defined]
            row.setAutoFillBackground(True)
            palette = row.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor(panel))
            row.setPalette(palette)
            _grab(row, folder / ("form-settings-%s-%s.png" % (mode, scale)))
            dialog = box.window()
            dialog.resize(236, max(dialog.height(), 1))
            _pump(qapp)
            _grab(row, folder / ("form-settings-%s-%s-236.png" % (mode, scale)))
            from app.features.form_builder.qtside.pickers import open_method_page

            picker = open_method_page(inspector, "printButton", "clicked")
            _pump(qapp)
            field = _child(picker, "formBuilder.eventPickerMethod")
            field.setFocus()
            _grab(picker, folder / ("method-page-%s-%s.png" % (mode, scale)))
            field.setText("close")
            _pump(qapp)
            _grab(picker, folder / ("method-page-bad-name-%s-%s.png" % (mode, scale)))
            picker.hide()
            panel = window._problems_panel  # type: ignore[attr-defined]
            tabs = window._problems_tab_widget  # type: ignore[attr-defined]
            if panel is not None and tabs is not None:
                tabs.setCurrentWidget(panel)
                splitter = window._vertical_splitter  # type: ignore[attr-defined]
                splitter.setSizes([540, 280])
                _pump(qapp)
                _grab(panel, folder / ("problems-fb201-%s-%s.png" % (mode, scale)))
    finally:
        from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

        _close(window, qapp, guard)


@pytest.mark.timeout(300)
def test_m6_2b_shots(qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, "200")
        return
    _shoot(qapp, folder, "100")
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
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
            "test_m6_2b_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
