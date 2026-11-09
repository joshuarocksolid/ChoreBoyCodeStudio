# pyright: reportAttributeAccessIssue=false
"""Saving, a toast, and a Problems update leave focus where the user put it.

UX-PRIN-006, OUT-008, FEED-002. Enter committing a rename may return focus
to that row. Nothing else may move it.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core.models import LoadedProject, ProjectMetadata  # noqa: E402
from app.features.form_builder.engine.commands.catalog import SetProperty  # noqa: E402
from app.features.form_builder.engine.diagnostics import (  # noqa: E402
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.engine.ui4.values import StringValue  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtCore import QObject, QPoint, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLineEdit, QTreeWidget, QTreeWidgetItem, QWidget  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text"><string>OK</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


class _FocusLog(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.changes: List[Tuple[str, str]] = []
        self._label = ""

    def set_label(self, label: str) -> None:
        self._label = label

    def note(self, _old: object, new: object) -> None:
        self.changes.append((self._label, _name(new)))


def _name(widget: object) -> str:
    if widget is None:
        return ""
    object_name = getattr(widget, "objectName", lambda: "")()
    if object_name:
        return str(object_name)
    return type(widget).__name__


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


def _open(window: MainWindow, qapp: QApplication, path: Path) -> object:
    path.write_text(_FORM, encoding="utf-8")
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


def _pump(qapp: QApplication) -> None:
    for _ in range(8):
        qapp.processEvents()


@pytest.mark.timeout(60)
def test_save_toast_and_problems_do_not_steal_focus(tmp_path: Path, qapp: QApplication) -> None:
    _require()
    root = tmp_path / "shop"
    path = root / "forms" / "invoice.ui"
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    log = _FocusLog()
    qapp.focusChanged.connect(log.note)
    try:
        _load(window, root)
        surface = _open(window, qapp, path)
        stolen: List[str] = []
        stolen.extend(_exercise(window, qapp, surface, log, path, "outline"))
        stolen.extend(_exercise(window, qapp, surface, log, path, "inspector"))
        stolen.extend(_exercise(window, qapp, surface, log, path, "canvas"))
        assert stolen == [], "\n".join(stolen)
    finally:
        qapp.focusChanged.disconnect(log.note)
        shutdown_main_window_for_test(window, qapp)


def _load(window: MainWindow, root: Path) -> None:
    (root / "forms").mkdir(parents=True)
    (root / "cbcs").mkdir()
    window._loaded_project = LoadedProject(  # noqa: SLF001
        project_root=str(root.resolve()),
        manifest_path=str((root / "cbcs" / "project.json").resolve()),
        metadata=ProjectMetadata(schema_version=1, name="Shop", default_entry="forms/invoice.ui"),
        entries=[],
    )


def _exercise(
    window: MainWindow,
    qapp: QApplication,
    surface: object,
    log: _FocusLog,
    path: Path,
    home: str,
) -> List[str]:
    stolen = []
    focus = _place(surface, qapp, home)
    assert focus is not None
    home_name = _name(focus)
    steps = (
        ("save", lambda: _save(window, qapp, surface, path)),
        ("toast", lambda: _paste(qapp, surface, focus, home)),
        ("problems", lambda: _add_problem(window, surface, qapp)),
        ("rename", lambda: _rename(surface, qapp, home)),
    )
    for label, action in steps:
        focus = _place(surface, qapp, home)
        assert focus is not None
        home_name = _name(focus)
        log.changes.clear()
        log.set_label(label)
        action()
        _pump(qapp)
        stolen.extend(_unexpected(log.changes, home, home_name, label))
    return stolen


def _unexpected(
    changes: List[Tuple[str, str]],
    home: str,
    home_name: str,
    label: str,
) -> List[str]:
    allowed = {home_name}
    if label == "rename" and home == "outline":
        allowed.add("formBuilder.structure")
        allowed.add("formBuilder.outlineRename")
    if label == "rename" and home == "inspector":
        allowed.add("formBuilder.inspectorName")
    if label == "rename" and home == "canvas":
        allowed.add("QLineEdit")
        allowed.add("formBuilder.outlineRename")
        # Double-click on a button opens the method page (UX D8).
        allowed.add("formBuilder.eventPickerSearch")
        allowed.add("formBuilder.eventPickerMethod")
    found = []
    for step, name in changes:
        if name not in allowed and name != home_name:
            found.append("%s/%s moved focus to %s" % (home, step, name or "(none)"))
    return found


def _place(surface: object, qapp: QApplication, home: str) -> Optional[QWidget]:
    if home == "outline":
        tree = surface.findChild(QTreeWidget, "formBuilder.structure")  # type: ignore[attr-defined]
        assert tree is not None
        tree.setFocus()
        item = tree.topLevelItem(0)
        assert item is not None
        tree.setCurrentItem(item)
        qapp.processEvents()
        QTest.keyClick(tree, Qt.Key_F2)
        qapp.processEvents()
        editor = qapp.focusWidget()
        assert isinstance(editor, QLineEdit)
        return editor
    if home == "inspector":
        name = surface.findChild(QLineEdit, "formBuilder.inspectorName")  # type: ignore[attr-defined]
        assert name is not None
        name.setFocus()
        qapp.processEvents()
        return name
    canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
    assert canvas is not None
    canvas.setFocus()
    qapp.processEvents()
    return canvas


def _save(window: MainWindow, qapp: QApplication, surface: object, path: Path) -> None:
    session = surface.session  # type: ignore[attr-defined]
    button = session.document.by_name("okButton")[0]
    session.log.execute(SetProperty(button, "text", StringValue("Focus saved")))
    QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier)
    _pump(qapp)
    tab = window._editor_manager.active_tab()  # noqa: SLF001
    assert tab is not None and tab.is_dirty is False
    assert "Focus saved" in path.read_text(encoding="utf-8")
    assert (path.parent / ("ui_%s.py" % path.stem)).is_file()


def _paste(qapp: QApplication, surface: object, focus: QWidget, home: str) -> None:
    if isinstance(focus, QLineEdit):
        # The outline rename editor and the inspector name field take the key,
        # so this proves a text paste. The canvas home runs the form paste.
        qapp.clipboard().setText("paste-token")
        QTest.keyClick(focus, Qt.Key_V, Qt.ControlModifier)
        assert "paste-token" in focus.text()
        return
    session = surface.session  # type: ignore[attr-defined]
    button = session.document.by_name("okButton")[0]
    session.selection.set((button,), current=button, source=SelectionSource.CANVAS)
    before = {node.object_name for node in session.document.iter_preorder() if hasattr(node, "object_name")}
    QTest.keyClick(focus, Qt.Key_C, Qt.ControlModifier)
    _pump(qapp)
    QTest.keyClick(focus, Qt.Key_V, Qt.ControlModifier)
    _pump(qapp)
    sentence = str(getattr(surface, "_gesture_sentence", ""))
    toast = surface.findChild(QWidget, "formBuilder.toastText")  # type: ignore[attr-defined]
    toast_text = "" if toast is None else str(getattr(toast, "text", lambda: "")())
    assert "Pasted" in sentence or "Pasted" in toast_text, sentence or toast_text or "paste had no effect"
    after = {node.object_name for node in session.document.iter_preorder() if hasattr(node, "object_name")}
    assert after - before


def _add_problem(window: MainWindow, surface: object, qapp: QApplication) -> None:
    session = surface.session  # type: ignore[attr-defined]
    session.diagnostics.publish(
        "names",
        (
            FormDiagnostic(
                code="FB010",
                severity=Severity.ERROR,
                message="Another widget is already called okButton.",
                location=DiagnosticLocation(object_name="okButton"),
                source="names",
            ),
        ),
    )
    _pump(qapp)
    panel = window._problems_panel  # noqa: SLF001
    assert panel is not None
    texts = _tree_text(panel.tree_widget())
    assert "Another widget is already called okButton." in texts


def _tree_text(tree: QTreeWidget) -> str:
    found: List[str] = []

    def walk(item: QTreeWidgetItem) -> None:
        found.append(" ".join(item.text(column) for column in range(item.columnCount())))
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                walk(child)

    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item is not None:
            walk(item)
    return "\n".join(found)


def _rename(surface: object, qapp: QApplication, home: str) -> None:
    session = surface.session  # type: ignore[attr-defined]
    if home == "outline":
        editor = surface.findChild(QLineEdit, "formBuilder.outlineRename")  # type: ignore[attr-defined]
        assert editor is not None
        editor.setText("okFromOutline")
        QTest.keyClick(editor, Qt.Key_Return)
        qapp.processEvents()
        assert session.document.by_name("okFromOutline")
        return
    if home == "inspector":
        name = surface.findChild(QLineEdit, "formBuilder.inspectorName")  # type: ignore[attr-defined]
        assert name is not None
        name.setText("okFromInspector")
        QTest.keyClick(name, Qt.Key_Return)
        qapp.processEvents()
        assert session.document.by_name("okFromInspector")
        return
    canvas = surface.findChild(QWidget, "formBuilder.canvas")  # type: ignore[attr-defined]
    assert canvas is not None
    QTest.keyClick(canvas, Qt.Key_F2)
    qapp.processEvents()
    editor = surface.findChild(QLineEdit, "formBuilder.outlineRename")  # type: ignore[attr-defined]
    if editor is not None and qapp.focusWidget() is editor:
        # Canvas F2 renames the current widget, then Esc returns to the canvas.
        QTest.keyClick(editor, Qt.Key_Escape)
        qapp.processEvents()
    else:
        assert getattr(surface, "_inert_note", "") == "F2 renames the selected outline row."
    button = canvas.page_widget().findChild(QWidget, "okButton")
    assert button is not None
    center = button.mapTo(canvas.page_widget(), button.rect().center())
    proxy = canvas.page_widget().graphicsProxyWidget()
    assert proxy is not None
    port = canvas.mapFromScene(proxy.mapToScene(QPoint(center.x(), center.y())))
    QTest.mouseDClick(canvas.viewport(), Qt.LeftButton, Qt.NoModifier, port)
    qapp.processEvents()
    assert qapp.focusWidget() is not None
