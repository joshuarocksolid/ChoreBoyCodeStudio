"""Golden sources for the formula compiler. Each case starts as text."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

import pytest

from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.formula import analyze, compile_formula, helper_table
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind, WidgetFacts
from app.features.form_builder.engine.project.window_facts import MethodFacts

Case = Tuple[str, str, str]


def _chain(name: str) -> Tuple[str, ...]:
    leaf = name.rsplit(".", 1)[-1]
    if leaf == name:
        return (name,)
    return (name, leaf)


def _facts(class_name: str, **kwargs: object) -> WidgetFacts:
    return WidgetFacts(class_name, **kwargs)  # type: ignore[arg-type]


WIDGETS = {
    "qty": _facts("QSpinBox"),
    "qtyBlank": _facts("QSpinBox", allow_blank=True),
    "slider": _facts("QSlider"),
    "dial": _facts("QDial"),
    "progress": _facts("QProgressBar"),
    "price": _facts("QDoubleSpinBox", decimals=2),
    "amount": _facts("QDoubleSpinBox", decimals=2, prefix="$"),
    "rate": _facts("QDoubleSpinBox", decimals=3),
    "rateBlank": _facts("QDoubleSpinBox", decimals=4, allow_blank=True),
    "nameEdit": _facts("QLineEdit", kind="text"),
    "plainEdit": _facts("QLineEdit"),
    "weirdEdit": _facts("QLineEdit", kind="nope"),
    "moneyEdit": _facts("QLineEdit", kind="money"),
    "priceEdit": _facts("QLineEdit", kind="money"),
    "pctEdit": _facts("QLineEdit", kind="percent"),
    "wholeEdit": _facts("QLineEdit", kind="whole"),
    "numEdit": _facts("QLineEdit", kind="number:3"),
    "num0Edit": _facts("QLineEdit", kind="number:0"),
    "dateLine": _facts("QLineEdit", kind="date"),
    "timeLine": _facts("QLineEdit", kind="time"),
    "caption": _facts("QLabel", kind="text"),
    "note": _facts("QLabel"),
    "weirdLabel": _facts("QLabel", kind="nope"),
    "moneyLabel": _facts("QLabel", kind="money"),
    "wholeLabel": _facts("QLabel", kind="whole"),
    "numLabel": _facts("QLabel", kind="number:2"),
    "pctLabel": _facts("QLabel", kind="percent"),
    "dateLabel": _facts("QLabel", kind="date"),
    "timeLabel": _facts("QLabel", kind="time"),
    "notes": _facts("QPlainTextEdit", kind="text"),
    "notesBare": _facts("QPlainTextEdit"),
    "notesMoney": _facts("QPlainTextEdit", kind="money"),
    "notesWhole": _facts("QPlainTextEdit", kind="whole"),
    "notesNum": _facts("QPlainTextEdit", kind="number:1"),
    "notesPct": _facts("QPlainTextEdit", kind="percent"),
    "notesDate": _facts("QPlainTextEdit", kind="date"),
    "notesTime": _facts("QPlainTextEdit", kind="time"),
    "body": _facts("QTextEdit", kind="text"),
    "bodyMoney": _facts("QTextEdit", kind="money"),
    "ok": _facts("QCheckBox"),
    "maybe": _facts("QCheckBox", tristate=True),
    "radio": _facts("QRadioButton"),
    "extra": _facts("QRadioButton"),
    "group": _facts("QButtonGroup"),
    "combo": _facts("QComboBox"),
    "comboData": _facts("QComboBox", has_items_data=True),
    "when": _facts("QDateEdit"),
    "when2": _facts("QDateEdit"),
    "whenBlank": _facts("QDateEdit", allow_blank=True),
    "clock": _facts("QTimeEdit"),
    "clockBlank": _facts("QTimeEdit", allow_blank=True),
    "stamp": _facts("QDateTimeEdit"),
    "stampBlank": _facts("QDateTimeEdit", allow_blank=True),
    "items": _facts("QListWidget"),
    "tabs": _facts("QTabWidget", pages=("shippingPage",)),
    "stack": _facts("QStackedWidget"),
    "dotted": _facts("QtWidgets.QSpinBox"),
}

METHODS = {
    "is_manager": MethodFacts("is_manager", 1, 2),
    "price_for": MethodFacts("price_for", 1, 2, params=("qty", "name"), required=2),
    "flag": MethodFacts("flag", 1, 2),
    "extra": MethodFacts("extra", 1, 2),
}
RETURNS = {"is_manager": "bool", "price_for": "Decimal", "extra": "int"}


def env_for(widgets: Optional[dict] = None) -> FormulaEnv:
    return FormulaEnv.for_test(
        WIDGETS if widgets is None else widgets,
        METHODS,
        returns=RETURNS,
        class_chain=_chain,
    )


def allowed_names(env: FormulaEnv) -> set:
    return set(env.widgets) | set(env.page_names())


def _slot(name: str) -> SlotKind:
    if name == "condition":
        return SlotKind.condition()
    return SlotKind(name)


SPECIAL = {
    "window-fb110": {"slot": "condition"},
    "self-name": {"self_name": "ui"},
    "class-name": {"widgets": {"alias": _facts("QtWidgets.QSpinBox")}},
}


def _ref_cases() -> list:
    rows = [
        ("ref-qty", "qty", "self.qty.value()"),
        ("ref-qty-blank", "qtyBlank", "_cbcs_read_spin(self.qtyBlank)"),
        ("ref-slider", "slider", "self.slider.value()"),
        ("ref-dial", "dial", "self.dial.value()"),
        ("ref-progress", "progress", "self.progress.value()"),
        ("ref-price", "price", "_cbcs_dec(self.price.value(), 2)"),
        ("ref-amount-money", "amount", "_cbcs_dec(self.amount.value(), 2)"),
        ("ref-rate", "rate", "_cbcs_dec(self.rate.value(), 3)"),
        ("ref-rate-blank", "rateBlank", "_cbcs_read_double(self.rateBlank, 4)"),
        ("ref-name", "nameEdit", "_cbcs_read_line(self.nameEdit)"),
        ("ref-plain-line", "plainEdit", "_cbcs_read_line(self.plainEdit)"),
        ("ref-weird-line", "weirdEdit", "_cbcs_read_line(self.weirdEdit)"),
        ("ref-money-line", "moneyEdit", "_cbcs_read_money(self.moneyEdit)"),
        ("ref-percent-line", "pctEdit", "_cbcs_read_percent(self.pctEdit)"),
        ("ref-whole-line", "wholeEdit", "_cbcs_read_whole(self.wholeEdit)"),
        ("ref-number-line", "numEdit", "_cbcs_read_number(self.numEdit, 3)"),
        ("ref-number-zero", "num0Edit", "_cbcs_read_number(self.num0Edit, 0)"),
        ("ref-date-line", "dateLine", "_cbcs_read_date(self.dateLine)"),
        ("ref-time-line", "timeLine", "_cbcs_read_time(self.timeLine)"),
        ("ref-caption", "caption", "self.caption.text()"),
        ("ref-note", "note", "self.note.text()"),
        ("ref-weird-label", "weirdLabel", "self.weirdLabel.text()"),
        ("ref-money-label", "moneyLabel", "_cbcs_read_label_money(self.moneyLabel)"),
        ("ref-whole-label", "wholeLabel", "_cbcs_read_label_whole(self.wholeLabel)"),
        ("ref-number-label", "numLabel", "_cbcs_read_label_number(self.numLabel, 2)"),
        ("ref-percent-label", "pctLabel", "_cbcs_read_label_percent(self.pctLabel)"),
        ("ref-date-label", "dateLabel", "_cbcs_read_label_date(self.dateLabel)"),
        ("ref-time-label", "timeLabel", "_cbcs_read_label_time(self.timeLabel)"),
        ("ref-notes", "notes", "_cbcs_read_plain(self.notes)"),
        ("ref-notes-bare", "notesBare", "_cbcs_read_plain(self.notesBare)"),
        ("ref-notes-money", "notesMoney", "_cbcs_read_plain_money(self.notesMoney)"),
        ("ref-notes-whole", "notesWhole", "_cbcs_read_plain_whole(self.notesWhole)"),
        ("ref-notes-number", "notesNum", "_cbcs_read_plain_number(self.notesNum, 1)"),
        ("ref-notes-percent", "notesPct", "_cbcs_read_plain_percent(self.notesPct)"),
        ("ref-notes-date", "notesDate", "_cbcs_read_plain_date(self.notesDate)"),
        ("ref-notes-time", "notesTime", "_cbcs_read_plain_time(self.notesTime)"),
        ("ref-body", "body", "_cbcs_read_plain(self.body)"),
        ("ref-body-money", "bodyMoney", "_cbcs_read_plain(self.bodyMoney)"),
        ("ref-ok", "ok", "self.ok.isChecked()"),
        ("ref-maybe", "maybe", "_cbcs_read_check(self.maybe)"),
        ("ref-radio", "radio", "self.radio.isChecked()"),
        ("ref-extra", "extra", "self.extra.isChecked()"),
        ("ref-group", "group", "_cbcs_read_radio(self.group)"),
        ("ref-combo", "combo", "self.combo.currentText()"),
        ("ref-combo-data", "comboData", "self.comboData.currentData()"),
        ("ref-when", "when", "_cbcs_read_dateedit(self.when)"),
        ("ref-when2", "when2", "_cbcs_read_dateedit(self.when2)"),
        ("ref-when-blank", "whenBlank", "_cbcs_read_dateedit(self.whenBlank)"),
        ("ref-clock", "clock", "_cbcs_read_timeedit(self.clock)"),
        ("ref-clock-blank", "clockBlank", "_cbcs_read_timeedit(self.clockBlank)"),
        ("ref-stamp", "stamp", "_cbcs_read_datetime(self.stamp)"),
        ("ref-stamp-blank", "stampBlank", "_cbcs_read_datetime(self.stampBlank)"),
        ("ref-items", "items", "_cbcs_read_list(self.items)"),
        ("ref-tabs", "tabs", "self.tabs.currentWidget()"),
        ("ref-stack", "stack", "self.stack.currentWidget()"),
        ("ref-page", "shippingPage", "self.shippingPage"),
        ("ref-dotted-class", "dotted", "self.dotted.value()"),
    ]
    return list(rows)


def _op_cases() -> list:
    return [
        ("add-wholes", "qty + slider", "self.qty.value() + self.slider.value()"),
        ("sub-wholes", "qty - slider", "self.qty.value() - self.slider.value()"),
        ("mul-wholes", "qty * slider", "self.qty.value() * self.slider.value()"),
        ("div-wholes", "qty / slider", "_cbcs_div(self.qty.value(), self.slider.value())"),
        ("div-lits", "7 / 2", "_cbcs_div(7, 2)"),
        ("div-blank", "qtyBlank / qty", "_cbcs_div(_cbcs_read_spin(self.qtyBlank), self.qty.value())"),
        ("add-blank-left", "qtyBlank + qty", "_cbcs_add(_cbcs_read_spin(self.qtyBlank), self.qty.value())"),
        ("sub-blank-right", "qty - qtyBlank", "_cbcs_sub(self.qty.value(), _cbcs_read_spin(self.qtyBlank))"),
        ("mul-both-blank", "qtyBlank * qtyBlank", "_cbcs_mul(_cbcs_read_spin(self.qtyBlank), _cbcs_read_spin(self.qtyBlank))"),
        ("add-decimals", "price + rate", "_cbcs_dec(self.price.value(), 2) + _cbcs_dec(self.rate.value(), 3)"),
        ("mul-price-qty", "price * qty", "_cbcs_dec(self.price.value(), 2) * self.qty.value()"),
        ("mul-money-line", "moneyEdit * qty", "_cbcs_mul(_cbcs_read_money(self.moneyEdit), self.qty.value())"),
        ("add-text-lits", '"a" + "b"', "'a' + 'b'"),
        ("concat-line-label", "nameEdit + caption", "_cbcs_concat(_cbcs_read_line(self.nameEdit), self.caption.text())"),
        ("concat-lit-line", '"a" + nameEdit', "_cbcs_concat('a', _cbcs_read_line(self.nameEdit))"),
        ("concat-line-lit", 'nameEdit + "b"', "_cbcs_concat(_cbcs_read_line(self.nameEdit), 'b')"),
        (
            "concat-then-plain",
            'nameEdit + caption + "x"',
            "_cbcs_concat(_cbcs_read_line(self.nameEdit), self.caption.text()) + 'x'",
        ),
        (
            "concat-nested",
            'nameEdit + (caption + "x")',
            "_cbcs_concat(_cbcs_read_line(self.nameEdit), _cbcs_concat(self.caption.text(), 'x'))",
        ),
        ("prec-mul-add", "(qty + slider) * dial", "(self.qty.value() + self.slider.value()) * self.dial.value()"),
        ("prec-add-mul", "qty + slider * dial", "self.qty.value() + self.slider.value() * self.dial.value()"),
        ("prec-sub-right", "qty - (slider - dial)", "self.qty.value() - (self.slider.value() - self.dial.value())"),
        ("prec-sub-left", "qty - slider - dial", "self.qty.value() - self.slider.value() - self.dial.value()"),
        ("prec-neg-sum", "-(qty + slider)", "-(self.qty.value() + self.slider.value())"),
        ("prec-neg-mul", "-(qty * slider)", "-(self.qty.value() * self.slider.value())"),
        ("neg-whole", "-qty", "-self.qty.value()"),
        ("neg-blank", "-qtyBlank", "_cbcs_neg(_cbcs_read_spin(self.qtyBlank))"),
        ("pos-whole", "+qty", "+self.qty.value()"),
        ("pos-blank", "+qtyBlank", "_cbcs_add(_cbcs_read_spin(self.qtyBlank), 0)"),
        ("mul-neg", "qty * -slider", "self.qty.value() * -self.slider.value()"),
        ("add-lit", "qty + 1000", "self.qty.value() + 1000"),
        ("add-neg-lit", "qty + -5", "self.qty.value() + -5"),
        ("lt-wholes", "qty < slider", "self.qty.value() < self.slider.value()"),
        ("le-wholes", "qty <= slider", "self.qty.value() <= self.slider.value()"),
        ("gt-wholes", "qty > slider", "self.qty.value() > self.slider.value()"),
        ("ge-wholes", "qty >= slider", "self.qty.value() >= self.slider.value()"),
        ("eq-wholes", "qty == slider", "self.qty.value() == self.slider.value()"),
        ("ne-wholes", "qty != slider", "self.qty.value() != self.slider.value()"),
        ("chain-wholes", "qty < slider < dial", "self.qty.value() < self.slider.value() < self.dial.value()"),
        ("chain-eq", "qty == slider == dial", "self.qty.value() == self.slider.value() == self.dial.value()"),
        ("cmp-sum", "qty + slider < dial", "self.qty.value() + self.slider.value() < self.dial.value()"),
        ("lt-text", "nameEdit < caption", "_cbcs_lt(_cbcs_read_line(self.nameEdit), self.caption.text())"),
        ("le-text", "nameEdit <= caption", "_cbcs_le(_cbcs_read_line(self.nameEdit), self.caption.text())"),
        ("gt-text", "nameEdit > caption", "_cbcs_gt(_cbcs_read_line(self.nameEdit), self.caption.text())"),
        ("ge-text", "nameEdit >= caption", "_cbcs_ge(_cbcs_read_line(self.nameEdit), self.caption.text())"),
        ("eq-text", "nameEdit == caption", "_cbcs_eq(_cbcs_read_line(self.nameEdit), self.caption.text())"),
        ("ne-text", "nameEdit != caption", "_cbcs_ne(_cbcs_read_line(self.nameEdit), self.caption.text())"),
        (
            "chain-text",
            'nameEdit < caption < "z"',
            "_cbcs_and(_cbcs_lt(_cbcs_read_line(self.nameEdit), self.caption.text()), _cbcs_lt(self.caption.text(), 'z'))",
        ),
        ("none-eq", "None == qty", "_cbcs_is_blank(self.qty.value())"),
        ("ne-none", "qty != None", "_cbcs_not(_cbcs_is_blank(self.qty.value()))"),
        ("none-ne", "None != qty", "_cbcs_not(_cbcs_is_blank(self.qty.value()))"),
        ("empty-eq", '"" == nameEdit', "_cbcs_is_blank(_cbcs_read_line(self.nameEdit))"),
        ("ne-empty", 'nameEdit != ""', "_cbcs_not(_cbcs_is_blank(_cbcs_read_line(self.nameEdit)))"),
        ("empty-ne", '"" != nameEdit', "_cbcs_not(_cbcs_is_blank(_cbcs_read_line(self.nameEdit)))"),
        ("lt-none", "qty < None", "_cbcs_lt(self.qty.value(), None)"),
        ("in-wholes", "qty in [1, 2, 3]", "self.qty.value() in [1, 2, 3]"),
        ("not-in-wholes", "qty not in [1, 2]", "self.qty.value() not in [1, 2]"),
        ("in-text", 'nameEdit in ["a", "b"]', "_cbcs_in(_cbcs_read_line(self.nameEdit), ['a', 'b'])"),
        ("not-in-text", 'nameEdit not in ["a", "b"]', "_cbcs_not_in(_cbcs_read_line(self.nameEdit), ['a', 'b'])"),
        ("in-empty-lit", '"" in [""]', "_cbcs_in('', [''])"),
        ("and-yes", "ok and radio", "self.ok.isChecked() and self.radio.isChecked()"),
        ("or-yes", "ok or radio", "self.ok.isChecked() or self.radio.isChecked()"),
        ("and-three", "ok and radio and extra", "self.ok.isChecked() and self.radio.isChecked() and self.extra.isChecked()"),
        ("or-of-and", "ok and radio or extra", "self.ok.isChecked() and self.radio.isChecked() or self.extra.isChecked()"),
        ("and-of-or", "ok and (radio or extra)", "self.ok.isChecked() and (self.radio.isChecked() or self.extra.isChecked())"),
        (
            "and-blank",
            "ok and maybe and radio",
            "_cbcs_and(_cbcs_and(self.ok.isChecked(), _cbcs_read_check(self.maybe)), self.radio.isChecked())",
        ),
        ("or-blank", "maybe or ok", "_cbcs_or(_cbcs_read_check(self.maybe), self.ok.isChecked())"),
        ("and-true", "True and ok", "True and self.ok.isChecked()"),
        ("or-false", "False or ok", "False or self.ok.isChecked()"),
        ("not-yes", "not ok", "not self.ok.isChecked()"),
        ("not-true", "not True", "not True"),
        ("not-blank", "not maybe", "_cbcs_not(_cbcs_read_check(self.maybe))"),
        ("not-and-yes", "not ok and radio", "not self.ok.isChecked() and self.radio.isChecked()"),
        ("if-wholes", "slider if ok else qty", "(self.slider.value() if self.ok.isChecked() else self.qty.value())"),
        (
            "if-blank-branch",
            "qty if ok else qtyBlank",
            "(self.qty.value() if self.ok.isChecked() else _cbcs_read_spin(self.qtyBlank))",
        ),
        (
            "if-nested",
            "qty if ok else slider if radio else dial",
            "(self.qty.value() if self.ok.isChecked() else (self.slider.value() if self.radio.isChecked() else self.dial.value()))",
        ),
        ("date-add", "when + qty", "_cbcs_add_days(_cbcs_read_dateedit(self.when), self.qty.value())"),
        ("whole-add-date", "qty + when", "_cbcs_add_days(_cbcs_read_dateedit(self.when), self.qty.value())"),
        ("date-sub-whole", "when - qty", "_cbcs_add_days(_cbcs_read_dateedit(self.when), -self.qty.value())"),
        (
            "date-sub-blank",
            "when - qtyBlank",
            "_cbcs_add_days(_cbcs_read_dateedit(self.when), _cbcs_neg(_cbcs_read_spin(self.qtyBlank)))",
        ),
        (
            "date-sub-sum",
            "when - (qty + slider)",
            "_cbcs_add_days(_cbcs_read_dateedit(self.when), -(self.qty.value() + self.slider.value()))",
        ),
        (
            "date-diff",
            "when - when2",
            "_cbcs_date_diff(_cbcs_read_dateedit(self.when), _cbcs_read_dateedit(self.when2))",
        ),
        ("date-blank-add", "whenBlank + qty", "_cbcs_add_days(_cbcs_read_dateedit(self.whenBlank), self.qty.value())"),
        ("date-lt", "when < when2", "_cbcs_read_dateedit(self.when) < _cbcs_read_dateedit(self.when2)"),
        (
            "date-lt-blank",
            "whenBlank < when",
            "_cbcs_lt(_cbcs_read_dateedit(self.whenBlank), _cbcs_read_dateedit(self.when))",
        ),
        ("page-eq", "tabs == shippingPage", "self.tabs.currentWidget() == self.shippingPage"),
        ("div-sum-arg", "(qty + slider) / dial", "_cbcs_div(self.qty.value() + self.slider.value(), self.dial.value())"),
    ]


def _call_cases() -> list:
    return [
        ("call-is-blank", "is_blank(qty)", "_cbcs_is_blank(self.qty.value())"),
        ("call-is-blank-text", "is_blank(nameEdit)", "_cbcs_is_blank(_cbcs_read_line(self.nameEdit))"),
        ("call-if-blank", "if_blank(moneyEdit, 0)", "_cbcs_if_blank(_cbcs_read_money(self.moneyEdit), 0)"),
        ("call-if-blank-whole", "if_blank(qty, 1)", "_cbcs_if_blank(self.qty.value(), 1)"),
        ("call-round", "round(rate)", "_cbcs_round(_cbcs_dec(self.rate.value(), 3))"),
        ("call-round-places", "round(rate, 1)", "_cbcs_round(_cbcs_dec(self.rate.value(), 3), 1)"),
        ("call-abs", "abs(qty)", "_cbcs_abs(self.qty.value())"),
        ("call-abs-money", "abs(moneyEdit)", "_cbcs_abs(_cbcs_read_money(self.moneyEdit))"),
        ("call-min", "min(qty, slider)", "_cbcs_min(self.qty.value(), self.slider.value())"),
        ("call-min-three", "min(qty, slider, dial)", "_cbcs_min(self.qty.value(), self.slider.value(), self.dial.value())"),
        ("call-max", "max(qty, slider)", "_cbcs_max(self.qty.value(), self.slider.value())"),
        ("call-count", "count(nameEdit)", "_cbcs_count(_cbcs_read_line(self.nameEdit))"),
        ("call-number", "number(nameEdit)", "_cbcs_number(_cbcs_read_line(self.nameEdit))"),
        ("call-whole", "whole(rate)", "_cbcs_whole(_cbcs_dec(self.rate.value(), 3))"),
        ("call-text", "text(qty)", "_cbcs_text(self.qty.value())"),
        ("call-text-money", 'text(qty, "money")', "_cbcs_text(self.qty.value(), 'money')"),
        ("call-text-number", 'text(qty, "number:2")', "_cbcs_text(self.qty.value(), 'number:2')"),
        ("call-text-percent", 'text(qty, "percent:1")', "_cbcs_text(self.qty.value(), 'percent:1')"),
        ("call-text-iso", 'text(when, "date:iso")', "_cbcs_text(_cbcs_read_dateedit(self.when), 'date:iso')"),
        ("call-text-short", 'text(when, "date:short")', "_cbcs_text(_cbcs_read_dateedit(self.when), 'date:short')"),
        ("call-text-long", 'text(when, "date:long")', "_cbcs_text(_cbcs_read_dateedit(self.when), 'date:long')"),
        ("call-text-upper", 'text(nameEdit, "text:upper")', "_cbcs_text(_cbcs_read_line(self.nameEdit), 'text:upper')"),
        ("call-text-proper", 'text(nameEdit, "text:proper")', "_cbcs_text(_cbcs_read_line(self.nameEdit), 'text:proper')"),
        ("call-len", "len(nameEdit)", "_cbcs_len(_cbcs_read_line(self.nameEdit))"),
        ("call-upper", "upper(nameEdit)", "_cbcs_upper(_cbcs_read_line(self.nameEdit))"),
        ("call-lower", "lower(nameEdit)", "_cbcs_lower(_cbcs_read_line(self.nameEdit))"),
        ("call-trim", "trim(nameEdit)", "_cbcs_trim(_cbcs_read_line(self.nameEdit))"),
        ("call-proper", "proper(nameEdit)", "_cbcs_proper(_cbcs_read_line(self.nameEdit))"),
        ("call-left", "left(nameEdit, 2)", "_cbcs_left(_cbcs_read_line(self.nameEdit), 2)"),
        ("call-right", "right(nameEdit, 3)", "_cbcs_right(_cbcs_read_line(self.nameEdit), 3)"),
        ("call-contains", 'contains(nameEdit, "ab")', "_cbcs_contains(_cbcs_read_line(self.nameEdit), 'ab')"),
        ("call-starts", 'starts_with(nameEdit, "ab")', "_cbcs_starts_with(_cbcs_read_line(self.nameEdit), 'ab')"),
        ("call-ends", 'ends_with(nameEdit, "ab")', "_cbcs_ends_with(_cbcs_read_line(self.nameEdit), 'ab')"),
        ("call-replace", 'replace(nameEdit, "a", "b")', "_cbcs_replace(_cbcs_read_line(self.nameEdit), 'a', 'b')"),
        ("call-matches", 'matches(nameEdit, "a.c")', "_cbcs_matches(_cbcs_read_line(self.nameEdit), 'a.c')"),
        ("call-email", "is_email(nameEdit)", "_cbcs_is_email(_cbcs_read_line(self.nameEdit))"),
        ("call-phone", "is_phone(nameEdit)", "_cbcs_is_phone(_cbcs_read_line(self.nameEdit))"),
        ("call-zip", "is_zip(nameEdit)", "_cbcs_is_zip(_cbcs_read_line(self.nameEdit))"),
        ("call-today", "today()", "_cbcs_today()"),
        ("call-now", "now()", "_cbcs_now()"),
        ("call-date", "date(2020, 1, 31)", "_cbcs_date(2020, 1, 31)"),
        ("call-year", "year(when)", "_cbcs_year(_cbcs_read_dateedit(self.when))"),
        ("call-month", "month(when)", "_cbcs_month(_cbcs_read_dateedit(self.when))"),
        ("call-day", "day(when)", "_cbcs_day(_cbcs_read_dateedit(self.when))"),
        ("call-weekday", "weekday(when)", "_cbcs_weekday(_cbcs_read_dateedit(self.when))"),
        ("call-add-days", "add_days(when, qty)", "_cbcs_add_days(_cbcs_read_dateedit(self.when), self.qty.value())"),
        ("call-add-months", "add_months(when, 1)", "_cbcs_add_months(_cbcs_read_dateedit(self.when), 1)"),
        (
            "call-days-between",
            "days_between(when, when2)",
            "_cbcs_days_between(_cbcs_read_dateedit(self.when), _cbcs_read_dateedit(self.when2))",
        ),
        ("today-eq-date", "today() == when", "_cbcs_today() == _cbcs_read_dateedit(self.when)"),
    ]


def _other_cases() -> list:
    return [
        ("lit-none", "None", "None"),
        ("lit-true", "True", "True"),
        ("lit-false", "False", "False"),
        ("lit-int", "1000", "1000"),
        ("lit-neg", "-5", "-5"),
        ("lit-decimal", "1.1", 'Decimal("1.1")'),
        ("lit-decimal-neg", "-2.50", '-Decimal("2.50")'),
        ("lit-quote", '"say \\"hi\\""', "'say \"hi\"'"),
        ("attr-text", "qty.text", "_cbcs_read_shown(self.qty)"),
        ("attr-enabled", "qty.enabled", "_cbcs_read_enabled(self.qty)"),
        ("attr-visible", "nameEdit.visible", "_cbcs_read_visible(self.nameEdit)"),
        ("attr-checked", "ok.checked", "_cbcs_read_checked(self.ok)"),
        ("attr-count", "combo.count", "_cbcs_read_count(self.combo)"),
        ("window-yes", "window.is_manager()", "self._form.is_manager()"),
        (
            "window-args",
            "window.price_for(qty, nameEdit)",
            "self._form.price_for(self.qty.value(), _cbcs_read_line(self.nameEdit))",
        ),
        ("window-any", "window.flag()", "self._form.flag()"),
        ("window-fb110", "window.flag()", "_cbcs_bool(self._form.flag())"),
        ("window-and", "window.is_manager() and ok", "self._form.is_manager() and self.ok.isChecked()"),
        ("window-add", "window.extra() + qty", "_cbcs_add(self._form.extra(), self.qty.value())"),
        ("self-name", "qty", "ui.qty.value()"),
        ("class-name", "alias", "self.alias.value()"),
    ]


GOLDEN = _ref_cases() + _op_cases() + _call_cases() + _other_cases()

ERRORS = (
    "sum(qty, slider)",
    "avg(qty, slider)",
    "count(qty, moneyEdit)",
    "stamp + qty",
    "stamp - when",
    "qty if nameEdit else slider",
    "(",
    "noSuchWidget",
    "qty == None",
    'nameEdit == ""',
    '"a" == ""',
    "qty / slider == None",
    "not (ok and radio)",
    "not (ok or radio)",
)


def referenced(source: str) -> tuple:
    table = list(helper_table())
    sources = {helper_id: text for helper_id, text in table}
    order = [helper_id for helper_id, _text in table]
    needed = set(re.findall(r"\b(_cbcs_[A-Za-z0-9_]*)\b", source))
    changed = True
    while changed:
        changed = False
        for helper_id in list(needed):
            text = sources.get(helper_id)
            if text is None:
                continue
            for found in re.findall(r"\b(_cbcs_[A-Za-z0-9_]*)\b", text):
                if found in sources and found not in needed:
                    needed.add(found)
                    changed = True
    return tuple(helper_id for helper_id in order if helper_id in needed)


def prepare(case: Case) -> tuple:
    name, text, _expected = case
    extra = SPECIAL.get(name, {})
    widgets = extra.get("widgets")
    env = env_for(widgets if isinstance(widgets, dict) else None)
    self_name = extra.get("self_name", "self")
    slot = _slot(str(extra.get("slot", "expr")))
    analysis = analyze(text, env, slot)
    return analysis, env, self_name


def _hand_built():
    """Trees the grammar will not produce.

    ``== None`` and ``== ""`` are FB107 (write ``is_blank``). ``not ( ... )`` is
    FB107 because it matches Excel ``NOT(...)``.
    """
    from app.features.form_builder.engine.logic.formula.nodes import (
        Analysis,
        Bin,
        Bool,
        Compare,
        Lit,
        Ref,
        Span,
        Unary,
    )
    from app.features.form_builder.engine.logic.formula.types import BLANK, NUMBER, TEXT, WHOLE, YESNO

    span = Span(0, 1)
    env = env_for()
    qty = Ref(span, WHOLE, "qty")
    slider = Ref(span, WHOLE, "slider")
    name = Ref(span, TEXT, "nameEdit")
    ok = Ref(span, YESNO, "ok")
    radio = Ref(span, YESNO, "radio")
    rows = [
        (
            Compare(span, YESNO, qty, (("==", Lit(span, BLANK, None)),)),
            "_cbcs_is_blank(self.qty.value())",
        ),
        (
            Compare(span, YESNO, name, (("==", Lit(span, TEXT, "")),)),
            "_cbcs_is_blank(_cbcs_read_line(self.nameEdit))",
        ),
        (
            Compare(span, YESNO, Lit(span, TEXT, "a"), (("==", Lit(span, TEXT, "")),)),
            "_cbcs_is_blank('a')",
        ),
        (
            Compare(span, YESNO, Bin(span, NUMBER, "/", qty, slider), (("==", Lit(span, BLANK, None)),)),
            "_cbcs_is_blank(_cbcs_div(self.qty.value(), self.slider.value()))",
        ),
        (
            Unary(span, YESNO, "not", Bool(span, YESNO, "and", (ok, radio))),
            "not (self.ok.isChecked() and self.radio.isChecked())",
        ),
        (
            Unary(span, YESNO, "not", Bool(span, YESNO, "or", (ok, radio))),
            "not (self.ok.isChecked() or self.radio.isChecked())",
        ),
    ]
    built = []
    for tree, expected in rows:
        analysis = Analysis("hand", tree, YESNO, (), (), frozenset(), ())
        emitted = compile_formula(analysis, env)
        built.append((expected, emitted))
    return built


def iter_golden_sources():
    for case in GOLDEN:
        analysis, env, self_name = prepare(case)
        emitted = compile_formula(analysis, env, self_name=self_name)
        yield emitted.source, self_name, allowed_names(env)
    env = env_for()
    for _expected, emitted in _hand_built():
        yield emitted.source, "self", allowed_names(env)


@pytest.mark.unit
def test_golden_case_count() -> None:
    assert len(GOLDEN) >= 150


@pytest.mark.unit
def test_hand_built_trees_the_grammar_rejects() -> None:
    for expected, emitted in _hand_built():
        assert emitted.source == expected
        assert emitted.helpers == referenced(emitted.source)


@pytest.mark.unit
@pytest.mark.parametrize("case", GOLDEN, ids=[case[0] for case in GOLDEN])
def test_compile_source(case: Case) -> None:
    _name, _text, expected = case
    analysis, env, self_name = prepare(case)
    errors = [
        (item.code, item.message)
        for item in analysis.problems
        if CODES[item.code].severity == Severity.ERROR
    ]
    assert errors == []
    emitted = compile_formula(analysis, env, self_name=self_name)
    assert emitted.source == expected
    assert emitted.helpers == referenced(emitted.source)


@pytest.mark.unit
@pytest.mark.parametrize("text", ERRORS)
def test_rejected_text_raises(text: str) -> None:
    analysis = analyze(text, env_for(), SlotKind("expr"))
    with pytest.raises(ValueError):
        compile_formula(analysis, env_for())


@pytest.mark.unit
def test_unknown_kind_warns_and_compiles() -> None:
    analysis, env, self_name = prepare(("ref-weird-line", "weirdEdit", ""))
    assert any(item.code == "FB118" for item in analysis.problems)
    emitted = compile_formula(analysis, env, self_name=self_name)
    assert emitted.source == "_cbcs_read_line(self.weirdEdit)"


@pytest.mark.unit
def test_widget_name_starting_with_underscore_raises() -> None:
    widgets = {"_x": _facts("QSpinBox")}
    env = env_for(widgets)
    analysis = analyze("_x", env, SlotKind("expr"))
    assert analysis.tree is not None
    with pytest.raises(ValueError, match="starts with _"):
        compile_formula(analysis, env)


@pytest.mark.unit
def test_imports_follow_source_and_helpers() -> None:
    env = env_for()

    def compiled(text: str) -> object:
        analysis = analyze(text, env, SlotKind("expr"))
        return compile_formula(analysis, env)

    assert compiled("1.1").imports == (("decimal", "Decimal"),)  # type: ignore[attr-defined]
    assert compiled("qty").imports == ()  # type: ignore[attr-defined]
    assert compiled("qty / slider").imports == (("decimal", "Decimal"),)  # type: ignore[attr-defined]
    assert compiled("price").imports == (("decimal", "Decimal"), ("decimal", "ROUND_HALF_UP"))  # type: ignore[attr-defined]
    assert compiled("today()").imports == (("datetime", "date"),)  # type: ignore[attr-defined]
    assert compiled("now()").imports == (("datetime", "datetime"),)  # type: ignore[attr-defined]


@pytest.mark.unit
def test_logic_hooks_helper_table_matches_formula_runtime() -> None:
    from app.features.form_builder.engine.codegen.logic_hooks import helper_table as hooks_table
    from app.features.form_builder.engine.codegen.logic_hooks import set_helper_provider

    set_helper_provider(None)
    assert hooks_table() == helper_table()


@pytest.mark.unit
def test_generated_module_pastes_add_and_its_blank_helper(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.engine.codegen import emit as emit_module
    from app.features.form_builder.engine.codegen.api import generate_form_module
    from app.features.form_builder.engine.codegen.logic_hooks import Contribution, set_helper_provider
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.ui4.reader import read_ui
    from tests.form_builder.engine.test_m6_1a_events import form

    set_helper_provider(None)
    env = env_for()
    analysis = analyze("qtyBlank + qty", env, SlotKind("expr"))
    emitted = compile_formula(analysis, env)
    assert "_cbcs_add" in emitted.helpers
    assert "_cbcs_is_blank" in emitted.helpers

    class _Probe:
        expander_id = "formula-helper"
        level = 1
        order = 1

        def contribute(self, doc: object, ctx: object) -> Contribution:
            del doc, ctx
            return Contribution(imports=emitted.imports, helpers=emitted.helpers)

    monkeypatch.setattr(emit_module, "load_expanders", lambda: (_Probe(),))
    text = form()
    path = tmp_path / "plain.ui"
    path.write_text(text, encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_plain.py"),
        window_path=str(tmp_path / "plain_window.py"),
        module_name="ui_plain",
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None
    assert "def _cbcs_add(" in result.text
    assert "def _cbcs_is_blank(" in result.text
    namespace: Dict[str, object] = {}
    exec(result.text, namespace)  # noqa: S102
    add = namespace["_cbcs_add"]
    blank = namespace["_cbcs_is_blank"]
    assert add(1, None) is None  # type: ignore[operator]
    assert add(2, 3) == 5  # type: ignore[operator]
    assert blank(None) is True  # type: ignore[operator]
    assert blank(0) is False  # type: ignore[operator]
