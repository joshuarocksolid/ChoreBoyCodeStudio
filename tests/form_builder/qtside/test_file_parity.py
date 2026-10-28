# pyright: reportAttributeAccessIssue=false
"""File commands on a real main window (R3-13..16).

Designer binds Ctrl+N to New Form. CBCS binds Ctrl+N to New Project, and
New Form is the File menu item. Save As writes a new .ui and ui_<name>.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectMetadata  # noqa: E402
from app.features.form_builder.engine.commands.catalog import SetProperty  # noqa: E402
from app.features.form_builder.engine.ui4.values import StringValue  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtCore import Qt, QTimer  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>280</height></rect></property>
  <widget class="QPushButton" name="okButton">
   <property name="geometry"><rect><x>40</x><y>40</y><width>80</width><height>28</height></rect></property>
   <property name="text"><string>OK</string></property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _load(window: MainWindow, root: Path) -> None:
    (root / "forms").mkdir(parents=True)
    (root / "cbcs").mkdir()
    window._loaded_project = LoadedProject(  # noqa: SLF001
        project_root=str(root.resolve()),
        manifest_path=str((root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(schema_version=1, name="Shop", default_entry="forms/invoice.ui"),
        entries=[],
    )


def _open(window: MainWindow, qapp: QApplication, path: Path, text: str = _FORM) -> object:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    assert window._editor_tab_factory.open_file_in_editor(str(path))  # noqa: SLF001
    stack = window._center_stack  # noqa: SLF001
    assert stack is not None
    stack.setCurrentIndex(1)
    window.resize(1400, 900)
    window.show()
    qapp.processEvents()
    surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
    assert surface is not None
    return surface


def _dirty(surface: object, text: str) -> None:
    session = surface.session  # type: ignore[attr-defined]
    button = session.document.by_name("okButton")[0]
    session.log.execute(SetProperty(button, "text", StringValue(text)))
    qapp = QApplication.instance()
    assert qapp is not None
    qapp.processEvents()


def _arm_discard(qapp: QApplication) -> dict:
    seen = {"clicked": False}
    pending = {"left": 40}

    def click() -> None:
        for widget in qapp.allWidgets():
            if isinstance(widget, QPushButton) and widget.isVisible() and "Discard" in widget.text():
                seen["clicked"] = True
                widget.click()
                return
        pending["left"] -= 1
        if pending["left"] > 0:
            QTimer.singleShot(50, click)

    QTimer.singleShot(0, click)
    return seen


def _pump(qapp: QApplication, times: int = 12) -> None:
    for _ in range(times):
        qapp.processEvents()


@pytest.mark.parity("R3-13")
@pytest.mark.timeout(60)
def test_new_form_from_the_file_menu_opens_a_form_tab(tmp_path: Path, qapp: QApplication) -> None:
    """File > New Form… creates a form. Ctrl+N stays New Project."""
    _require()
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        _load(window, root)
        window.resize(1400, 900)
        window.show()
        qapp.processEvents()
        registry = window.menu_registry
        assert registry is not None
        action = registry.action("shell.action.file.newForm")
        assert action is not None
        action.trigger()
        _pump(qapp)
        panel = window.findChild(QWidget, "formBuilder.newForm")
        assert panel is not None
        card = panel.findChild(QWidget, "formBuilder.newForm.card.data_entry")
        assert card is not None
        card.setFocus()
        QTest.keyClick(card, Qt.Key_Return)
        _pump(qapp, 30)
        written = list((root / "forms").glob("*.ui"))
        assert written
        canvas = window.findChild(QWidget, "formBuilder.canvas")
        assert canvas is not None
    finally:
        shutdown_main_window_for_test(window, qapp)


@pytest.mark.parity("R3-14")
@pytest.mark.timeout(60)
def test_open_ui_opens_a_form_tab_with_the_canvas(tmp_path: Path, qapp: QApplication) -> None:
    """Open a .ui. The form tab shows the canvas."""
    _require()
    path = tmp_path / "invoice.ui"
    path.write_text(_FORM, encoding="utf-8")
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        window.resize(1400, 900)
        window.show()
        qapp.processEvents()
        with patch(
            "app.shell.file_project_commands_workflow.choose_open_files",
            return_value=[str(path)],
        ):
            QTest.keyClick(window, Qt.Key_O, Qt.ControlModifier | Qt.ShiftModifier)
            _pump(qapp)
        surface = window._tab_content_registry.surface_for_path(str(path))  # noqa: SLF001
        assert surface is not None
        canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
        assert canvas is not None
        assert canvas.page_widget() is not None
    finally:
        shutdown_main_window_for_test(window, qapp)


@pytest.mark.parity("R3-15")
@pytest.mark.timeout(90)
def test_ctrl_s_and_save_all_write_the_ui_and_the_generated_module(
    tmp_path: Path, qapp: QApplication
) -> None:
    """Ctrl+S and Save All write the .ui and ui_*.py for dirty project forms."""
    _require()
    root = tmp_path / "shop"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        _load(window, root)
        first = root / "forms" / "invoice.ui"
        second = root / "forms" / "receipt.ui"
        left = _open(window, qapp, first)
        right = _open(window, qapp, second)
        _dirty(left, "Left saved")
        _dirty(right, "Right saved")
        QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier)
        _pump(qapp, 20)
        active = window._editor_manager.active_tab()  # noqa: SLF001
        assert active is not None
        active_path = Path(active.file_path)
        assert "saved" in active_path.read_text(encoding="utf-8").lower()
        assert (active_path.parent / ("ui_%s.py" % active_path.stem)).is_file()
        QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier | Qt.ShiftModifier)
        _pump(qapp, 20)
        for path, needle in ((first, "Left saved"), (second, "Right saved")):
            assert needle in path.read_text(encoding="utf-8")
            assert (path.parent / ("ui_%s.py" % path.stem)).is_file()
        _save_as_copies_and_retargets(window, qapp, root, {first: left, second: right})
    finally:
        shutdown_main_window_for_test(window, qapp)


def _save_as_copies_and_retargets(
    window: MainWindow, qapp: QApplication, root: Path, surfaces: dict
) -> None:
    """Save As writes a new .ui and ui_<name>.py, retitles the tab, and leaves
    the old pair, its breakpoints and its history alone. The next Ctrl+S
    writes the new file."""
    active = window._editor_manager.active_tab()  # noqa: SLF001
    assert active is not None
    source = Path(active.file_path)
    surface = surfaces[source]
    old_ui = source.read_text(encoding="utf-8")
    old_module = (source.parent / ("ui_%s.py" % source.stem)).read_text(encoding="utf-8")
    breakpoints = window._debug_control_workflow.breakpoint_store  # noqa: SLF001
    breakpoints.set_line_enabled(str(source), 3, enabled=True)
    _dirty(surface, "Copied text")
    copy = root / "forms" / "copy_form.ui"
    with patch(
        "app.shell.save_workflow.QFileDialog.getSaveFileName",
        return_value=(str(copy), "UI forms (*.ui)"),
    ):
        registry = window.menu_registry
        assert registry is not None
        save_as = registry.action("shell.action.file.saveAs")
        assert save_as is not None
        save_as.trigger()
    _pump(qapp, 20)
    assert "Copied text" in copy.read_text(encoding="utf-8")
    assert (copy.parent / "ui_copy_form.py").is_file()
    assert source.read_text(encoding="utf-8") == old_ui
    assert (source.parent / ("ui_%s.py" % source.stem)).read_text(encoding="utf-8") == old_module
    assert breakpoints.lines_for_file(str(source)) == {3}
    assert breakpoints.lines_for_file(str(copy)) == set()
    moved = window._editor_manager.active_tab()  # noqa: SLF001
    assert moved is not None and Path(moved.file_path) == copy
    tabs = window._editor_tabs_widget  # noqa: SLF001
    assert tabs is not None
    assert tabs.tabText(tabs.currentIndex()).startswith("copy_form.ui")
    _dirty(surface, "Next save")
    QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier)
    _pump(qapp, 20)
    assert "Next save" in copy.read_text(encoding="utf-8")
    assert source.read_text(encoding="utf-8") == old_ui


@pytest.mark.parity("R3-16")
@pytest.mark.timeout(60)
def test_closing_a_dirty_form_tab_asks_before_discard(tmp_path: Path, qapp: QApplication) -> None:
    """Closing a dirty form tab prompts. Discard closes it."""
    _require()
    path = tmp_path / "invoice.ui"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open(window, qapp, path)
        _dirty(surface, "Unsaved")
        seen = _arm_discard(qapp)
        QTest.keyClick(window, Qt.Key_W, Qt.ControlModifier)
        _pump(qapp, 30)
        assert seen["clicked"]
        assert window._tab_content_registry.surface_for_path(str(path)) is None  # noqa: SLF001
        assert "Unsaved" not in path.read_text(encoding="utf-8")
    finally:
        shutdown_main_window_for_test(window, qapp)


@pytest.mark.parity("R3-16")
@pytest.mark.timeout(60)
def test_quitting_with_a_dirty_form_asks_before_discard(tmp_path: Path, qapp: QApplication) -> None:
    """Quit with a dirty form prompts. Discard leaves the file untouched."""
    _require()
    path = tmp_path / "invoice.ui"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    try:
        surface = _open(window, qapp, path)
        _dirty(surface, "Unsaved")
        seen = _arm_discard(qapp)
        window.close()
        _pump(qapp, 20)
        assert seen["clicked"]
        assert "Unsaved" not in path.read_text(encoding="utf-8")
        assert window._tab_content_registry.surface_for_path(str(path)) is None  # noqa: SLF001
    finally:
        shutdown_main_window_for_test(window, qapp)
