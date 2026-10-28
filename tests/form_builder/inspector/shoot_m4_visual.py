# pyright: reportAttributeAccessIssue=false
"""Grab the M4.3b popovers. Not a test. Run with the FreeCAD Python."""

from __future__ import annotations

import os
import sys

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GroupId
from app.qt.QtGui import QPixmap
from app.qt.QtWidgets import QApplication, QPushButton, QToolButton, QVBoxLayout, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.test_m4_visual import _FORM
from tests.form_builder.qtside.support import realize

_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")
_WIDTHS = (236, 300)


def _grab(widget: QWidget, path: str, scale: int) -> None:
    image = widget.grab()
    if scale == 2 and image.devicePixelRatio() < 1.5:
        image = image.scaled(image.width() * 2, image.height() * 2)
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    image.save(path)


def main() -> None:
    folder = os.environ.get(
        "CBCS_FB_SCREENSHOT_DIR",
        "/Users/local/Projects/ChoreBoyCodeStudio/docs/form_builder/orch/shots_m4.3b",
    )
    scale = 2 if os.environ.get("QT_SCALE_FACTOR") == "2" else 1
    app = QApplication.instance() or QApplication(sys.argv)
    session, realizer = realize(_FORM)
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(pane)
    window.show()
    session.selection.set((session.document.by_name("title")[0],), source=SelectionSource.PROGRAM)
    pane.set_group_expanded(GroupId.ALL, True)
    pane.set_group_expanded(GroupId.APPEARANCE, True)
    for mode in _MODES:
        pane.apply_chrome(chrome_for(tokens_from_palette(app.palette(), force_mode=mode)))
        for width in _WIDTHS:
            pane.setFixedWidth(width)
            window.resize(width + 40, 780)
            app.processEvents()
            pane.flush()
            suffix = "%s-%d-%d" % (mode, width, scale)
            _row_shot(app, pane, window, folder, "colour-row", "formBuilder.row.color", suffix, scale, open_it=False)
            _open(app, pane, "formBuilder.row.font")
            more = _button("More \u25b8")
            if more is not None and not more.isChecked():
                more.click()
                app.processEvents()
            _shot_popover(app, folder, "font-popover", suffix, scale)
            _close_popover(app)
            _open(app, pane, "formBuilder.row.color")
            _shot_popover(app, folder, "colour-popover", suffix, scale)
            _close_popover(app)
            _open(app, pane, "formBuilder.row.brush")
            pattern = _button("Pattern")
            if pattern is not None:
                pattern.click()
                app.processEvents()
            _shot_popover(app, folder, "brush-pattern", suffix, scale)
            gradient = _button("Gradient")
            if gradient is not None:
                gradient.click()
                app.processEvents()
            _shot_popover(app, folder, "gradient-popover", suffix, scale)
            _close_popover(app)
            _open(app, pane, "formBuilder.row.palette")
            _shot_popover(app, folder, "palette-popover", suffix, scale)
            roles = _named("formBuilder.paletteRoles")
            if roles is not None:
                roles.setFocus()
                from app.qt.QtCore import Qt
                from app.qt.QtTest import QTest
                QTest.keyClick(roles, Qt.Key.Key_Return)
                app.processEvents()
            _shot_popover(app, folder, "palette-role-brush", suffix, scale)
            _close_popover(app)
    # A written 50% swatch on the colour row.
    pane.apply_chrome(chrome_for(tokens_from_palette(app.palette(), force_mode="light")))
    pane.setFixedWidth(236)
    _open(app, pane, "formBuilder.row.color")
    field = _named("formBuilder.colorHex")
    if field is not None:
        field.setText("#1A7F3780")
        from app.qt.QtCore import Qt
        from app.qt.QtTest import QTest
        QTest.keyClick(field, Qt.Key.Key_Return)
        app.processEvents()
    row = pane.findChild(QWidget, "formBuilder.row.color")
    if row is not None:
        _grab(row, os.path.join(folder, "colour-row-alpha50-light-236-1.png"), 1)
    from app.features.form_builder.qtside.visual.color_picker import Swatch
    from app.qt.QtWidgets import QHBoxLayout, QLabel

    for mode in _MODES:
        strip = QWidget()
        row = QHBoxLayout(strip)
        swatch = Swatch(strip, 16)
        swatch.set_tokens(chrome_for(tokens_from_palette(app.palette(), force_mode=mode)))
        swatch.set_color(None, hollow=True)
        caption = QLabel("Default", strip)
        row.addWidget(swatch)
        row.addWidget(caption)
        strip.resize(132, 28)
        strip.show()
        app.processEvents()
        _grab(strip, os.path.join(folder, "colour-row-unwritten-%s-236-1.png" % mode), 1)
        strip.close()
    pane.dispose()
    realizer.dispose()
    session.dispose()
    window.close()


def _open(app: QApplication, pane: QWidget, name: str) -> None:
    _close_popover(app)
    row = pane.findChild(QWidget, name)
    if row is None:
        return
    summary = row.findChild(QPushButton, "formBuilder.summary")
    if summary is not None:
        summary.click()
        app.processEvents()


def _shot_popover(app: QApplication, folder: str, stem: str, suffix: str, scale: int) -> None:
    pop = _named("formBuilder.rowPopover")
    if pop is None:
        return
    _grab(pop, os.path.join(folder, "%s-%s.png" % (stem, suffix)), scale)


def _row_shot(app, pane, window, folder, stem, name, suffix, scale, open_it: bool) -> None:
    del app, open_it, window
    row = pane.findChild(QWidget, name)
    if row is None:
        return
    _grab(row, os.path.join(folder, "%s-%s.png" % (stem, suffix)), scale)


def _named(name: str) -> QWidget | None:
    found = [widget for widget in QApplication.allWidgets() if widget.objectName() == name and widget.isVisible()]
    return found[-1] if found else None


def _button(text: str) -> QToolButton | None:
    for widget in QApplication.allWidgets():
        if isinstance(widget, QToolButton) and widget.isVisible() and widget.text() == text:
            return widget
    return None


def _close_popover(app: QApplication) -> None:
    done = _named("formBuilder.popoverDone")
    if done is not None:
        done.click()
        app.processEvents()


if __name__ == "__main__":
    main()
