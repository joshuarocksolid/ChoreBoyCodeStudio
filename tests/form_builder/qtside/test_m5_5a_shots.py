# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalCall=false, reportIndexIssue=false
"""M5.5a screenshots (UX_SPEC 12.2 M5 states). Skips unless CBCS_FB_SCREENSHOT_DIR is set.

aa-style-screen, add-screen-dialog, image-saved-toast and view-code-split in light, dark and both
high-contrast themes. 100% is this process; 200% is a child with QT_SCALE_FACTOR=2.
The Aa menu is a plain QMenu that the shell's application style sheet paints in the product; here
the builder chrome stands in for that sheet.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration import image_export
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.context_menu import paint_menu
from app.qt.QtCore import QPoint, Qt
from app.qt.QtGui import QImage, QPainter
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QMenu
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _session

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit, pytest.mark.timeout(900)]

_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>300</height></rect></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item><widget class="QLabel" name="titleLabel"><property name="text"><string>Invoice</string></property></widget></item>
   <item><widget class="QLineEdit" name="customerEdit"/></item>
   <item><widget class="QLineEdit" name="totalEdit"/></item>
   <item><widget class="QCheckBox" name="paidCheck"><property name="text"><string>Paid</string></property></widget></item>
   <item><widget class="QPushButton" name="saveButton"><property name="text"><string>Save</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_m5_5a_screenshots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, tmp_path, 200)
        return
    _shoot(qapp, folder, tmp_path, 100)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("PYTHONNOUSERSITE", "1")
    env.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    completed = subprocess.run(
        [sys.executable, "-s", "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib", "--timeout", "0",
         "-q", str(Path(__file__).resolve()), "-k", "test_m5_5a_screenshots"],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _flush(qapp: QApplication, rounds: int = 8) -> None:
    for _ in range(rounds):
        qapp.processEvents()


def _compose(first: QMenu, second: QMenu, path: Path) -> None:
    """The menu and its open submenu together, at the offset they have on screen (the submenu may open to the left)."""
    left = first.grab().toImage()
    right = second.grab().toImage()
    ratio = left.devicePixelRatio() or 1.0
    offset = second.mapToGlobal(QPoint(0, 0)) - first.mapToGlobal(QPoint(0, 0))
    x = int(offset.x() * ratio)
    y = int(offset.y() * ratio)
    origin_x = max(0, -x)
    origin_y = max(0, -y)
    canvas = QImage(
        max(origin_x + left.width(), origin_x + x + right.width()),
        max(origin_y + left.height(), origin_y + y + right.height()),
        QImage.Format.Format_ARGB32,
    )
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage(origin_x, origin_y, left)
    painter.drawImage(origin_x + x, origin_y + y, right)
    painter.end()
    canvas.save(str(path))


def _shoot(qapp: QApplication, folder: Path, tmp_path: Path, scale: int) -> None:
    for mode in _MODES:
        base = tmp_path / ("window-" + mode)
        window, kb, guard = _session(base, qapp, _FORM)
        try:
            window.resize(1800, 900)
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            chrome = chrome_for(tokens)
            surface = kb.surface
            surface.apply_theme(tokens)
            control = surface.preview_control
            session = surface.session
            _flush(qapp)
            # --- Aa menu with Style and Screen open
            menu = surface._toolbar.text_size.menu()
            menu.aboutToShow.emit()
            paint_menu(menu, chrome)
            for stem, title in (("screen", "Screen"), ("style", "Style")):
                menu.popup(surface._toolbar.text_size.mapToGlobal(QPoint(0, surface._toolbar.text_size.height())))
                _flush(qapp)
                found = menu.findChild(QMenu, "formBuilder.preview%sMenu" % title)
                action = found.menuAction()
                menu.setActiveAction(action)
                found.popup(menu.mapToGlobal(menu.actionGeometry(action).topRight()))
                _flush(qapp)
                paint_menu(menu, chrome)
                _compose(menu, found, folder / ("aa-style-%s-%s-%d.png" % (stem, mode, scale)))
                menu.hide()
                found.hide()
                _flush(qapp)
            # --- Add a screen
            dialog = control.add_screen_dialog()
            dialog.name.setText("Till counter")
            dialog.width_box.setValue(1280)
            dialog.height_box.setValue(800)
            dialog.font_size.setValue(14)
            dialog.scale.setValue(150)
            _flush(qapp)
            dialog.grab().save(str(folder / ("add-screen-dialog-%s-%d.png" % (mode, scale))))
            dialog.reject()
            _flush(qapp)
            # --- the toast after Save image
            target = base / "invoice.png"
            image_export.write_image(surface, str(target))
            _flush(qapp)
            surface.grab().save(str(folder / ("image-saved-toast-%s-%d.png" % (mode, scale))))
            surface._command_toast.dismiss()
            # --- View Python code: the selected widget's lines marked
            node = session.document.by_name("totalEdit")[0]
            session.selection.set((node,), source=SelectionSource.PROGRAM)
            # On a ChoreBoy screen (1366 x 768) the Outline waits on its rail while the code is open.
            window.resize(1366, 768)
            _flush(qapp)
            assert surface.toggle_code_view()
            # The shell's application style sheet paints the editor in the product; stand in for it here.
            surface._workbench.code_view.panel.editor.setStyleSheet(
                "QPlainTextEdit { background: %s; color: %s; }" % (tokens.editor_bg, tokens.text_primary)
            )
            QTest.qWait(450)
            _flush(qapp)
            surface.grab().save(str(folder / ("view-code-split-%s-%d.png" % (mode, scale))))
            surface.toggle_code_view()
            _flush(qapp)
        finally:
            _close(window, qapp, guard)
