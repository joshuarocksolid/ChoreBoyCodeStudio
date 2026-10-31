# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""K25, keyboard only (UX_SPEC §12.3).

A finished link opens the real event picker. Down moves to returnPressed,
Enter opens the step page, and Enter again writes the step.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from app.features.form_builder.qtside.canvas.layers.connections import drawable_steps
from app.qt.QtCore import Qt
from app.qt.QtGui import QKeySequence
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.engine.commands._support import saved
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.unit

_SALE = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui"
_DESIGNER = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "designer_made.ui"


def _pump(qapp: QApplication) -> None:
    for _ in range(6):
        qapp.processEvents()


def _name(surface: object) -> str:
    document = surface.session.document  # type: ignore[attr-defined]
    current = surface.session.selection.state.current  # type: ignore[attr-defined]
    node = document.get(current) if current is not None else None
    return getattr(node, "object_name", "") or ""


def _click(widget: QWidget, key: Qt.Key, modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
    QTest.keyClick(widget, key, modifier)


def _chord(widget: QWidget, sequence: str) -> None:
    """Press the key the installed QShortcut listens for, including Mac Command."""
    combo = QKeySequence(sequence)[0]
    key = combo.key() if hasattr(combo, "key") else Qt.Key(int(combo) & 0x01FFFFFF)
    mods = combo.keyboardModifiers() if hasattr(combo, "keyboardModifiers") else Qt.KeyboardModifier(int(combo) & 0xFE000000)
    window = widget.window()
    window.activateWindow()
    # Offscreen drops the active window when the picker dialog closes. A chord
    # after that reaches the shortcut only once the window is active again.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        QApplication.setActiveWindow(window)
    widget.setFocus()
    QTest.keyClick(widget, key, mods)


@pytest.mark.timeout(180)
@pytest.mark.parity("R3-2")
@pytest.mark.logic("L-canvas-overlay")
def test_k25_connections_overlay_from_the_keyboard(qapp: QApplication, tmp_path: Path) -> None:
    host = QWidget()
    surface = _open(host, _SALE.read_text(encoding="utf-8"), tmp_path / "sale.ui")
    host.show()
    surface.show()
    _pump(qapp)
    canvas = surface.workbench.canvas
    canvas.setFocus()
    _pump(qapp)
    original = saved(surface.session.document)
    report = []

    _click(canvas, Qt.Key.Key_F4)
    _pump(qapp)
    banner = canvas._banner
    label = banner.findChild(QWidget, "formBuilder.overlayBannerText")
    report.append("F4 banner: visible=%s text=%s" % (banner.isVisible(), "" if label is None else label.text()))
    assert surface.modes.active == "connections"
    assert banner.isVisible()

    for _ in range(12):
        if _name(surface) == "phoneEdit":
            break
        _click(canvas, Qt.Key.Key_Tab)
        _pump(qapp)
    report.append("Tab reached: %s" % _name(surface))
    assert _name(surface) == "phoneEdit"

    _click(canvas, Qt.Key.Key_Return)
    _pump(qapp)
    report.append("Enter link source: %s" % _name(surface))
    assert surface.modes.link_source == surface.session.document.by_name("phoneEdit")[0]

    for _ in range(12):
        if _name(surface) == "nameEdit":
            break
        _click(canvas, Qt.Key.Key_Tab)
        _pump(qapp)
    report.append("Tab receiver: %s" % _name(surface))
    assert _name(surface) == "nameEdit"

    _click(canvas, Qt.Key.Key_Return)
    _pump(qapp)
    search = QApplication.focusWidget()
    assert search is not None and search.objectName() == "formBuilder.eventPickerSearch"
    # editingFinished is current. Down lands on returnPressed, then the step page, then the step.
    _click(search, Qt.Key.Key_Down)
    _pump(qapp)
    _click(search, Qt.Key.Key_Return)
    _pump(qapp)
    _click(search, Qt.Key.Key_Return)
    _pump(qapp)
    drawn = drawable_steps(surface.session.document)
    phone = [step for step in drawn if step.sender == "phoneEdit" and step.receiver == "nameEdit"]
    report.append("phoneEdit step: %s" % bool(phone))
    assert phone
    assert phone[0].signal == "returnPressed()"
    assert len(surface.session.log.entries()) == 1

    _click(canvas, Qt.Key.Key_Escape)
    _pump(qapp)
    if surface.modes.active == "connections":
        _click(canvas, Qt.Key.Key_Escape)
        _pump(qapp)
    report.append("Esc closed overlay: %s" % (surface.modes.active == ""))
    assert surface.modes.active == ""

    canvas.setFocus()
    _chord(canvas, "Ctrl+Shift+L")
    _pump(qapp)
    status = surface.editor_status_sentence()
    count = len(drawable_steps(surface.session.document))
    report.append("Show all status: %s (drawable %d)" % (status, count))
    assert status == "Showing all 3 connections. Ctrl+Shift+L hides them."
    assert count == 3
    arrows = [
        item
        for item in canvas.overlay().items
        if isinstance(getattr(item, "data", None), tuple)
        and item.data
        and item.data[0] == "arrow"
        and item.data[8] == "phoneEdit"
    ]
    report.append("phoneEdit arrow in the layer: %s" % bool(arrows))
    assert arrows
    while surface.undo():
        _pump(qapp)
    report.append("Undo all restored the file: %s" % (saved(surface.session.document) == original))
    assert saved(surface.session.document) == original
    _chord(canvas, "Ctrl+Shift+L")
    _pump(qapp)
    assert links_off(surface)

    _click(canvas, Qt.Key.Key_F4)
    _pump(qapp)
    save = surface.session.document.by_name("saveButton")[0]
    surface.session.selection.set((save,), current=save, source=_source())
    _click(canvas, Qt.Key.Key_Return)
    _pump(qapp)
    _click(canvas, Qt.Key.Key_Home)
    _pump(qapp)
    report.append("Home targets the form: %s" % (surface.modes.link_source == save and _candidate_is_root(surface)))
    assert surface.modes.link_source == save
    assert _candidate_is_root(surface)
    _click(canvas, Qt.Key.Key_Escape)
    _pump(qapp)
    _click(canvas, Qt.Key.Key_Escape)
    _pump(qapp)
    assert saved(surface.session.document) == original and not surface.session.log.entries()
    report.append("Esc twice wrote nothing")

    surface.release()
    host.close()

    designer_bytes = _DESIGNER.read_bytes()
    host2 = QWidget()
    designer = _open(host2, designer_bytes.decode("utf-8"), tmp_path / "designer_made.ui")
    _pump(qapp)
    current = designer.content_source().current_text().encode("utf-8")
    on_disk = (tmp_path / "designer_made.ui").read_bytes()
    report.append("designer resave bytes match the file: %s" % (current == on_disk == designer_bytes))
    assert current == on_disk == designer_bytes
    designer.release()
    host2.close()
    print("\n".join(report))


def links_off(surface: object) -> bool:
    from app.features.form_builder.integration.workbench_ext.connections import links_for

    host = links_for(surface)
    return host is not None and not host.show_all


def _source() -> object:
    from app.features.form_builder.engine.query.selection import SelectionSource

    return SelectionSource.CANVAS


def _candidate_is_root(surface: object) -> bool:
    modes = surface.modes  # type: ignore[attr-defined]
    return modes._link_candidate == surface.session.document.root.id  # type: ignore[attr-defined]
