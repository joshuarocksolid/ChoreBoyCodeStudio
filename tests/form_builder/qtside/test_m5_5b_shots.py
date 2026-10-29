# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""M5.5b screenshot states (UX_SPEC 12.2): ``form-settings`` at 236 and 300 px, and the free-placement grid on the canvas.

Skips unless CBCS_FB_SCREENSHOT_DIR is set. The 200% pass runs in a child process with QT_SCALE_FACTOR=2.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.commands.catalog_ext.form_fields import SetFormGrid, SetFormField
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.schema import LayoutDefault
from app.features.form_builder.integration.chrome import chrome_for
from app.qt.QtGui import QPalette
from app.qt.QtWidgets import QApplication, QCheckBox, QLineEdit, QToolButton, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.m5_5b_support import close, free_form, open_pane
from tests.form_builder.inspector.test_m43c_pictures import _fit_row
from tests.form_builder.qtside.test_m5_5b_canvas import _open_big

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    qapp.processEvents()
    widget.grab().save(str(folder / (stem + ".png")))


@pytest.mark.timeout(600)
def test_m5_5b_shots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, tmp_path, "200")
        return
    _shoot(qapp, folder, tmp_path, "100")
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    completed = subprocess.run(
        [sys.executable, "-s", "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib", "--timeout", "600", "-q",
         str(Path(__file__).resolve()), "-k", "test_m5_5b_shots"],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _shoot(qapp: QApplication, folder: Path, tmp_path: Path, suffix: str) -> None:
    for mode in _MODES:
        tokens = tokens_from_palette(QPalette(), force_mode=mode)
        chrome = chrome_for(tokens)
        for width in (236, 300):
            _settings(qapp, folder, "%s-%s-%d" % (mode, suffix, width), width, chrome)
        _canvas(qapp, folder, tmp_path, "%s-%s" % (mode, suffix), tokens)


def _settings(qapp, folder: Path, name: str, width: int, chrome) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer = open_pane(qapp, free_form(' stdsetdef="1"'), width)
    try:
        pane.apply_chrome(chrome)
        _fit_row(qapp, window, pane, width)
        window.resize(window.width(), 1500)
        log = session.log
        log.execute(SetFormField("author", "Pat Ng"))
        log.execute(SetFormField("layoutdefault", LayoutDefault(6, 11)))
        log.execute(SetFormField("pixmapfunction", "load_picture"))
        log.execute(SetFormField("includes", (("local", "shop.h"), ("global", "vector"))))
        log.execute(SetFormField("idbasedtr", "true"))
        log.execute(SetFormGrid("across", 16))
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        for key in ("code", "translation", "freePlacement"):
            toggle = pane.findChild(QToolButton, "formBuilder.group.%s" % key)
            if toggle is not None and not toggle.isChecked():
                toggle.click()
        pane.flush()
        # A refused function name shows its sentence under the row.
        edit = pane.findChild(QLineEdit, "formBuilder.formSetting.pixmapfunction.edit")
        edit.setText("load picture")
        edit.editingFinished.emit()
        qapp.processEvents()
        _grab(qapp, window, folder, "form-settings-" + name)
    finally:
        close(window, pane, realizer, session, qapp)


def _canvas(qapp, folder: Path, tmp_path: Path, name: str, tokens) -> None:  # type: ignore[no-untyped-def]
    host, surface = _open_big(tmp_path / ("till_%s.ui" % name), free_form())
    try:
        surface.apply_theme(tokens)
        surface.session.log.execute(SetFormGrid("across", 16))
        surface.session.log.execute(SetFormGrid("down", 16))
        for _ in range(4):
            qapp.processEvents()
        _grab(qapp, surface.workbench.canvas, folder, "free-grid-canvas-" + name)
    finally:
        surface.release()
        host.close()
