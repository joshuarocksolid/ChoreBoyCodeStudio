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

from app.features.form_builder.engine.diagnostics import (  # noqa: E402
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.qt.QtCore import QObject, Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import QApplication, QLineEdit, QTreeWidget, QWidget  # noqa: E402
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
    window._center_stack.setCurrentIndex(1)  # noqa: SLF001
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
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    log = _FocusLog()
    qapp.focusChanged.connect(log.note)
    try:
        surface = _open(window, qapp, tmp_path / "invoice.ui")
        stolen: List[str] = []
        stolen.extend(_exercise(window, qapp, surface, log, "outline"))
        stolen.extend(_exercise(window, qapp, surface, log, "inspector"))
        stolen.extend(_exercise(window, qapp, surface, log, "canvas"))
        assert stolen == [], "\n".join(stolen)
    finally:
        qapp.focusChanged.disconnect(log.note)
        shutdown_main_window_for_test(window, qapp)


def _exercise(
    window: MainWindow,
    qapp: QApplication,
    surface: object,
    log: _FocusLog,
    home: str,
) -> List[str]:
    stolen = []
    focus = _place(surface, qapp, home)
    assert focus is not None
    home_name = _name(focus)
    for label, action in (
        ("save", lambda: QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier)),
        ("toast", lambda: QTest.keyClick(focus, Qt.Key_V, Qt.ControlModifier)),
        ("problems", lambda: _add_problem(surface)),
        ("rename", lambda: _rename(surface, qapp, home)),
    ):
        _place(surface, qapp, home)
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


def _add_problem(surface: object) -> None:
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


def _rename(surface: object, qapp: QApplication, home: str) -> None:
    if home != "outline":
        return
    editor = surface.findChild(QLineEdit, "formBuilder.outlineRename")  # type: ignore[attr-defined]
    assert editor is not None
    QTest.keyClick(editor, Qt.Key_Return)
    qapp.processEvents()
