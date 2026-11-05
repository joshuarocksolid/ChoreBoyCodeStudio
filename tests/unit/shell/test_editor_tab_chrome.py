"""A second edit of an already-dirty tab does not ask the host to lay out."""

from __future__ import annotations

import pytest

from app.editors.editor_tab import EditorTabState
from app.qt.QtCore import QEvent, QObject
from app.qt.QtWidgets import QTabWidget, QWidget
from app.shell.editor_tabs_coordinator import EditorTabsCoordinator

pytestmark = pytest.mark.usefixtures("qapp")


def test_second_dirty_present_sends_no_layout_request() -> None:
    host = QWidget()
    host.setObjectName("shell.editorGroupsHost")
    tabs = QTabWidget(host)
    tabs.addTab(QWidget(tabs), "form.ui")
    tab = EditorTabState("/tmp/form.ui", "form.ui", "saved", "edited")
    assert tab.is_dirty
    coordinator = EditorTabsCoordinator(object())
    coordinator.present_tab_at(0, tab, tabs=tabs)

    requests = {"n": 0}
    kind = getattr(getattr(QEvent, "Type", QEvent), "LayoutRequest")

    class _Count(QObject):
        def eventFilter(self, _watched: object, event: object) -> bool:  # noqa: N802
            if event.type() == kind:  # type: ignore[attr-defined]
                requests["n"] += 1
            return False

    counter = _Count()
    host.installEventFilter(counter)
    tabs.installEventFilter(counter)
    coordinator.present_tab_at(0, tab, tabs=tabs)
    assert tabs.tabText(0) == "form.ui *"
    assert requests["n"] == 0
    host.deleteLater()
