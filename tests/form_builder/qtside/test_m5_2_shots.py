# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""M5.2 screenshot states (UX_SPEC 12.2): picker sections, file-path fix, pictures group, toast, resource editor.

Skips unless CBCS_FB_SCREENSHOT_DIR is set. The 200% pass runs in a child process with QT_SCALE_FACTOR=2.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

from app.core import constants
from app.features.form_builder.engine.project.qrc_write import add_pictures
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.provider import FormTabProvider
from app.features.form_builder.integration.toast import CommandToast, ToastNote
from app.qt.QtGui import QColor, QImage, QPalette
from app.qt.QtWidgets import QApplication, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.test_m43c_pictures import _close, _fit_row, _open_row, _select
from tests.form_builder.inspector.test_m5_2_add_picture import _open as _open_form
from tests.form_builder.qtside.test_m5_2_resource_editor import _Editor, _Request

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _picture(index: int) -> bytes:
    image = QImage(24, 24, getattr(getattr(QImage, "Format", QImage), "Format_ARGB32"))
    image.fill(QColor(30 + index * 9 % 200, 110, 200 - index * 7 % 150))
    from app.qt.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    qapp.processEvents()
    widget.grab().save(str(folder / (stem + ".png")))


def _popover(window: QWidget) -> QWidget:
    visible = [w for w in window.findChildren(QWidget, "formBuilder.rowPopover") if w.isVisible()]
    assert visible
    return visible[-1]


def _project(tmp_path: Path, sub: str) -> Path:
    root = tmp_path / sub
    root.mkdir()
    desktop = tmp_path / ("desk_" + sub)
    desktop.mkdir()
    for index, name in enumerate(("logo.png", "mark.png", "pay.png", "save.png", "open.png", "print.png")):
        (desktop / name).write_bytes(_picture(index))
    add_pictures(str(root), str(root / "forms" / "resources.qrc"), [str(desktop / n) for n in ("logo.png", "mark.png", "pay.png")])
    add_pictures(str(root), str(root / "assets" / "more.qrc"), [str(desktop / n) for n in ("save.png", "open.png", "print.png")])
    return root


@pytest.mark.timeout(600)
def test_m5_2_shots(qapp: QApplication, tmp_path: Path) -> None:
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
         str(Path(__file__).resolve()), "-k", "test_m5_2_shots"],
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
            _form_states(qapp, folder, tmp_path, mode, suffix, width, chrome)
        _tab_states(qapp, folder, tmp_path, mode, suffix, tokens)


def _form_states(qapp, folder, tmp_path, mode, suffix, width, chrome) -> None:  # type: ignore[no-untyped-def]
    name = "%s-%s-%d" % (mode, suffix, width)
    # Picker with two sections and two pictures files (the Change caption shows).
    root = _project(tmp_path, "p_%s_%s_%d" % (mode, suffix, width))
    window, pane, session, realizer, _toasts = _open_form(qapp, root)
    try:
        from app.features.form_builder.engine.project.picture_adopt import include_commands

        with session.log.transaction("setup") as txn:
            for command in include_commands(session.document, session.path, str(root / "forms" / "resources.qrc")):
                txn.execute(command)
        pane.apply_chrome(chrome)
        _select(session, "logo")
        pane.flush()
        _fit_row(qapp, window, pane, width)
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        _grab(qapp, _popover(window), folder, "picker-sections-" + name)
        _close_popover(window)
        session.selection.clear(source=SelectionSource.PROGRAM)
        pane.flush()
        group = pane.findChild(QWidget, "formBuilder.formGroup.pictures")
        assert group is not None
        scroll = pane.findChild(QWidget, "formBuilder.inspectorScroll")
        if scroll is not None and hasattr(scroll, "ensureWidgetVisible"):
            scroll.ensureWidgetVisible(group)
        _grab(qapp, pane, folder, "files-group-" + name)
    finally:
        _close(window, pane, realizer, session, qapp)
    # Picker with nothing in it but the footer.
    empty_root = tmp_path / ("e_" + name)
    empty_root.mkdir()
    window, pane, session, realizer, _toasts = _open_form(qapp, empty_root)
    try:
        pane.apply_chrome(chrome)
        _select(session, "logo")
        pane.flush()
        _fit_row(qapp, window, pane, width)
        _open_row(pane, "formBuilder.row.pixmap", qapp)
        _grab(qapp, _popover(window), folder, "picker-empty-" + name)
    finally:
        _close(window, pane, realizer, session, qapp)
    # A file-path icon: the row's warning and its fix link.
    fix_root = tmp_path / ("f_" + name)
    (fix_root / "forms" / "art").mkdir(parents=True)
    (fix_root / "forms" / "art" / "pay.png").write_bytes(_picture(2))
    icon = '<property name="icon"><iconset><normaloff>art/pay.png</normaloff></iconset></property>'
    window, pane, session, realizer, _toasts = _open_form(qapp, fix_root, icon)
    try:
        pane.apply_chrome(chrome)
        _select(session, "payButton")
        pane.flush()
        _fit_row(qapp, window, pane, width)
        row = pane.findChild(QWidget, "formBuilder.row.icon")
        scroll = pane.findChild(QWidget, "formBuilder.inspectorScroll")
        if scroll is not None and hasattr(scroll, "ensureWidgetVisible"):
            scroll.ensureWidgetVisible(row)
        qapp.processEvents()
        _grab(qapp, pane, folder, "file-path-fix-" + name)
    finally:
        _close(window, pane, realizer, session, qapp)


def _close_popover(window: QWidget) -> None:
    done = _popover(window).findChild(QWidget, "formBuilder.popoverDone")
    if done is not None:
        done.click()
    QApplication.processEvents()


def _tab_states(qapp, folder, tmp_path, mode, suffix, tokens) -> None:  # type: ignore[no-untyped-def]
    name = "%s-%s" % (mode, suffix)
    # The toast after the first picture made forms/resources.qrc.
    host = QWidget()
    host.resize(560, 140)
    toast = CommandToast(host)
    toast.apply_theme(tokens)
    host.setStyleSheet("background: %s;" % tokens.editor_bg)
    toast.show_note(
        ToastNote("Made forms/resources.qrc for this project's pictures and added logo.png.", "Undo", "Add picture logo.png", 1),
        lambda _note: None,
    )
    host.show()
    qapp.processEvents()
    _grab(qapp, host, folder, "picture-added-toast-" + name)
    host.close()
    # The resource editor, with a missing picture.
    root = _project(tmp_path, "t_" + name)
    add_pictures(str(root), str(root / "forms" / "resources.qrc"), [str(tmp_path / ("desk_t_" + name) / "print.png")])
    (root / "forms" / "pictures" / "mark.png").unlink()
    path = root / "forms" / "resources.qrc"
    from app.features.form_builder.engine.project.qrc_write import read_layout, write_layout, add_prefix

    write_layout(str(root), str(path), add_prefix(read_layout(str(path)), "/icons"))
    request = _Request(str(path), path.read_text(encoding="utf-8"), None, tokens, _Editor, lambda _p: None, str(root))
    surface = FormTabProvider().create_surface(request)
    surface.resize(1080, 560)
    surface.show()
    qapp.processEvents()
    try:
        _grab(qapp, surface, folder, "qrc-editor-" + name)
        surface.grid.select_resource(":/pictures/mark.png")
        _grab(qapp, surface, folder, "qrc-editor-missing-" + name)
    finally:
        surface.release()


