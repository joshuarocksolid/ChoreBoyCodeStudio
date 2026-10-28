# pyright: reportAttributeAccessIssue=false
"""M4.2 round-3 screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set.

100% is this process. 200% is a child process with QT_SCALE_FACTOR=2.
Inspector rows are 236 px of content.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GROUP_ORDER, GroupId
from app.features.form_builder.qtside.realize.api import Realizer
from app.qt.QtWidgets import QApplication, QScrollArea, QWidget
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_m4_empty_pages import EMPTY
from tests.form_builder.qtside.test_m4_mdi import MDI
from tests.form_builder.qtside.test_m4_pages_canvas import _Host
from tests.form_builder.qtside.test_m4_r2_shots import _bands, _flush

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_MODES = ("light", "high_contrast_dark")

_DOCK = form(
    'class="QMainWindow" name="Main"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>420</height></rect></property>
  <widget class="QWidget" name="centralwidget"/>
  <widget class="QDockWidget" name="dock">
   <attribute name="dockWidgetArea"><number>1</number></attribute>
   <widget class="QWidget" name="dockContents"/>
  </widget>
""",
)

_PANEL = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>300</height></rect></property>
  <widget class="QDockWidget" name="dock">
   <property name="geometry"><rect><x>20</x><y>20</y><width>200</width><height>160</height></rect></property>
   <widget class="QWidget" name="contents"/>
  </widget>
""",
)

_GROUP = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>240</height></rect></property>
  <widget class="QGroupBox" name="box">
   <property name="title"><string>Details</string></property>
   <property name="checkable"><bool>true</bool></property>
   <property name="checked"><bool>true</bool></property>
  </widget>
""",
)

_LINE = form(
    'class="QWidget" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>160</height></rect></property>
  <widget class="Line" name="line">
   <property name="orientation"><enum>Qt::Horizontal</enum></property>
  </widget>
""",
)

_WIZARD_ROOT = form(
    'class="QWizard" name="Wizard"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>320</height></rect></property>
  <widget class="QWizardPage" name="start">
   <property name="title"><string>Start</string></property>
  </widget>
""",
)


def test_m4_r3_screenshots(qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, 200)
        return
    _shoot(qapp, folder, 100)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONNOUSERSITE", "1")
    env.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    completed = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "--timeout",
            "0",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m4_r3_screenshots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _shoot(qapp: QApplication, folder: Path, scale: int) -> None:
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        _canvas_shot(tokens, folder, "pages-empty", EMPTY % ("QTabWidget", "tabs"), mode, scale, None)
        _canvas_shot(tokens, folder, "pages-empty-box", EMPTY % ("QToolBox", "box"), mode, scale, None)
        _canvas_shot(tokens, folder, "pages-empty-stack", EMPTY % ("QStackedWidget", "stack"), mode, scale, None)
        _canvas_shot(tokens, folder, "dock-bands", _DOCK, mode, scale, _bands)
        _canvas_shot(tokens, folder, "mdi-windows", MDI, mode, scale, _second_window)
        _canvas_shot(tokens, folder, "wizard-root", _WIZARD_ROOT, mode, scale, None)
        _inspector_shot(qapp, tokens, folder, "rows-dock", _DOCK, "dock", (GroupId.PLACEMENT, GroupId.CONTENT), mode, scale)
        _inspector_shot(qapp, tokens, folder, "rows-panel", _PANEL, "dock", (GroupId.PLACEMENT,), mode, scale)
        _inspector_shot(qapp, tokens, folder, "rows-group", _GROUP, "box", (GroupId.CONTENT, GroupId.APPEARANCE), mode, scale)
        _inspector_shot(qapp, tokens, folder, "rows-line", _LINE, "line", (GroupId.APPEARANCE,), mode, scale)


def _canvas_shot(
    tokens: ShellThemeTokens,
    folder: Path,
    stem: str,
    text: str,
    mode: str,
    scale: int,
    prepare: Callable[[FormSession, FormCanvas], None] | None,
) -> None:
    host = _Host()
    with opened(text) as (session, realizer):
        parent = QWidget()
        parent.resize(900, 640)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(900, 640)
        parent.show()
        canvas.setFocus()
        canvas.apply_theme(tokens)
        _flush()
        if prepare is not None:
            prepare(session, canvas)
            _flush()
        canvas.grab().save(str(folder / ("%s-%s-%d.png" % (stem, mode, scale))))
        canvas.dispose()
        parent.deleteLater()
        _flush()


def _second_window(session: FormSession, canvas: FormCanvas) -> None:
    found = session.document.by_name("notes")
    if found:
        canvas._controller._show_page_step(1, found[0])


def _inspector_shot(
    qapp: QApplication,
    tokens: ShellThemeTokens,
    folder: Path,
    stem: str,
    text: str,
    name: str,
    groups: Tuple[GroupId, ...],
    mode: str,
    scale: int,
) -> None:
    with opened(text) as (session, realizer):
        window, pane = _inspector(session, realizer)
        try:
            pane.apply_chrome(chrome_for(tokens))
            wanted = set(groups)
            for group in GROUP_ORDER:
                pane.set_group_expanded(group, group in wanted)
            found = session.document.by_name(name)
            assert found, name
            session.selection.set((found[0],), source=SelectionSource.PROGRAM)
            pane.flush()
            _fit(qapp, window, pane, 236)
            pane.grab().save(str(folder / ("%s-%s-%d.png" % (stem, mode, scale))))
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            _flush()


def _fit(qapp: QApplication, window: QWidget, pane: QWidget, row_target: int) -> None:
    scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    assert isinstance(scroll, QScrollArea)
    width = row_target + 48
    for _ in range(24):
        window.resize(width, 720)
        pane.resize(width, 720)
        _flush()
        qapp.processEvents()
        row = scroll.viewport().width()
        if row == row_target:
            return
        width += row_target - row
    assert scroll.viewport().width() == row_target


def _inspector(session: FormSession, realizer: Realizer) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    window.resize(280, 720)
    window.show()
    _flush()
    return window, pane
