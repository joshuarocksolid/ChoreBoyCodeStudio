# pyright: reportAttributeAccessIssue=false
"""M8.0s Data pane and inspector Data tab are built from registered sections."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QLabel, QWidget

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.qtside.data_panel.panel import DataPanel
from app.features.form_builder.qtside.data_panel import sections_ext as panel_sections
from app.features.form_builder.qtside.inspector.data_page import DataPage
from app.features.form_builder.qtside.inspector import data_ext
from tests.form_builder.engine.test_m6_1a_events import form
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = pytest.mark.unit


class _Host(QWidget):
    def __init__(self, document: object) -> None:
        super().__init__()
        self.session = SimpleNamespace(document=document)


def test_registered_sections_are_what_the_panels_show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp) -> None:
    del qapp
    panel_package = make_package(
        tmp_path,
        monkeypatch,
        "m80s_panel",
        {
            "probe": """
                from app.qt.QtWidgets import QLabel
                from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection

                def register(registry):
                    registry.add(PanelSection(
                        "probe", 10,
                        lambda host: QLabel("Probe section", host),
                        lambda doc: True,
                    ))
            """
        },
    )
    data_package = make_package(
        tmp_path,
        monkeypatch,
        "m80s_data",
        {
            "probe": """
                from app.qt.QtWidgets import QLabel
                from app.features.form_builder.qtside.inspector.data_ext import DataSection

                def register(registry):
                    registry.add(DataSection(
                        "probe", 5,
                        lambda parent: QLabel("Probe data", parent),
                        lambda class_name: True,
                    ))
            """
        },
    )
    try:
        panel_sections.reset_default_registry()
        data_ext.reset_default_registry()
        monkeypatch.setattr(
            "app.features.form_builder.qtside.data_panel.panel.default_registry",
            lambda: panel_sections.load_sections(panel_package),
        )
        monkeypatch.setattr(
            "app.features.form_builder.qtside.inspector.data_page.default_registry",
            lambda: data_ext.load_sections(data_package),
        )
        document = read_ui(form(), allocator=IdAllocator()).document
        panel = DataPanel(_Host(document))
        assert panel.findChild(QLabel).text() == "Probe section"
        page = DataPage(panel)
        page.paint("QLineEdit")
        assert page.findChild(QLabel).text() == "Probe data"
    finally:
        panel_sections.reset_default_registry()
        data_ext.reset_default_registry()
        forget_package("m80s_panel")
        forget_package("m80s_data")


def test_empty_data_surfaces_say_the_unbound_sentences(qapp) -> None:
    del qapp
    document = read_ui(form(), allocator=IdAllocator()).document
    panel = DataPanel(_Host(document))
    sentence = panel.findChild(QLabel, "formBuilder.data.sentence")
    assert sentence is not None and sentence.text() == "This form isn't connected to a database."
    connect = panel.findChild(QWidget, "formBuilder.data.connect")
    assert connect is not None and connect.isEnabled() is False
    page = DataPage(panel)
    page.paint("QLabel")
    assert page.findChild(QLabel, "formBuilder.inspectorData.sentence").text() == (
        "Labels and layouts aren't bound. Select a field."
    )
    page.paint("QLineEdit")
    assert page.findChild(QLabel, "formBuilder.inspectorData.notBound").text() == "Not bound"
