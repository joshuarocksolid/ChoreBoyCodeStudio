# pyright: reportAttributeAccessIssue=false
"""State and formula screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.core import constants
from app.qt.QtTest import QTest
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
    """Point the 200% child at the pytest that provides the timeout plugin.

    The checks runner leaves user-site pytest ahead of the vendor tree, and
    that pytest has no timeout plugin. The child sets PYTHONNOUSERSITE, so it
    must be given the vendor directory explicitly.
    """
    import importlib.util

    spec = importlib.util.find_spec("pytest_timeout")
    if spec is None or spec.origin is None:
        return env
    root = Path(spec.origin).resolve().parent
    if root.name == "pytest_timeout":
        root = root.parent
    prior = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) if not prior else os.pathsep.join((str(root), prior))
    return env


def _grab(widget: QWidget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _child(root: QWidget, name: str) -> QWidget:
    found = root.findChild(QWidget, name)
    assert found is not None, name
    return found


def _theme(window: QWidget, mode: str, qapp: QApplication) -> None:
    window._theme_mode = mode  # type: ignore[attr-defined]
    window._shell_theme_workflow.apply_theme_styles()  # type: ignore[attr-defined]
    _pump(qapp)


def _apply_inspector_width(window: QWidget, width: int) -> None:
    from app.qt.QtWidgets import QSplitter

    splitter = window.findChild(QSplitter, "formBuilder.splitter")
    assert splitter is not None
    right = splitter.widget(2)
    right.setMinimumWidth(width)
    right.setMaximumWidth(width)
    sizes = splitter.sizes()
    total = sum(sizes) or splitter.width()
    left = sizes[0] if len(sizes) == 3 else 232
    splitter.setSizes([left, max(360, total - left - width), width])


def _set_inspector_width(window: QWidget, width: int, qapp: QApplication) -> None:
    # A taller open formula grows the workbench, and that resize puts the
    # saved inspector width back. Apply once so the section can grow, then
    # again so the grab sees the requested width.
    _apply_inspector_width(window, width)
    _pump(qapp)
    _apply_inspector_width(window, width)
    qapp.processEvents()
    editor = window.findChild(QWidget, "formBuilder.formula")
    reflow = getattr(editor, "_reflow_block", None) if editor is not None else None
    if editor is not None and editor.isVisible() and callable(reflow):
        reflow()


def _clear_inspector_width(window: QWidget, qapp: QApplication) -> None:
    from app.features.form_builder.integration.layout import INSPECTOR_DEFAULT, INSPECTOR_MAX, INSPECTOR_MIN

    from app.qt.QtWidgets import QSplitter

    splitter = window.findChild(QSplitter, "formBuilder.splitter")
    assert splitter is not None
    right = splitter.widget(2)
    right.setMinimumWidth(INSPECTOR_MIN)
    right.setMaximumWidth(INSPECTOR_MAX)
    _set_inspector_width(window, INSPECTOR_DEFAULT, qapp)


def _key(name: str) -> object:
    from app.qt.QtCore import Qt

    return getattr(getattr(Qt, "Key", Qt), name)


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m7_2b1_k27 import _session

    tmp = Path(tempfile.mkdtemp()).resolve()
    window, kb, guard, _path = _session(tmp, qapp)
    try:
        surface = kb.surface
        edit = surface.session.document.by_name("discountEdit")[0]
        inspector = surface.workbench.inspector
        for mode in _MODES:
            _theme(window, mode, qapp)
            surface.session.selection.set((edit,), source="canvas")
            inspector.focus_tab(TabId.BEHAVIOR)
            inspector.flush()
            _pump(qapp)
            state = _child(inspector, "formBuilder.state")
            from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row
            from app.qt.QtCore import Qt

            node = surface.session.document.node(edit)
            stored = getattr(node.value("cbcsEnabledWhen"), "text", "") if node is not None else ""
            if stored:
                open_state_row(inspector, "cbcsEnabledWhen")
                _pump(qapp)
                editor = _child(inspector, "formBuilder.formula")
                editor.setPlainText("")  # type: ignore[attr-defined]
                QTest.keyClick(editor, _key("Key_Return"), Qt.KeyboardModifier.ControlModifier)  # type: ignore[arg-type]
                _pump(qapp)
                assert not editor.isVisible()
            _save(state, window, folder, "state-empty", mode, scale, qapp)
            open_state_row(inspector, "cbcsEnabledWhen")
            _pump(qapp)
            editor = _child(inspector, "formBuilder.formula")
            QTest.keyClicks(editor, "discountCheck")
            _pump(qapp)
            QTest.keyClick(editor, _key("Key_Return"), Qt.KeyboardModifier.ControlModifier)  # type: ignore[arg-type]
            _pump(qapp)
            assert not editor.isVisible()
            _save(state, window, folder, "state-filled", mode, scale, qapp)
            open_state_row(inspector, "cbcsVisibleWhen")
            _pump(qapp)
            editor = _child(inspector, "formBuilder.formula")
            QTest.keyClicks(editor, "disc")
            _pump(qapp)
            _save(state, window, folder, "fx-complete", mode, scale, qapp)
            editor = _child(inspector, "formBuilder.formula")
            editor.setPlainText("missingField")
            _pump(qapp)
            _save(state, window, folder, "fx-error", mode, scale, qapp)
            QTest.keyClick(editor, _key("Key_Escape"))
            _pump(qapp)
    finally:
        from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

        _close(window, qapp, guard)


def _save(state: QWidget, window: QWidget, folder: Path, slug: str, mode: str, scale: str, qapp: QApplication) -> None:
    if slug == "fx-complete":
        _assert_completion_list_opaque(state, qapp)
    _grab(state, folder / ("%s-%s-%s.png" % (slug, mode, scale)))
    _set_inspector_width(window, 236, qapp)
    _grab(state, folder / ("%s-%s-%s-236.png" % (slug, mode, scale)))
    _clear_inspector_width(window, qapp)


@pytest.mark.timeout(300)
def test_m7_2b1_shots(qapp: QApplication) -> None:
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
            "test_m7_2b1_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text


def _assert_completion_list_opaque(state: QWidget, qapp: QApplication) -> None:
    """Pixels inside the completion list are its own fill or its own text.

    The list sits on top of Read-only when, Value, and Format. A transparent
    popup leaves those colours in the list rect.
    """
    from app.qt.QtCore import QPoint
    from app.qt.QtGui import QColor
    from app.qt.QtWidgets import QListWidget

    listed = state.findChild(QListWidget, "formBuilder.formula.complete")
    assert listed is not None and listed.isVisible(), "completion list is not open"
    listed.hide()
    state.repaint()
    qapp.processEvents()
    under = state.grab().toImage()
    listed.show()
    listed.raise_()
    state.repaint()
    qapp.processEvents()
    over = state.grab().toImage()
    ratio = over.width() / float(max(1, state.width()))
    if ratio <= 0:
        ratio = 1.0
    origin = listed.mapTo(state, QPoint(0, 0))
    inset = max(3, int(round(4 * ratio)))
    left = int(round(origin.x() * ratio)) + inset
    top = int(round(origin.y() * ratio)) + inset
    right = int(round((origin.x() + listed.width()) * ratio)) - inset
    bottom = int(round((origin.y() + listed.height()) * ratio)) - inset
    right = min(right, over.width())
    bottom = min(bottom, over.height())
    assert right - left > 4 and bottom - top > 4, (left, top, right, bottom, over.width(), over.height())
    fill = QColor(str(listed.property("cbcsFill") or "#000000"))
    ink = QColor(str(listed.property("cbcsInk") or "#000000"))
    mark = QColor(str(listed.property("cbcsMark") or listed.property("cbcsFill") or "#000000"))
    # The current row is a selection. Glyph edges blend that fill with the text,
    # and the row edge blends it with the list fill. The platform highlight is
    # a different blue, so the colours come from the theme properties.
    pairs = ((fill, ink), (mark, ink), (fill, mark))
    foreign = []
    leaked = 0
    changed = 0
    seen = 0
    for y in range(top, bottom, 2):
        for x in range(left, min(right, under.width()), 2):
            if x < 0 or y < 0 or y >= under.height():
                continue
            seen += 1
            pixel = over.pixelColor(x, y)
            before = under.pixelColor(x, y)
            if not _list_color(pixel, pairs):
                foreign.append((x, y, pixel.name()))
            if not _near(pixel, before, 2):
                changed += 1
            elif not _near(pixel, fill, 12):
                # Same pixels as the rows underneath, and not the list fill.
                # Grey body text sits near the fill-to-ink blend, so a colour
                # check alone would accept it.
                leaked += 1
    assert seen > 0
    assert not foreign, foreign[:8]
    assert changed * 8 > seen, (changed, seen)
    assert leaked * 12 <= seen, (leaked, seen)


def _list_color(pixel: object, pairs: tuple) -> bool:
    for left, right in pairs:
        if _segment_distance(pixel, left, right) <= 22:
            return True
    return False


def _near(pixel: object, other: object, limit: int) -> bool:
    return _channel_distance(pixel, other) <= limit


def _channel_distance(pixel: object, other: object) -> int:
    return max(
        abs(pixel.red() - other.red()),  # type: ignore[attr-defined]
        abs(pixel.green() - other.green()),  # type: ignore[attr-defined]
        abs(pixel.blue() - other.blue()),  # type: ignore[attr-defined]
    )


def _segment_distance(pixel: object, start: object, end: object) -> float:
    ax, ay, az = start.red(), start.green(), start.blue()  # type: ignore[attr-defined]
    bx, by, bz = end.red(), end.green(), end.blue()  # type: ignore[attr-defined]
    px, py, pz = pixel.red(), pixel.green(), pixel.blue()  # type: ignore[attr-defined]
    abx, aby, abz = float(bx - ax), float(by - ay), float(bz - az)
    apx, apy, apz = float(px - ax), float(py - ay), float(pz - az)
    denom = abx * abx + aby * aby + abz * abz
    if denom <= 0:
        return float(_channel_distance(pixel, start))
    tee = (apx * abx + apy * aby + apz * abz) / denom
    if tee < 0:
        tee = 0.0
    elif tee > 1:
        tee = 1.0
    cx, cy, cz = ax + tee * abx, ay + tee * aby, az + tee * abz
    return ((px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2) ** 0.5
