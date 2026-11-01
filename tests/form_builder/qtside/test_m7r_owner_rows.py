# pyright: reportAttributeAccessIssue=false
"""Owner-facing rows: display names, spoken state, wrapped steps, code-line breaks."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.ipc.protocol import TryStart
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, WidgetFacts
from app.features.form_builder.engine.logic.uses import PanelRow, Use
from app.features.form_builder.integration.preview_notice import preview_request
from app.features.form_builder.qtside.inspector.behavior_ext.events import _Row, _elide_place
from app.features.form_builder.qtside.logic_panel.panel import _face
from app.features.form_builder.qtside.logic_panel.rows import LogicRow, break_opportunities
from app.features.form_builder.qtside.logic_panel.uses_view import UsesDialog
from app.features.form_builder.qtside.preview.try_log import (
    TryEvent,
    TryLine,
    fold,
    names_from_env,
    source_label,
    source_of,
)
from app.features.form_builder.qtside.preview.what_ran import WhatRan
from app.features.form_builder.qtside.theme.chrome import default_chrome
from app.qt.QtGui import QFontDatabase, QFontMetrics, QTextOption
from app.qt.QtWidgets import QApplication, QLabel, QTreeWidget, QWidget
from tests.form_builder.qtside.test_m7_6_try import _Session, _invoice_text, _scope

pytestmark = pytest.mark.unit

_NAMES = {
    "lineTotalLabel": "Line total",
    "discountEdit": "Discount rate",
    "emailEdit": "Email",
    "saveButton": "Save",
}
_CALL = "self.ui.discountEdit.setEnabled(True)"
_STEP = "Check all fields (stops here if a field fails)"
_PLACE = "invoice_window.py:13"


@pytest.mark.parametrize(
    "ref,label",
    (
        ("lineTotalLabel:cbcsValue", "Line total · Value"),
        ("discountEdit:cbcsEnabledWhen", "Discount rate · Enabled when"),
        ("emailEdit:cbcsValidate", "Email · Checks"),
        ("saveButton: When clicked", "Save · When clicked"),
    ),
)
def test_source_column_uses_the_display_name(ref: str, label: str) -> None:
    assert source_label(ref, _NAMES) == label


def test_a_check_sentence_uses_the_display_name() -> None:
    lines = fold((TryEvent("check", "emailEdit:cbcsValidate", "Enter an email address"),), {}, {}, _NAMES)
    assert lines[0].sentence == "Check Email: Enter an email address"


def test_preview_start_carries_the_formula_env_names(tmp_path: Path) -> None:
    document, scope, path = _scope(tmp_path, _invoice_text())
    message = preview_request(_Session(document, scope), str(path), "v1", run_behavior=True)
    assert isinstance(message, TryStart)
    names = dict(message.display_names)
    assert names["saveButton"] == "Save"
    assert names["discountCheck"] == "Discount"
    assert names["qtySpin"] == "Qty"
    assert names["priceSpin"] == "Price"
    assert names["lineTotalLabel"] == "Line total"
    assert names["emailEdit"] == "Email"
    # discountCheck already says "Discount", so the edit's fallback is the split name.
    assert names["discountEdit"] == "discount edit"


def test_identical_rule_rows_collapse_and_other_lines_do_not(qapp: QApplication) -> None:
    del qapp
    refs = ("lineTotalLabel:cbcsValue", "discountEdit:cbcsEnabledWhen")
    rule = TryLine("Rules ran (2)", refs[0], source_of(refs[0]), "rule", details=refs)
    other = TryLine(
        "Rules ran (2)",
        "emailEdit:cbcsValidate",
        source_of("emailEdit:cbcsValidate"),
        "rule",
        details=("emailEdit:cbcsValidate", "saveButton: When clicked"),
    )
    check = TryLine(
        "Check Email: Enter an email address",
        "emailEdit:cbcsValidate",
        source_of("emailEdit:cbcsValidate"),
        "check",
    )
    view = WhatRan()
    view.set_names(_NAMES)
    for _ in range(4):
        view.add((rule,), 0)
    tree = view.findChild(QTreeWidget, "preview.whatRan.list")
    assert tree is not None
    assert tree.topLevelItemCount() == 1
    item = tree.topLevelItem(0)
    assert item.text(1) == "Rules ran (2) \u00d74"
    assert item.childCount() == 2
    assert item.child(0).text(1) == "Line total · Value"
    assert item.child(1).text(1) == "Discount rate · Enabled when"
    view.clear()
    view.add((rule,), 0)
    view.add((check,), 0)
    view.add((rule,), 0)
    assert tree.topLevelItemCount() == 3
    assert tree.topLevelItem(0).text(1) == "Rules ran (2)"
    assert tree.topLevelItem(1).text(1) == "Check Email: Enter an email address"
    assert tree.topLevelItem(1).text(2) == "Email · Checks"
    assert tree.topLevelItem(2).text(1) == "Rules ran (2)"
    view.clear()
    view.add((rule,), 0)
    view.add((other,), 0)
    assert tree.topLevelItemCount() == 2
    view.clear()
    view.add((check,), 0)
    view.add((check,), 0)
    assert tree.topLevelItemCount() == 2


def _env() -> FormulaEnv:
    return FormulaEnv.for_test(
        {
            "qtySpin": WidgetFacts("QSpinBox", "Qty"),
            "priceSpin": WidgetFacts("QDoubleSpinBox", "Price", decimals=2),
            "discountCheck": WidgetFacts("QCheckBox", "Discount"),
            "lineTotalLabel": WidgetFacts("QLabel", "Line total"),
            "discountEdit": WidgetFacts("QLineEdit", "Discount rate"),
            "emailEdit": WidgetFacts("QLineEdit", "Email"),
            "saveButton": WidgetFacts("QPushButton", "Save"),
        }
    )


def test_name_map_matches_the_inspector_display() -> None:
    names = dict(names_from_env(_env()))
    assert names["lineTotalLabel"] == "Line total"
    assert names["discountEdit"] == "Discount rate"
    assert names["emailEdit"] == "Email"
    assert names["saveButton"] == "Save"


@pytest.mark.parametrize(
    "widget,key,words,summary,display,aside,body",
    (
        ("lineTotalLabel", "cbcsValue", "Value", "qtySpin * priceSpin", "Line total", "Value · Qty × Price", ""),
        (
            "discountEdit",
            "cbcsEnabledWhen",
            "Enabled when",
            "discountCheck",
            "Discount rate",
            "Enabled when · Discount is checked",
            "",
        ),
        ("lineTotalLabel", "cbcsValue", "Value", "qtySpin.value()", "Line total", "Value", "qtySpin.value()"),
    ),
)
def test_state_row_speaks_and_keeps_a_code_line_when_it_cannot(
    qapp: QApplication,
    widget: str,
    key: str,
    words: str,
    summary: str,
    display: str,
    aside: str,
    body: str,
) -> None:
    del qapp
    use = Use("rule", "set", "rule", widget, summary, key, 0, "", 0, "", "")
    face = _face(PanelRow(use, "STATE", words, summary, False), display, "STATE", _env())
    assert face.title == display
    assert face.aside == aside
    assert face.tooltip == summary
    assert face.accessible.startswith("STATE, %s," % widget)
    host = QWidget()
    host.show()
    row = LogicRow(face, host)
    row.show()
    assert row.findChild(QLabel, "formBuilder.logic.rowTitle").text() == display
    assert row.findChild(QLabel, "formBuilder.logic.rowAside").text() == aside
    assert row.toolTip() == summary
    formula = row.formula()
    if body:
        assert face.code is True
        assert formula.isVisible()
        assert body in formula.text().replace("\u200b", "")
    else:
        assert face.code is False
        assert not formula.isVisible()


def test_step_sentence_wraps_in_full(qapp: QApplication) -> None:
    host = QWidget()
    host._chrome = default_chrome()  # type: ignore[attr-defined]
    host.resize(400, 200)
    host.show()
    row = _Row(host, "clicked", 0, _STEP, _STEP, False, False, False, "cbcsOnClicked")
    row.resize(180, 24)
    qapp.processEvents()
    label = row.findChild(QLabel)
    assert label is not None
    assert label.text() == _STEP
    assert "\u2026" not in label.text()
    assert label.wordWrap() is True
    assert label.hasHeightForWidth() is True
    assert label.heightForWidth(140) > label.fontMetrics().lineSpacing()
    assert row.minimumHeight() > label.fontMetrics().lineSpacing()


def test_place_link_middle_elides_the_file_and_keeps_the_line(qapp: QApplication) -> None:
    del qapp
    metrics = QFontMetrics(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
    full_width = metrics.horizontalAdvance(_PLACE)
    assert _elide_place(_PLACE, metrics, full_width + 40) == _PLACE
    shown = _elide_place(_PLACE, metrics, max(full_width - metrics.horizontalAdvance("window"), 48))
    assert shown.endswith(":13")
    assert shown != _PLACE
    left, mark, right = shown.partition("\u2026")
    assert mark == "\u2026"
    assert left
    file_tail = right[: -len(":13")]
    assert file_tail
    assert _PLACE.startswith(left)
    assert "invoice_window.py".endswith(file_tail)


@pytest.mark.parametrize(
    "text,broken",
    (
        (_CALL, "self\u200b.ui\u200b.discountEdit\u200b.setEnabled\u200b(True)"),
        ("qtySpin.value()", "qtySpin\u200b.value\u200b()"),
        ("setEnabled(...)", "setEnabled\u200b(...)"),
    ),
)
def test_break_opportunities_sit_before_a_dot_or_paren(text: str, broken: str) -> None:
    assert break_opportunities(text) == broken


def test_uses_and_the_logic_code_line_keep_identifiers_whole(qapp: QApplication) -> None:
    host = QWidget()
    host.show()
    use = Use("setEnabled", "set", "code", "discountEdit", _CALL, "", 0, "", 1, "invoice_window.py", "setEnabled")
    dialog = UsesDialog("discountEdit", "Discount rate", (use,), (_CALL,), {}, None)
    dialog.setFixedWidth(184)
    dialog.show()
    qapp.processEvents()
    uses_row = dialog.findChild(LogicRow, "formBuilder.logic.uses.row.0")
    assert uses_row is not None
    problem = Use(
        "setEnabled",
        "set",
        "code",
        "discountEdit",
        "setEnabled",
        "cbcsEnabledWhen",
        0,
        "",
        12,
        "invoice_window.py",
        "setEnabled",
    )
    face = _face(PanelRow(problem, "STATE", "Enabled when", "setEnabled", True), "Discount rate")
    logic = LogicRow(face, host)
    logic.setFixedWidth(184)
    qapp.processEvents()
    for formula in (uses_row.formula(), logic.formula()):
        text = formula.text()
        assert "\u200b.setEnabled\u200b(" in text
        assert "setEn\u200b" not in text
        _assert_identifier_stays_whole(text, "setEnabled")
        _assert_identifier_stays_whole(text, "discountEdit")


def _assert_identifier_stays_whole(text: str, identifier: str) -> None:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    metrics = QFontMetrics(font)
    width = metrics.horizontalAdvance(identifier) + 4
    assert metrics.horizontalAdvance(text.replace("\u200b", "")) > width
    for line in _wrapped_lines(text, width, font):
        visible = line.replace("\u200b", "")
        if identifier[:4] in visible:
            assert identifier in visible, (identifier, visible)


def _wrapped_lines(text: str, width: int, font: object) -> list:
    from app.qt.QtGui import QTextLayout

    option = QTextOption()
    option.setWrapMode(_wrap_mode())
    layout = QTextLayout(text, font)  # type: ignore[arg-type]
    layout.setTextOption(option)
    layout.beginLayout()
    lines = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1, width))
        start = line.textStart()
        lines.append(text[start : start + line.textLength()])
    layout.endLayout()
    assert len(lines) > 1, lines
    return lines


def _wrap_mode() -> object:
    mode = getattr(QTextOption, "WrapAtWordBoundaryOrAnywhere", None)
    if mode is None:
        mode = getattr(QTextOption.WrapMode, "WrapAtWordBoundaryOrAnywhere")
    return mode
