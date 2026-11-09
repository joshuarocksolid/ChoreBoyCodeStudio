"""The reference form is a pure function and the reader accepts it."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.perf.reference import EDIT_NAME, reference_form

_CLASSES = (
    "QMainWindow",
    "QTabWidget",
    "QGroupBox",
    "QSplitter",
    "QMenuBar",
    "QMenu",
    "QToolBar",
    "QStatusBar",
    "QFormLayout",
    "QGridLayout",
    "QVBoxLayout",
    "QHBoxLayout",
)


@pytest.mark.parametrize("count", (300, 600, 1000))
def test_reference_form_has_that_many_widgets_and_reads(count: int) -> None:
    form = reference_form(count, seed=1505)
    assert form.xml.count("<widget ") == count
    document = read_ui(form.xml, allocator=IdAllocator()).document
    widgets = [node for node in document.iter_preorder() if node.kind == "widget"]
    assert len(widgets) == count
    assert document.by_name(EDIT_NAME)
    for class_name in _CLASSES:
        assert 'class="%s"' % class_name in form.xml
    assert "<action name=" in form.xml
    assert form.xml == reference_form(count, seed=1505).xml
    assert form.xml != reference_form(count, seed=1506).xml
