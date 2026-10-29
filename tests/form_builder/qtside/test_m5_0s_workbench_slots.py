# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Workbench slots: a left section with Alt+5, a drawer under the canvas, a split beside it."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List

import pytest

import app.features.form_builder.integration.workbench_ext as ext
from app.features.form_builder.integration.workbench_ext import LeftSection, load_workbench_contributors
from app.qt.QtWidgets import QLabel, QListWidget, QShortcut, QSplitter, QTabWidget, QToolButton, QWidget
from tests.form_builder.m5_0s_support import forget_package, make_package
from tests.unit.features.form_builder.test_workbench import _FORM, _open

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_PACKAGE = "m5_workbench_probe"

_LANE = """
    from app.qt.QtWidgets import QListWidget
    from app.features.form_builder.integration.workbench_ext import LeftSection

    SHOW = [False]
    SEEN = []

    def _build(workbench):
        widget = QListWidget()
        widget.setObjectName("probe.actions")
        return widget

    def register(slots):
        slots.add_left_section(LeftSection("actions", "Actions", _build, order=30,
                                           shown=lambda session: SHOW[0], keys="Alt+5"))
        slots.on_workbench(SEEN.append)
"""


@pytest.fixture()
def lane(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    package = make_package(tmp_path, monkeypatch, _PACKAGE, {"actions": _LANE})
    monkeypatch.setattr(ext, "_DEFAULT", load_workbench_contributors(package))
    yield package.actions
    forget_package(_PACKAGE)


def _open_sized(qapp, tmp_path: Path, width: int, height: int):  # type: ignore[no-untyped-def]
    host = QWidget()
    surface = _open(host, _FORM, tmp_path / "invoice.ui")
    host.show()
    surface.show()
    host.resize(width, height)
    surface.resize(width, height)
    qapp.processEvents()
    return host, surface


def test_a_left_section_shows_with_the_form_takes_a_share_and_answers_alt_5(  # type: ignore[no-untyped-def]
    lane, qapp, tmp_path: Path
) -> None:
    host, surface = _open_sized(qapp, tmp_path, 1100, 800)
    try:
        bench = surface._workbench
        assert lane.SEEN == [bench]
        widget = bench.section_widget("actions")
        assert widget is not None and isinstance(widget, QListWidget)
        assert not widget.isVisibleTo(bench)
        assert not bench.focus_section("actions")
        lane.SHOW[0] = True
        bench.refresh(None, "keep")
        qapp.processEvents()
        split = bench.findChild(QSplitter, "formBuilder.leftSplitter")
        assert split.indexOf(widget) == 2 and widget.isVisibleTo(bench)
        sizes = split.sizes()
        assert abs(sizes[2] * 100 // sum(sizes) - 25) <= 3
        assert abs(sizes[0] * 100 // sum(sizes) - 40) <= 3
        keys = [shortcut for shortcut in bench.findChildren(QShortcut) if shortcut.key().toString() == "Alt+5"]
        assert len(keys) == 1
        keys[0].activated.emit()
        focus = qapp.focusWidget()
        assert widget.hasFocus() or (focus is not None and widget.isAncestorOf(focus))
        lane.SHOW[0] = False
        bench.refresh(None, "keep")
        assert not widget.isVisibleTo(bench)
    finally:
        surface.release()
        host.close()


def test_a_left_section_is_a_third_tab_at_short_heights_and_a_third_rail_button(  # type: ignore[no-untyped-def]
    lane, qapp, tmp_path: Path
) -> None:
    host, surface = _open_sized(qapp, tmp_path, 1100, 500)
    try:
        lane.SHOW[0] = True
        bench = surface._workbench
        bench.refresh(None, "keep")
        qapp.processEvents()
        tabs = bench.findChild(QTabWidget, "formBuilder.leftTabs")
        titles: List[str] = [tabs.tabText(index) for index in range(tabs.count())]
        assert titles == ["Outline", "Insert", "Actions"]
        assert tabs.isVisibleTo(bench)
        assert bench.focus_section("actions") and tabs.currentWidget() is bench.section_widget("actions")
        host.resize(1100, 800)
        surface.resize(1100, 800)
        qapp.processEvents()
        split = bench.findChild(QSplitter, "formBuilder.leftSplitter")
        assert split.indexOf(bench.section_widget("actions")) == 2 and not tabs.isVisibleTo(bench)
        host.resize(800, 800)
        surface.resize(800, 800)
        qapp.processEvents()
        rail = bench.findChild(QToolButton, "formBuilder.leftRail.actions")
        assert rail is not None and rail.accessibleName() == "Actions" and rail.isVisibleTo(bench)
    finally:
        surface.release()
        host.close()


def test_the_drawer_under_the_canvas_pushes_the_canvas_and_covers_it_at_short_heights(  # type: ignore[no-untyped-def]
    qapp, tmp_path: Path
) -> None:
    host, surface = _open_sized(qapp, tmp_path, 1100, 800)
    try:
        bench = surface._workbench
        drawer = QLabel("drawer")
        heard: List[int] = []
        bench.set_under_canvas_listener(heard.append)
        before = bench.canvas.height()
        assert bench.open_under_canvas("style", drawer, height=240)
        qapp.processEvents()
        assert bench.under_canvas_key() == "style" and drawer.isVisibleTo(bench)
        assert abs(drawer.height() - 240) <= 8
        assert bench.canvas.height() >= 200 and bench.canvas.height() < before
        bench.close_under_canvas()
        qapp.processEvents()
        assert not drawer.isVisibleTo(bench) and bench.under_canvas_key() == ""
        assert bench.canvas.height() >= before - 4
        host.resize(1100, 500)
        surface.resize(1100, 500)
        qapp.processEvents()
        full = bench.canvas.height()
        assert bench.open_under_canvas("style", drawer, height=240)
        qapp.processEvents()
        assert drawer.isVisibleTo(bench) and bench.canvas.height() == full
        column = bench.findChild(QSplitter, "formBuilder.canvasColumn")
        assert drawer.mapTo(bench, drawer.rect().bottomLeft()).y() <= column.mapTo(bench, column.rect().bottomLeft()).y() + 1
        bench.close_under_canvas()
    finally:
        surface.release()
        host.close()


def test_the_split_beside_the_canvas_refuses_when_the_canvas_would_be_too_narrow(  # type: ignore[no-untyped-def]
    qapp, tmp_path: Path
) -> None:
    host, surface = _open_sized(qapp, tmp_path, 1500, 800)
    try:
        bench = surface._workbench
        code = QLabel("code")
        assert bench.open_beside_canvas("code", code)
        qapp.processEvents()
        assert code.isVisibleTo(bench) and bench.canvas.width() >= 360
        assert bench.beside_canvas_key() == "code"
        bench.close_beside_canvas()
        assert not code.isVisibleTo(bench)
        assert not bench.open_beside_canvas("code", code, min_canvas=5000)
        assert bench.beside_canvas_key() == ""
    finally:
        surface.release()
        host.close()
