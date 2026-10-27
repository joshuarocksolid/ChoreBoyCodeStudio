# pyright: reportAttributeAccessIssue=false
"""Sizing signals that arrive after the editor or the session is gone."""

from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType
from typing import List, Optional, Tuple, Type

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.install import form_builder_enabled  # noqa: E402
from app.features.form_builder.qtside.inspector.api import GroupId  # noqa: E402
from app.features.form_builder.qtside.inspector.pane import InspectorPane  # noqa: E402
from app.qt.QtWidgets import QApplication, QSpinBox, QWidget  # noqa: E402
from app.qt.qt_compat import delete_now  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402
from testing.main_window_shutdown import shutdown_main_window_for_test  # noqa: E402

pytestmark = pytest.mark.unit

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>200</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="grow">
     <property name="text"><string>Grow</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _open(window: MainWindow, qapp: QApplication, path: Path, text: str) -> object:
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


def _require() -> None:
    if not form_builder_enabled():
        pytest.skip("form builder is registered on PySide6")


class _Hook:
    def __init__(self) -> None:
        self.caught: List[Tuple[Type[BaseException], BaseException]] = []
        self._previous = sys.excepthook

    def __enter__(self) -> "_Hook":
        def hook(
            exc_type: Type[BaseException], exc: BaseException, _tb: Optional[TracebackType]
        ) -> None:
            self.caught.append((exc_type, exc))

        sys.excepthook = hook
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        sys.excepthook = self._previous


def _focus_share(surface: object, qapp: QApplication) -> QSpinBox:
    session = surface.session  # type: ignore[attr-defined]
    found = session.document.by_name("grow")
    assert found
    session.selection.set((found[0],), source=SelectionSource.PROGRAM)
    pane = surface.findChild(InspectorPane, "formBuilder.inspector")  # type: ignore[attr-defined]
    assert isinstance(pane, InspectorPane)
    pane.set_group_expanded(GroupId.SIZE, True)
    pane.flush()
    qapp.processEvents()
    spin = pane.findChild(QSpinBox, "formBuilder.size.share.v.value")
    assert isinstance(spin, QSpinBox) and spin.isVisible()
    spin.setFocus()
    qapp.processEvents()
    focus = QApplication.focusWidget()
    assert focus is spin or spin.isAncestorOf(focus)
    live = surface._realizer.widget_for(found[0])  # noqa: SLF001
    assert isinstance(live, QWidget)
    live.resize(live.width() + 40, live.height() + 12)
    return spin


def test_closing_the_form_tab_with_the_share_spin_focused_raises_nothing(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    path = tmp_path / "form.ui"
    try:
        surface = _open(window, qapp, path, _FORM)
        _focus_share(surface, qapp)
        with _Hook() as hook:
            window._editor_tab_workflow.close_tab_discarding_edits(str(path))  # noqa: SLF001
            qapp.processEvents()
        assert hook.caught == []
    finally:
        shutdown_main_window_for_test(window, qapp)


def test_deleting_the_size_editor_with_the_share_spin_focused_raises_nothing(
    tmp_path: Path, qapp: QApplication
) -> None:
    _require()
    window = MainWindow(state_root=str((tmp_path / "state").resolve()))
    path = tmp_path / "form.ui"
    try:
        surface = _open(window, qapp, path, _FORM)
        spin = _focus_share(surface, qapp)
        body = spin.parent()
        while body is not None and body.objectName() != "formBuilder.sizeBody":
            body = body.parent()
        assert body is not None and body.objectName() == "formBuilder.sizeBody"
        with _Hook() as hook:
            delete_now(body)
            qapp.processEvents()
        assert hook.caught == []
    finally:
        shutdown_main_window_for_test(window, qapp)
