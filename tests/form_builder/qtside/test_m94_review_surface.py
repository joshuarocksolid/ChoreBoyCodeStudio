# pyright: reportAttributeAccessIssue=false
"""Status text, a hidden inspector, and a pane moved to its rail stay in step with the form."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.integration.layout import RAIL_WIDTH, WorkbenchMemory, plan_workbench
from app.qt.QtWidgets import QApplication, QLineEdit, QWidget
from tests.form_builder.engine.test_m94_caption_patch import _ROW
from tests.form_builder.qtside.test_canvas_status import _flush
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp"), pytest.mark.timeout(300)]


def test_status_sentence_follows_a_selected_fields_caption(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(1100, 720)
    surface = _open(parent, _ROW, tmp_path / "invoice.ui")
    parent.show()
    _flush()
    try:
        assert surface.select_object("emailEdit")
        _flush()
        surface.narrate("")
        before = surface.editor_status_sentence()
        assert before.startswith("Customer")
        document = surface._session.document  # noqa: SLF001
        label = document.by_name("customerLabel")[0]
        surface._session.log.execute(SetProperty(label, "text", StringValue("Invoice")))  # noqa: SLF001
        _flush()
        assert surface.editor_status_sentence().startswith("Invoice")
    finally:
        surface.release()
        parent.deleteLater()
        _flush()


def test_hidden_inspector_keeps_the_edit_before_a_spacing_change(tmp_path: Path) -> None:
    parent = QWidget()
    parent.resize(1100, 720)
    surface = _open(parent, _ROW, tmp_path / "invoice.ui")
    parent.show()
    _flush()
    try:
        assert surface.select_object("emailEdit")
        _flush()
        inspector = surface._workbench.inspector  # noqa: SLF001
        inspector.hide()
        _flush()
        document = surface._session.document  # noqa: SLF001
        edit = document.by_name("emailEdit")[0]
        surface._session.log.execute(SetProperty(edit, "text", StringValue("ada@shop")))  # noqa: SLF001
        layout = document.by_name("formLayout")[0]
        surface._session.log.execute(SetProperty(layout, "spacing", NumberValue(18)))  # noqa: SLF001
        inspector.show()
        _flush()
        row = inspector.findChild(QWidget, "formBuilder.row.text")
        assert row is not None
        editors = [editor.text() for editor in row.findChildren(QLineEdit)]
        assert "ada@shop" in editors
    finally:
        surface.release()
        parent.deleteLater()
        _flush()


def test_moving_the_inspector_to_its_rail_refits_without_a_window_resize(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    parent.resize(1400, 800)
    surface = _open(parent, _ROW, tmp_path / "invoice.ui")
    parent.show()
    surface.resize(1400, 800)
    _flush()
    try:
        bench = surface._workbench  # noqa: SLF001
        plan = plan_workbench(1400, 800, WorkbenchMemory())
        bench.apply_plan(plan)
        qapp.processEvents()
        docked = bench._splitter.sizes()  # noqa: SLF001
        assert docked[2] > RAIL_WIDTH + 40
        grown = docked[0] + 80
        bench._left_stack.setMinimumWidth(grown)  # noqa: SLF001
        qapp.processEvents()
        assert bench._splitter.sizes()[0] >= grown  # noqa: SLF001
        rail = dataclasses.replace(
            plan,
            density="rail",
            inspector_docked=False,
            inspector_width=RAIL_WIDTH,
        )
        bench.apply_plan(rail)
        qapp.processEvents()
        assert bench._splitter.sizes()[2] <= RAIL_WIDTH + 8  # noqa: SLF001
    finally:
        surface.release()
        parent.deleteLater()
        _flush()
