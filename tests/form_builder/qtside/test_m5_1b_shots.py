# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Screenshots of the main-window states (UX-MAIN-003 ... 016). Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.commands.catalog_ext.actions import NewAction
from app.features.form_builder.engine.commands.catalog_ext.main_window import AddEntry, AddMainWindowPart, AddMenu
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.workbench import FormWorkbench
from app.features.form_builder.qtside.actions.glue import MIME_ACTIONS
from app.features.form_builder.qtside.canvas.core.palette import MIME_INSERT
from app.qt.QtCore import QByteArray, QMimeData, QPoint, QPointF, Qt
from app.qt.QtGui import QDropEvent, QPalette
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QScrollArea, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _pump(qapp: QApplication) -> None:
    for _ in range(5):
        qapp.processEvents()


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    _pump(qapp)
    widget.grab().save(str(folder / (stem + ".png")))


def _drop(mime: QMimeData, at: QPoint) -> QDropEvent:
    return QDropEvent(QPointF(at), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def _viewport_point(glue, rect, fx: float = 0.5, fy: float = 0.5) -> QPoint:  # type: ignore[no-untyped-def]
    ox, oy, factor = glue._page_to_viewport()
    return QPoint(int(ox + (rect.x + rect.width * fx) * factor), int(oy + (rect.y + rect.height * fy) * factor))


@pytest.mark.timeout(600)
def test_m5_1b_shots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, "200", tmp_path)
        return
    _shoot(qapp, folder, "100", tmp_path)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    done = subprocess.run(
        [sys.executable, "-s", "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib", "-q",
         str(Path(__file__).resolve()), "-k", "test_m5_1b_shots"],
        cwd=str(Path(__file__).resolve().parents[3]), env=env, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stdout + "\n" + done.stderr


def _shoot(qapp: QApplication, folder: Path, suffix: str, tmp_path: Path) -> None:
    for mode in _MODES:
        host = QWidget()
        surface = _open(host, build_template_ui("main_window", "shop_window"), tmp_path / ("shop-%s-%s.ui" % (mode, suffix)))
        host.show()
        surface.show()
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        surface.apply_theme(tokens)
        host.resize(1080, 600)
        surface.resize(1080, 600)
        _pump(qapp)
        session = surface.session
        doc = session.document
        bar = doc.by_name("menubar")[0]
        file_menu = session.log.execute(AddMenu(bar, 0, "&File")).result
        session.log.execute(AddMenu(bar, 1, "&Edit"))
        session.log.execute(AddEntry(file_menu, 0, "New sale", None, "the File menu"))
        session.log.execute(AddEntry(file_menu, 1, "Print receipt", None, "the File menu"))
        session.log.execute(NewAction("Quit"))
        toolbar = session.log.execute(AddMainWindowPart("toolbar")).result
        session.log.execute(AddEntry(toolbar, 0, "New sale", "actionNew_sale", "toolBar"))
        _pump(qapp)
        glue = surface._menu_edit
        canvas = surface._workbench.canvas_view()
        tag = "%s-%s" % (mode, suffix)
        _grab(qapp, surface, folder, "main-idle-%s" % tag)
        # The File menu open, typing "Pri": the reuse list under the editor.
        session.selection.set((file_menu,), source=SelectionSource.PROGRAM)
        glue.start(file_menu)
        for _ in range(2):
            QTest.keyClick(canvas.viewport(), Qt.Key.Key_Down)
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Return)
        QTest.keyClicks(glue._line if glue._line is not None else canvas.viewport(), "Pri")
        _grab(qapp, surface, folder, "menu-editing-reuse-%s" % tag)
        glue.editor.leave()
        glue.refresh()
        # Toolbar editing with the reuse list.
        session.selection.set((toolbar,), source=SelectionSource.PROGRAM)
        glue.start(toolbar)
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Right)
        QTest.keyClick(canvas.viewport(), Qt.Key.Key_Return)
        QTest.keyClicks(glue._line if glue._line is not None else canvas.viewport(), "Pri")
        _grab(qapp, surface, folder, "toolbar-editing-reuse-%s" % tag)
        glue.editor.leave()
        glue.refresh()
        # An Actions row over the toolbar: the landing line and the sentence.
        tool_map = next(m for m in glue._maps if m.host == toolbar)
        mime = QMimeData()
        mime.setData(MIME_ACTIONS, QByteArray(b"actionQuit"))
        canvas.dragEnterEvent(_drop(mime, _viewport_point(glue, tool_map.rect, 0.9)))
        _grab(qapp, surface, folder, "drag-landing-%s" % tag)
        canvas.dragLeaveEvent(None)
        # A widget over the toolbar is refused.
        refused = QMimeData()
        refused.setData(MIME_INSERT, QByteArray(b"QPushButton"))
        canvas.dragEnterEvent(_drop(refused, _viewport_point(glue, tool_map.rect, 0.5)))
        canvas.dragMoveEvent(_drop(refused, _viewport_point(glue, tool_map.rect, 0.5)))
        _grab(qapp, surface, folder, "refusal-toolbar-%s" % tag)
        canvas.dragLeaveEvent(None)
        # An action selected: the inspector.
        action = doc.by_name("actionPrint_receipt")[0]
        session.selection.set((action,), source=SelectionSource.PROGRAM)
        _grab(qapp, surface, folder, "action-selected-%s" % tag)
        surface.release()
        host.close()
        # The inspector alone at 236 px.
        window, pane, session2, realizer = _pane(qapp, build_template_ui("main_window", "shop_window"))
        try:
            pane.apply_chrome(chrome_for(tokens))
            d2 = session2.document
            menu = session2.log.execute(AddMenu(d2.by_name("menubar")[0], 0, "&File")).result
            session2.log.execute(AddEntry(menu, 0, "Print receipt", None, "the File menu"))
            session2.selection.set((d2.by_name("actionPrint_receipt")[0],), source=SelectionSource.PROGRAM)
            window.resize(236 + 60, 900)
            _pump(qapp)
            pane.flush()
            _grab(qapp, pane, folder, "inspector-action-236-%s" % tag)
            session2.selection.set((d2.root.id,), source=SelectionSource.PROGRAM)
            pane.flush()
            _grab(qapp, pane, folder, "inspector-form-236-%s" % tag)
        finally:
            _close(window, pane, realizer, session2, qapp)
