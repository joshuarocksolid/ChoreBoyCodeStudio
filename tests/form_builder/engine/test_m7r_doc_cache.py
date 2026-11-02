# pyright: reportAttributeAccessIssue=false
"""A freed document must not leave its cache for the next object at that address."""

from __future__ import annotations

import gc
from typing import Optional

from app.features.form_builder.engine.commands.catalog import SetLogic
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic import read_as_text
from app.features.form_builder.engine.logic.read_as_text import spoken_display
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.qtside.canvas.layers import logic_badges
from tests.form_builder.engine.commands._support import open_log

import pytest

pytestmark = pytest.mark.unit


def _caption_form(caption: str) -> UiDocument:
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ui version="4.0"><class>Alpha</class>'
        '<widget class="QDialog" name="Alpha">'
        '<widget class="QLabel" name="customerLabel">'
        '<property name="text"><string>%s</string></property>'
        '<property name="buddy"><cstring>emailEdit</cstring></property>'
        "</widget>"
        '<widget class="QLineEdit" name="emailEdit"/>'
        "</widget></ui>"
    ) % caption
    return read_ui(text, allocator=IdAllocator()).document


def test_spoken_names_do_not_follow_a_reused_document_id() -> None:
    first = _caption_form("Customer")
    assert spoken_display(first, "emailEdit") == "Customer"
    address = id(first)
    stolen = {"emailEdit": ("Customer", False)}
    del first
    gc.collect()
    second: Optional[UiDocument] = None
    for _try in range(50):
        candidate = _caption_form("Invoice")
        if id(candidate) == address:
            second = candidate
            break
        del candidate
        gc.collect()
    if second is None:
        second = _caption_form("Invoice")
        try:
            read_as_text._PREFERRED[(id(second), second.structure_revision)] = stolen  # type: ignore[index]
        except TypeError:
            pass
    assert spoken_display(second, "emailEdit") == "Invoice"


def _sale() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Sale</class>\n'
        ' <widget class="QDialog" name="Sale">\n'
        '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        '   <item>\n    <widget class="QLineEdit" name="nameEdit"/>\n   </item>\n'
        "  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n"
    )


def test_undo_of_a_rule_refreshes_the_badge_mark() -> None:
    log = open_log(_sale())
    document = log.document
    owner = document.by_name("nameEdit")[0]
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "qtySpin"))
    logic_badges._cached_mark(document, "nameEdit", ())
    log.execute(SetLogic(owner, "cbcsVisibleWhen", "priceSpin"))
    logic_badges._cached_mark(document, "nameEdit", ())
    assert log.undo()
    assert logic_badges._logic_text(document, "nameEdit") == "cbcsVisibleWhen=qtySpin"
    assert logic_badges._cached_mark(document, "nameEdit", ()) == logic_badges._mark(
        document, "nameEdit", ()
    )
    assert log.redo()
    assert logic_badges._logic_text(document, "nameEdit") == "cbcsVisibleWhen=priceSpin"
    assert logic_badges._cached_mark(document, "nameEdit", ()) == logic_badges._mark(
        document, "nameEdit", ()
    )
