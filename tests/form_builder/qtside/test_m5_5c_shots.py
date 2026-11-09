# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""M5.5c screenshots (UX_SPEC 12.2 M5 states). Skips unless CBCS_FB_SCREENSHOT_DIR is set.

save-template, start-your-templates (L at 1280 px with the rail, C at 1000 px) and settings-form-designer, in
light, dark and both high-contrast themes. 100% is this process; 200% is a child with QT_SCALE_FACTOR=2.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.features.form_builder.engine.project import user_templates as ut
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.integration import settings_page
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.dialogs.save_template import SaveTemplatePopover
from app.features.form_builder.qtside.start.panel import NewFormPanel
from app.qt.QtCore import QPoint
from app.qt.QtGui import QColor, QPainter, QPixmap
from app.qt.QtWidgets import QApplication, QWidget
from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_models import EditorSettingsSnapshot
from app.shell.theme_tokens import tokens_from_palette

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")
_FORM = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Till</class>\n'
    ' <widget class="QWidget" name="Till"/>\n <resources/>\n <connections/>\n</ui>\n'
)
_TEMPLATES = (
    ("Shop window", "Till and receipts", "user", "window"),
    ("Customer card", "One customer, all details", "user", "fields"),
    ("Daily takings", "", "project", "table"),
)


def test_m5_5c_screenshots(qapp: QApplication, tmp_path: Path) -> None:
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
         "-q", str(Path(__file__).resolve()), "-k", "test_m5_5c_screenshots"],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _picture(path: Path, kind: str) -> None:
    pixmap = QPixmap(200, 120)
    pixmap.fill(QColor("#F2F2F2"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#8A8A8A"))
    painter.setBrush(QColor("#FFFFFF"))
    if kind == "window":
        painter.drawRect(10, 8, 180, 104)
        painter.fillRect(11, 9, 178, 14, QColor("#D8D8D8"))
        painter.fillRect(24, 36, 40, 26, QColor("#3B7DD8"))
        painter.drawRect(76, 38, 100, 10)
        painter.drawRect(76, 56, 100, 10)
    elif kind == "fields":
        for row in range(4):
            painter.drawRect(16, 14 + row * 24, 36, 10)
            painter.drawRect(60, 12 + row * 24, 120, 14)
    else:
        painter.drawRect(10, 10, 180, 14)
        for row in range(4):
            painter.drawRect(10, 30 + row * 20, 180, 16)
    painter.end()
    assert pixmap.save(str(path), "PNG")


def _shoot(qapp: QApplication, folder: Path, tmp_path: Path, scale: int) -> None:
    state = tmp_path / "state"
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True, exist_ok=True)
    for name, description, scope, kind in _TEMPLATES:
        info = ut.save_template(
            scope=scope,
            state_root=str(state),
            project_root=str(root),
            name=name,
            description=description,
            ui_text=_FORM,
            thumbnail=b"",
        )
        _picture(Path(info.folder) / "thumbnail.png", kind)
    found = ut.list_templates(str(state), str(root))
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        chrome = chrome_for(tokens)
        for label, width, height in (("L", 1280, 820), ("C", 1000, 720)):
            panel = NewFormPanel(
                project_root=str(root), directory=str(root / "forms"), fs=OsFileSystem(), chrome=chrome
            )
            panel.resize(width, height)
            panel.show()
            panel.set_user_templates(found)
            panel.set_recents((("invoice.ui", "forms/", "forms/invoice.ui"), ("till.ui", "forms/", "forms/till.ui")))
            panel.card(found[0].card_key).setFocus()
            for _ in range(3):
                qapp.processEvents()
            panel.grab().save(str(folder / ("start-your-templates-%s-%s-%d.png" % (label, mode, scale))))
            panel.close()
        host = QWidget()
        host.resize(520, 360)
        host.setStyleSheet("background: %s;" % chrome.window)
        host.show()
        popover = SaveTemplatePopover(
            host, chrome, name="Shop window", description="Till and receipts", project_available=True, on_save=lambda *a: None
        )
        popover.adjustSize()
        popover.move(host.mapToGlobal(QPoint(20, 20)))
        popover.show()
        for _ in range(3):
            qapp.processEvents()
        popover.grab().save(str(folder / ("save-template-%s-%d.png" % (mode, scale))))
        popover.close()
        host.close()
        settings_page.install()
        dialog = SettingsDialog(EditorSettingsSnapshot(), tokens=tokens, global_settings_payload={})
        page = dialog._tabs_widget.widget(dialog._tabs_widget.count() - 1)
        dialog._tabs_widget.setCurrentWidget(page)
        dialog.resize(860, 520)
        dialog.show()
        for _ in range(3):
            qapp.processEvents()
        dialog.grab().save(str(folder / ("settings-form-designer-%s-%d.png" % (mode, scale))))
        dialog.close()

