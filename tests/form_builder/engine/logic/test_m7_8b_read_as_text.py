"""Read as text for the invoice fixture. A few sentences, not the whole page."""

from __future__ import annotations

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic.read_as_text import behavior_text, page_text
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.engine.logic.test_m7_8a_uses import invoice_text


def test_invoice_sentences_include_the_rule_and_the_total() -> None:
    doc = read_ui(invoice_text(), allocator=IdAllocator()).document
    sentences = behavior_text(doc)
    texts = [sentence.text for sentence in sentences]
    assert "Discount rate is enabled only when Discount is checked." in texts
    assert "Line total is always Qty \u00d7 Price." in texts
    assert any(sentence.section == "CHECKS" and "Enter an email address" in sentence.text for sentence in sentences)
    assert any(sentence.section == "EVENTS" and "call save_invoice" in sentence.text for sentence in sentences)
    assert not any("Call save_invoice()" in sentence.text for sentence in sentences)
    assert [sentence.number for sentence in sentences] == list(range(1, len(sentences) + 1))
    sections = []
    for sentence in sentences:
        if not sections or sections[-1] != sentence.section:
            sections.append(sentence.section)
    assert sections == ["STATE", "CHECKS", "EVENTS"]
    copied = page_text(sentences)
    assert "STATE" in copied.splitlines()
    assert "1. %s" % sentences[0].text in copied


def test_a_refused_formula_stays_in_backticks() -> None:
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ui version="4.0"><class>Note</class>'
        '<widget class="QDialog" name="Note">'
        '<widget class="QLineEdit" name="noteEdit">'
        '<property name="cbcsValue"><string>noteEdit.value()</string></property>'
        "</widget></widget></ui>"
    )
    doc = read_ui(text, allocator=IdAllocator()).document
    sentences = behavior_text(doc)
    assert any("is calculated as `noteEdit.value()`." in sentence.text for sentence in sentences)
