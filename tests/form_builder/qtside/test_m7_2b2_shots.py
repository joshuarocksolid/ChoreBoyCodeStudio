# pyright: reportAttributeAccessIssue=false
"""M7.2b2 screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.core import constants
from app.qt.QtCore import QPoint, QRect
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


def _with_pytest_path(env: dict) -> dict:
    import pytest_timeout

    root = Path(pytest_timeout.__file__).resolve().parent
    if root.name == "pytest_timeout":
        root = root.parent
    prior = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) if not prior else os.pathsep.join((str(root), prior))
    return env


def _grab(widget: QWidget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _mapped(widget: QWidget, root: QWidget) -> QRect:
    return QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())


def _clear(root: QWidget, widgets: list) -> None:
    visible = [widget for widget in widgets if widget.isVisible() and widget.width() > 0 and widget.height() > 0]
    for index, above in enumerate(visible):
        above_rect = _mapped(above, root)
        for below in visible[index + 1 :]:
            assert not above_rect.intersects(_mapped(below, root)), (above.objectName(), below.objectName())


def _theme(window: QWidget, mode: str, qapp: QApplication) -> None:
    window._theme_mode = mode  # type: ignore[attr-defined]
    window._shell_theme_workflow.apply_theme_styles()  # type: ignore[attr-defined]
    _pump(qapp)


_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>240</height></rect></property>
  <layout class="QGridLayout" name="gridLayout">
   <property name="horizontalSpacing"><number>64</number></property>
   <property name="verticalSpacing"><number>18</number></property>
   <item row="0" column="0">
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
   <item row="1" column="0">
    <widget class="QSpinBox" name="priceSpin"/>
   </item>
   <item row="0" column="1">
    <widget class="QLabel" name="totalLabel">
     <property name="text"><string>Total</string></property>
     <property name="minimumSize"><size><width>72</width><height>0</height></size></property>
    </widget>
   </item>
   <item row="2" column="0" colspan="2">
    <widget class="QCheckBox" name="discountCheck">
     <property name="text"><string>Discount</string></property>
    </widget>
   </item>
   <item row="3" column="0">
    <widget class="QLineEdit" name="noteEdit"/>
   </item>
   <item row="4" column="0" colspan="2">
    <spacer name="verticalSpacer">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
    </spacer>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _open_form(qapp: QApplication, tmp: Path, text: str) -> tuple:
    from app.shell.main_window import MainWindow
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _NoMouse, _open, _project, _require

    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp / "shop"
    window = MainWindow(state_root=str((tmp / "state").resolve()))
    _project(window, root)
    path = (root / "forms" / "sale.ui").resolve()
    surface = _open(window, qapp, path, text)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    surface.focus_primary()  # type: ignore[attr-defined]
    window.resize(1400, 1000)
    _pump(qapp)
    return window, surface, guard


def _box(widget: QWidget, canvas: QWidget) -> QRect:
    return QRect(widget.mapTo(canvas, QPoint(0, 0)), widget.size())


def _channel_gap(left: object, right: object) -> int:
    return max(
        abs(left.red() - right.red()),  # type: ignore[attr-defined]
        abs(left.green() - right.green()),  # type: ignore[attr-defined]
        abs(left.blue() - right.blue()),  # type: ignore[attr-defined]
    )


def _assert_feed_pixels(path: Path, canvas: QWidget, feeder: QWidget, target: QWidget, mode: str) -> None:
    """Arrow pixels sit in the gap, in ov.connect, at least as far from the backdrop as a connection arrow."""
    from app.features.form_builder.qtside.theme.overlay import backdrop_fill, overlay_palette
    from app.qt.QtGui import QColor, QImage

    image = QImage(str(path))
    assert not image.isNull(), path
    ratio = image.width() / float(max(1, canvas.width()))
    start = _box(feeder, canvas)
    end = _box(target, canvas)
    union = start.united(end).adjusted(-16, -16, 16, 16)
    high = "high_contrast" in mode
    dark = mode in (constants.UI_THEME_MODE_DARK, constants.UI_THEME_MODE_HIGH_CONTRAST_DARK)
    ink = QColor(overlay_palette(high).connect[:7])
    fill = QColor(backdrop_fill(dark, high)[0])
    margin = _channel_gap(ink, fill)
    hits = 0
    strongest = 0
    for y in range(int(union.top() * ratio), int(union.bottom() * ratio)):
        for x in range(int(union.left() * ratio), int(union.right() * ratio)):
            if x < 0 or y < 0 or x >= image.width() or y >= image.height():
                continue
            point = QPoint(int(x / ratio), int(y / ratio))
            if start.adjusted(4, 4, -4, -4).contains(point) or end.adjusted(4, 4, -4, -4).contains(point):
                continue
            pixel = image.pixelColor(x, y)
            if _channel_gap(pixel, ink) > 28:
                continue
            hits += 1
            strongest = max(strongest, _channel_gap(pixel, fill))
    assert hits >= 12, (path.name, feeder.objectName(), hits)
    assert strongest >= int(margin * 0.55), (path.name, strongest, margin)


def _assert_badge_corner(path: Path, canvas: QWidget, widget: QWidget, mode: str) -> None:
    from app.features.form_builder.qtside.theme.overlay import overlay_palette
    from app.qt.QtGui import QColor, QImage

    image = QImage(str(path))
    ratio = image.width() / float(max(1, canvas.width()))
    box = _box(widget, canvas)
    regions = (
        QRect(box.right() - 22, box.top() - 18, 36, 36),
        QRect(box.right() - 22, box.bottom() - 18, 36, 40),
    )
    high = "high_contrast" in mode
    ink = QColor(overlay_palette(high).logic_badge[:7])
    hits = 0
    for region in regions:
        for y in range(int(region.top() * ratio), int(region.bottom() * ratio)):
            for x in range(int(region.left() * ratio), int(region.right() * ratio)):
                if x < 0 or y < 0 or x >= image.width() or y >= image.height():
                    continue
                if _channel_gap(image.pixelColor(x, y), ink) <= 32:
                    hits += 1
    assert hits >= 10, (path.name, widget.objectName(), hits)


def _grab_content(window: QWidget, inspector: QWidget, path: Path, qapp: QApplication) -> None:
    from app.qt.QtWidgets import QScrollArea

    toggle = inspector.findChild(QWidget, "formBuilder.group.content")
    rows = []
    for name in ("formBuilder.row.alignment", "formBuilder.row.wordWrap", "formBuilder.row.text"):
        row = inspector.findChild(QWidget, name)
        if row is not None:
            rows.append(row)
    text_row = inspector.findChild(QWidget, "formBuilder.row.text")
    area = inspector.findChild(QScrollArea)
    if area is not None and text_row is not None:
        area.ensureWidgetVisible(text_row, 0, 8)
        _pump(qapp)
    if toggle is None or not rows:
        _grab(inspector, path)
        return
    top_widget = text_row if text_row is not None else toggle
    top = top_widget.mapTo(inspector, QPoint(0, 0)).y()
    bottom = max(row.mapTo(inspector, QPoint(0, row.height())).y() for row in rows) + 8
    if bottom > inspector.height() or top < 0:
        window.resize(window.width(), window.height() + max(0, bottom - inspector.height()) + max(0, -top) + 48)
        _pump(qapp)
        if area is not None and text_row is not None:
            area.ensureWidgetVisible(text_row, 0, 8)
            _pump(qapp)
        top = top_widget.mapTo(inspector, QPoint(0, 0)).y()
        bottom = max(row.mapTo(inspector, QPoint(0, row.height())).y() for row in rows) + 8
    rect = QRect(0, max(0, top), inspector.width(), max(1, bottom - max(0, top)))
    path.parent.mkdir(parents=True, exist_ok=True)
    inspector.grab(rect).save(str(path))


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from app.features.form_builder.engine.commands.catalog import SetLogic
    from app.features.form_builder.engine.ui4.defaults import QtClassTable
    from app.features.form_builder.engine.logic.repair import repair_references
    from app.features.form_builder.integration.workbench_ext.connections import links_for
    from app.features.form_builder.integration.workbench_ext.repair_refs import offer_repair
    from app.features.form_builder.qtside.dialogs.repair_refs import RepairDialog
    from app.features.form_builder.qtside.formula.editor import FormulaEditor
    from app.features.form_builder.qtside.inspector import TabId
    from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row
    from app.features.form_builder.qtside.pickers.flow import PickContext, PickerSource, _step_page
    from app.features.form_builder.qtside.pickers.popover import EventPicker
    from app.features.form_builder.qtside.pickers.verb_pages import page_for
    from app.features.form_builder.integration.chrome import chrome_for
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest
    from app.qt.QtWidgets import QListWidget
    from app.shell.theme_tokens import tokens_from_palette

    tmp = Path(tempfile.mkdtemp()).resolve()
    window, surface, guard = _open_form(qapp, tmp, _FORM)
    try:
        session = surface.session
        document = session.document
        label_id = document.by_name("totalLabel")[0]
        session.log.execute(SetLogic(label_id, "cbcsValue", "qtySpin * priceSpin"))
        session.log.execute(SetLogic(document.by_name("discountCheck")[0], "cbcsEnabledWhen", "totalLabel"))
        inspector = surface.workbench.inspector
        canvas = surface.workbench.canvas
        realizer = surface.realizer
        for mode in _MODES:
            _theme(window, mode, qapp)
            hide_banner = getattr(canvas, "hide_banner", None)
            if callable(hide_banner):
                hide_banner()
            session.selection.set((label_id,), source="canvas")
            inspector.focus_tab(TabId.BEHAVIOR)
            inspector.flush()
            host = links_for(surface)
            if host is not None:
                host.sync()
            open_state_row(inspector, "cbcsValue")
            _pump(qapp)
            shown = realizer.widget_named("totalLabel")
            assert shown is not None and shown.text() == "0"  # type: ignore[attr-defined]
            _grab(canvas, folder / ("canvas-live-%s-%s.png" % (mode, scale)))
            editor = inspector.findChild(QWidget, "formBuilder.formula")
            assert editor is not None
            QTest.keyClick(editor, Qt.Key.Key_Escape)
            _pump(qapp)
            if host is not None:
                host.sync()
            _pump(qapp)
            feeds_path = folder / ("canvas-feeds-%s-%s.png" % (mode, scale))
            _grab(canvas, feeds_path)
            qty = realizer.widget_named("qtySpin")
            price = realizer.widget_named("priceSpin")
            total = realizer.widget_named("totalLabel")
            check = realizer.widget_named("discountCheck")
            assert qty is not None and price is not None and total is not None and check is not None
            _assert_feed_pixels(feeds_path, canvas, qty, total, mode)
            _assert_feed_pixels(feeds_path, canvas, price, total, mode)
            _assert_badge_corner(feeds_path, canvas, total, mode)
            _assert_badge_corner(feeds_path, canvas, check, mode)
            inspector.focus_tab(TabId.PROPERTIES)
            inspector.flush()
            from tests.form_builder.qtside.test_m7_2b1_shots import _set_inspector_width

            _set_inspector_width(window, 300, qapp)
            _pump(qapp)
            row = inspector.findChild(QWidget, "formBuilder.row.text")
            label = inspector.findChild(QWidget, "formBuilder.calculatedLabel")
            button = inspector.findChild(QWidget, "formBuilder.calculatedEdit")
            assert row is not None and label is not None and button is not None
            assert label.text().startswith("Calculated:")
            assert "qtySpin * priceSpin" in label.text()
            assert "\u2026" not in label.text()
            search = inspector.findChild(QWidget, "formBuilder.inspectorSearch")
            if search is not None:
                assert not _mapped(label, inspector).intersects(_mapped(search, inspector))
            _clear(row, [label, button])
            _grab_content(window, inspector, folder / ("calculated-%s-%s.png" % (mode, scale)), qapp)
            session.log.execute(SetLogic(label_id, "cbcsValue", "oldName"))
            offer_repair(surface.workbench, {"oldName": "QLineEdit"})
            _pump(qapp)
            banner = canvas.banner
            assert banner.isVisible()
            assert banner.sentence() == "1 rule points at a widget that was renamed outside Code Studio."
            _grab(banner, folder / ("repair-banner-%s-%s.png" % (mode, scale)))
            fixes = repair_references(document, {"oldName": "QLineEdit"})
            dialog = RepairDialog(fixes, window, document)
            tokens = getattr(surface, "_tokens", None)
            if tokens is not None:
                dialog.apply_chrome(chrome_for(tokens))
            dialog.adjustSize()
            dialog.show()
            _pump(qapp)
            _grab(dialog, folder / ("repair-dialog-%s-%s.png" % (mode, scale)))
            dialog.close()
            if callable(hide_banner):
                hide_banner()
            tokens = getattr(surface, "_tokens", None)
            chrome = chrome_for(tokens) if tokens is not None else chrome_for(tokens_from_palette(qapp.palette()))
            ctx = PickContext(
                document,
                QtClassTable.shared(),
                PickerSource("noteEdit", "textChanged"),
                "",
                (),
                "forms/sale.ui",
                "Form",
                False,
            )
            picker = EventPicker(window, chrome, lambda gesture: None)
            picker._ctx = ctx
            picker._apply(page_for(_step_page(ctx, "textChanged", False, -1, ""), "set"))
            picker.adjustSize()
            picker.show()
            formula = picker.findChild(FormulaEditor, "formBuilder.verbField.formula")
            assert isinstance(formula, FormulaEditor)
            formula.setFocus()
            QTest.keyClicks(formula, "qty")
            _pump(qapp, 12)
            status = picker.findChild(QWidget, "formBuilder.verbStatus.formula")
            complete = picker.findChild(QListWidget, "formBuilder.formula.complete")
            assert status is not None and status.isVisible() and status.text()  # type: ignore[attr-defined]
            assert complete is not None and complete.isVisible()
            _pump(qapp)
            _grab(picker, folder / ("verb-formula-%s-%s.png" % (mode, scale)))
            picker.close()
            session.log.execute(SetLogic(label_id, "cbcsValue", "qtySpin * priceSpin"))
            _pump(qapp)
    finally:
        from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

        _close(window, qapp, guard)


@pytest.mark.timeout(300)
def test_m7_2b2_shots(qapp: QApplication) -> None:
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
    _with_pytest_path(env)
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
            "test_m7_2b2_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), "\n".join(text.splitlines()[-30:])
