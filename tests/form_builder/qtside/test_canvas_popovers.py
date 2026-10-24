"""Problem text and the layout choices open as popovers, not dialogs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QApplication, QFrame, QMenu, QTabWidget, QWidget
from app.features.form_builder.engine.diagnostics import DiagnosticLocation, FormDiagnostic, Severity
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form
from app.shell.problems_panel import ProblemsPanel
from tests.unit.features.form_builder.test_workbench import _FORM, _open

pytestmark = pytest.mark.usefixtures("qapp")

_MESSAGE = "This name is already used."


def test_a_problem_opens_a_popover_when_the_panel_is_absent(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "popover")
    try:
        _publish(surface)
        button = surface._session.document.by_name("okButton")[0]  # type: ignore[attr-defined]  # noqa: SLF001
        surface.open_problem(button)
        _flush()
        popover = surface.findChild(QFrame, "formBuilder.problemPopover")
        assert isinstance(popover, QFrame)
        assert popover.isVisible()
        assert not popover.isWindow()
        assert _MESSAGE in popover.findChild(QWidget, "formBuilder.problemText").text()  # type: ignore[union-attr]
        assert popover.maximumWidth() == 480
    finally:
        _close(parent, surface)


def test_a_problem_reveals_the_problems_row_when_the_panel_has_it(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "panel")
    panel = ProblemsPanel()
    tabs = QTabWidget()
    tabs.addTab(QWidget(), "Output")
    tabs.addTab(panel, "Problems")
    tabs.setCurrentIndex(0)
    parent._problems_panel = panel  # type: ignore[attr-defined]
    parent._bottom_tabs_widget = tabs  # type: ignore[attr-defined]
    try:
        button = surface._session.document.by_name("okButton")[0]  # type: ignore[attr-defined]  # noqa: SLF001
        _publish(surface)
        rows = code_diagnostics_for_form(surface.form_path(), surface._session.diagnostics.all())  # type: ignore[attr-defined]  # noqa: SLF001
        panel.set_diagnostics(rows)
        _flush()
        surface.open_problem(button)
        _flush()
        assert tabs.currentWidget() is panel
        popover = surface.findChild(QFrame, "formBuilder.problemPopover")
        assert popover is not None and not popover.isVisible()
    finally:
        _close(parent, surface)


def test_the_layout_popover_lists_the_four_layouts(tmp_path: Path) -> None:
    parent, surface = _shown(tmp_path, "layout")
    try:
        root = surface._session.document.root.id  # type: ignore[attr-defined]  # noqa: SLF001
        surface.open_layout_popover(root)
        _flush()
        menu = surface.findChild(QMenu, "formBuilder.layoutPopover")
        assert isinstance(menu, QMenu)
        assert menu.isVisible()
        assert menu.toolTipsVisible()
        labels = [action.text() for action in menu.actions()]
        assert labels == ["Vertical", "Horizontal", "Grid", "Form"]
        for action in menu.actions():
            if not action.isEnabled():
                tip = action.toolTip()
                assert tip
                assert "M2" not in tip and "M3" not in tip
        modality = getattr(getattr(Qt, "WindowModality", Qt), "WindowModal")
        assert menu.windowModality() != modality
    finally:
        menu = surface.findChild(QMenu, "formBuilder.layoutPopover")
        if menu is not None:
            menu.close()
        _close(parent, surface)


def _shown(tmp_path: Path, name: str) -> tuple:
    parent = QWidget()
    parent.resize(900, 640)
    surface = _open(parent, _FORM, tmp_path / ("%s.ui" % name))
    surface.resize(900, 640)
    parent.show()
    surface.show()
    _flush()
    return parent, surface


def _publish(surface: QWidget) -> None:
    button = surface._session.document.by_name("okButton")[0]  # type: ignore[attr-defined]  # noqa: SLF001
    surface._session.diagnostics.publish(  # type: ignore[attr-defined]  # noqa: SLF001
        "names",
        (
            FormDiagnostic(
                code="FB003",
                severity=Severity.ERROR,
                message=_MESSAGE,
                location=DiagnosticLocation(node_id=button, object_name="okButton", line=4),
                source="names",
            ),
        ),
    )


def _close(parent: QWidget, surface: QWidget) -> None:
    surface.release()  # type: ignore[attr-defined]
    parent.deleteLater()
    _flush()


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()
