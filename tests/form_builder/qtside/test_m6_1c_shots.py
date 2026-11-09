# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Screenshots of the M6.1c canvas states (UX_SPEC §12.2).

Skips unless CBCS_FB_SCREENSHOT_DIR is set. 100% is this process. 200% is a
child with QT_SCALE_FACTOR=2. L is 1440×860 and C is 1080×600.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.logic.events_codec import call_step, slot_step
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.workbench_ext.connections import links_for
from app.features.form_builder.qtside.canvas.core.overlay import LayerItem
from app.features.form_builder.qtside.canvas.layers.connections import drawable_steps
from app.qt.QtCore import QPoint, QPointF
from app.qt.QtWidgets import QApplication, QGraphicsProxyWidget, QVBoxLayout, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)
_SIZES = (("L", 1440, 860), ("C", 1080, 600))
_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui"


def _pump(qapp: QApplication, times: int = 8) -> None:
    for _ in range(times):
        qapp.processEvents()


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    _pump(qapp)
    widget.grab().save(str(folder / (stem + ".png")))


def _marks(canvas: QWidget) -> tuple:
    arrows = chips = badges = 0
    for item in canvas.overlay().items:  # type: ignore[attr-defined]
        if not isinstance(item, LayerItem) or not isinstance(item.data, tuple) or not item.data:
            continue
        if item.data[0] == "arrow":
            arrows += 1
        elif item.data[0] == "chip" and item.data[2]:
            chips += 1
        elif item.data[0] == "badge":
            badges += 1
    return badges, arrows, chips


@pytest.mark.timeout(600)
def test_m6_1c_shots(qapp: QApplication, tmp_path: Path) -> None:
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
            "test_m6_1c_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    # FreeCAD's offscreen plugin aborts after pytest has already reported the
    # result. A passing summary is the result; the abort is not a failed shot.
    # subprocess reports a signal as a negative number. -11 is SIGSEGV, which
    # this offscreen plugin raises after pytest has printed a passing summary.
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text


def _shoot(qapp: QApplication, folder: Path, suffix: str, tmp_path: Path) -> None:
    sale = _FIXTURE.read_text(encoding="utf-8")
    for mode in _MODES:
        for size, width, height in _SIZES:
            tag = "%s-%s-%s" % (mode, suffix, size)
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            host = QWidget()
            column = QVBoxLayout(host)
            column.setContentsMargins(0, 0, 0, 0)
            surface = _open(host, sale, tmp_path / ("sale-%s.ui" % tag))
            column.insertWidget(0, surface, 1)
            host.resize(width, height)
            host.show()
            surface.show()
            surface.apply_theme(tokens)
            _pump(qapp)
            _arm(surface)
            _pump(qapp)
            canvas = surface.workbench.canvas
            canvas.repaint()
            _pump(qapp, 20)
            badges, arrows, chips = _marks(canvas)
            assert badges >= 4 and arrows >= 1 and chips >= 2, (tag, badges, arrows, chips)
            _grab(qapp, host, folder, "canvas-badges-arrows-%s" % tag)
            _shoot_board(qapp, folder, tag, tokens, width, height, tmp_path)
            surface.toggle_overlay("connections")
            _pump(qapp)
            assert surface.modes.active == "connections"
            assert _marks(surface.workbench.canvas)[0] == 0
            _grab(qapp, host, folder, "connections-overlay-%s" % tag)
            document = surface.session.document
            modes = surface.modes
            modes._link_source = document.by_name("phoneEdit")[0]  # type: ignore[attr-defined]
            modes._link_dragging = True  # type: ignore[attr-defined]
            modes._link_candidate = document.by_name("nameEdit")[0]  # type: ignore[attr-defined]
            canvas = surface.workbench.canvas
            page = canvas.page_widget()
            field = page.findChild(QWidget, "nameEdit")
            local = field.mapTo(page, QPoint(field.width() // 2, field.height() // 2))
            proxy = next(
                item
                for item in canvas.scene().items()
                if isinstance(item, QGraphicsProxyWidget) and item.widget() is page
            )
            scene = proxy.mapToScene(QPointF(float(local.x()), float(local.y())))
            modes._link_pointer = (int(scene.x()), int(scene.y()))  # type: ignore[attr-defined]
            modes._push()  # type: ignore[attr-defined]
            _grab(qapp, host, folder, "connections-link-drag-%s" % tag)
            modes.finish_registered_link(document.by_name("nameEdit")[0])  # type: ignore[attr-defined]
            _pump(qapp, 12)
            picker = next(
                (
                    widget
                    for widget in QApplication.topLevelWidgets()
                    if widget.objectName() == "formBuilder.eventPicker" and widget.isVisible()
                ),
                None,
            )
            assert picker is not None, tag
            _grab(qapp, picker, folder, "connections-overlay-picker-%s" % tag)
            picker.close()
            surface.modes.close()
            surface.release()
            host.close()


def _board_xml() -> str:
    buttons = []
    for index in range(30):
        column, row = index % 6, index // 6
        buttons.append(
            '  <widget class="QPushButton" name="b%d">'
            '<property name="geometry"><rect><x>%d</x><y>%d</y><width>72</width><height>24</height></rect></property>'
            "<property name=\"text\"><string>B%d</string></property></widget>"
            % (index, 12 + column * 88, 12 + row * 40, index)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"><class>Board</class>'
        '<widget class="QWidget" name="Board">'
        '<property name="geometry"><rect><x>0</x><y>0</y><width>560</width><height>240</height></rect></property>'
        "%s</widget></ui>" % "".join(buttons)
    )


def _shoot_board(
    qapp: QApplication,
    folder: Path,
    tag: str,
    tokens: object,
    width: int,
    height: int,
    tmp_path: Path,
) -> None:
    host = QWidget()
    column = QVBoxLayout(host)
    column.setContentsMargins(0, 0, 0, 0)
    surface = _open(host, _board_xml(), tmp_path / ("board-%s.ui" % tag))
    column.insertWidget(0, surface, 1)
    host.resize(width, height)
    host.show()
    surface.show()
    surface.apply_theme(tokens)
    log = surface.session.log
    for index in range(30):
        log.execute(
            SetEventSteps(
                "b%d" % index,
                "clicked",
                (slot_step("b%d" % ((index + 1) % 30), "setFocus()"),),
                caption="Connect b%d" % index,
            )
        )
    links = links_for(surface)
    assert links is not None
    links.toggle_show_all()
    _pump(qapp)
    assert _marks(surface.workbench.canvas)[1] >= 30, tag
    _grab(qapp, host, folder, "canvas-show-all-%s" % tag)
    surface.release()
    host.close()


def _arm(surface: object) -> None:
    document = surface.session.document  # type: ignore[attr-defined]
    log = surface.session.log  # type: ignore[attr-defined]
    log.execute(
        SetEventSteps(
            "clearButton",
            "clicked",
            (
                slot_step("nameEdit", "clear()"),
                call_step("print_receipt"),
                slot_step("Sale", "accept()"),
            ),
            caption="Connect clearButton",
        )
    )
    for sender, signal, target, slot in (
        ("printButton", "clicked", "nameEdit", "setFocus()"),
        ("saveButton", "clicked", "phoneEdit", "setFocus()"),
        ("phoneEdit", "returnPressed", "nameEdit", "setFocus()"),
    ):
        log.execute(SetEventSteps(sender, signal, (slot_step(target, slot),), caption="Connect %s" % sender))
    clear = document.by_name("clearButton")[0]
    surface.session.selection.set((clear,), current=clear, source=SelectionSource.CANVAS)  # type: ignore[attr-defined]
    surface.workbench.focus_inspector_tab("behavior")  # type: ignore[attr-defined]
    host = links_for(surface)
    assert host is not None
    drawn = drawable_steps(document)
    label = next(step for step in drawn if step.sender == "clearButton" and step.kind == "widget")
    host._hover = (label.sender, label.signal, label.index)  # type: ignore[attr-defined]
    host.sync()
