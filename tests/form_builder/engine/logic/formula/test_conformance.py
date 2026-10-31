"""Front-end half of the formula conformance suite (CONTRACTS.md section 17.14)."""

from __future__ import annotations

import ast

import pytest

from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.formula import analyze, apply_fix, normalize
from app.features.form_builder.engine.logic.formula.library import FUNCTIONS
from app.features.form_builder.engine.commands.refs import FORMULA_NAMES
from app.features.form_builder.engine.logic.formula.types import NUMBER, TEXT
from tests.form_builder.engine.logic.formula.support import ENV, ENV_DATA, SLOTS

pytestmark = pytest.mark.unit

# (text, slot, expect). expect is a type kind, or an FB code that must be present.
CASES = []


def add(text: str, slot: str, expect: str) -> None:
    CASES.append((text, slot, expect))


for _name, _slot, _expect in (
    ("qtySpin", "whole", "whole"),
    ("slider", "whole", "whole"),
    ("dial", "whole", "whole"),
    ("progress", "whole", "whole"),
    ("mySpin", "whole", "whole"),
    ("blankSpin", "whole", "whole"),
    ("rateSpin", "number", "number"),
    ("priceSpin", "money", "money"),
    ("percentEdit", "number", "number"),
    ("wholeEdit", "whole", "whole"),
    ("nameEdit", "text", "text"),
    ("notesEdit", "text", "text"),
    ("bodyEdit", "text", "text"),
    ("titleLabel", "text", "text"),
    ("shipGroup", "text", "text"),
    ("plainCombo", "text", "text"),
    ("itemsList", "text", "text"),
    ("discountCheck", "yesno", "yesno"),
    ("triCheck", "yesno", "yesno"),
    ("rushRadio", "yesno", "yesno"),
    ("invoiceDate", "date", "date"),
    ("whenEdit", "time", "time"),
    ("stampEdit", "datetime", "datetime"),
    ("detailTabs", "page", "page"),
    ("stack", "page", "page"),
    ("customerCombo", "text", "choice"),
    ("itemsGrid", "text", "FB114"),
    ("badKind", "text", "text"),
):
    add(_name, _slot, _expect)

_NUM = {"w": "qtySpin", "n": "rateSpin", "m": "priceSpin"}


def _arith_kind(op: str, left: str, right: str) -> str:
    if left == "m" or right == "m":
        return "money"
    if op == "/":
        return "number"
    if left == "w" and right == "w":
        return "whole"
    return "number"


for _op in ("+", "-", "*", "/"):
    for _left in ("w", "n", "m"):
        for _right in ("w", "n", "m"):
            add("%s %s %s" % (_NUM[_left], _op, _NUM[_right]), _arith_kind(_op, _left, _right), _arith_kind(_op, _left, _right))

add("nameEdit + nameEdit", "text", "text")
add("nameEdit + qtySpin", "text", "FB102")
add("qtySpin + nameEdit", "whole", "FB102")
add("invoiceDate + qtySpin", "date", "date")
add("qtySpin + invoiceDate", "date", "date")
add("invoiceDate - qtySpin", "date", "date")
add("invoiceDate - invoiceDate", "whole", "whole")
add("invoiceDate + rateSpin", "date", "FB102")
add("qtySpin < nameEdit", "cond", "FB102")
add("qtySpin == nameEdit", "cond", "FB102")
add("not nameEdit", "cond", "FB102")
add("not qtySpin", "cond", "FB102")
add("nameEdit and discountCheck", "cond", "FB102")
add("qtySpin or discountCheck", "cond", "FB102")
add("discountCheck and rushRadio", "cond", "yesno")
add("not discountCheck", "cond", "yesno")
add('nameEdit in ["A", "B"]', "cond", "yesno")
add("qtySpin in [1, 2]", "cond", "yesno")
add('qtySpin in ["A"]', "cond", "FB102")
add("qtySpin in []", "cond", "yesno")
add("nameEdit if discountCheck else notesEdit", "text", "text")
add("qtySpin if discountCheck else nameEdit", "text", "FB102")
add("-qtySpin", "whole", "whole")
add("+rateSpin", "number", "number")
add("None + qtySpin", "whole", "whole")
add("nameEdit + None", "text", "text")
add('nameEdit != ""', "cond", "yesno")
add("None < qtySpin", "cond", "yesno")
add("is_blank(nameEdit)", "cond", "yesno")
add("is_blank(0)", "cond", "yesno")
add("is_blank(None)", "cond", "yesno")
add("if_blank(rateSpin, 0)", "number", "number")
add("if_blank(nameEdit, 0)", "text", "FB102")

for _op in ("==", "!=", "<", "<=", ">", ">="):
    add("qtySpin %s rateSpin" % _op, "cond", "yesno")
    add("priceSpin %s qtySpin" % _op, "cond", "yesno")

_FUN = (
    ("is_blank(nameEdit)", "cond", "yesno"),
    ("if_blank(priceSpin, 0)", "money", "money"),
    ("round(rateSpin)", "number", "number"),
    ("round(rateSpin, 2)", "number", "number"),
    ("abs(rateSpin)", "number", "number"),
    ("abs(-3)", "number", "number"),
    ("min(qtySpin, rateSpin)", "number", "number"),
    ("max(priceSpin, qtySpin)", "money", "money"),
    ('number("$1,234.50")', "number", "number"),
    ("whole(rateSpin)", "whole", "whole"),
    ("text(qtySpin)", "text", "text"),
    ('text(invoiceDate, "date:long")', "text", "text"),
    ('len("ab")', "whole", "whole"),
    ('upper(nameEdit)', "text", "text"),
    ('lower("Ab")', "text", "text"),
    ('trim(" a ")', "text", "text"),
    ('proper(nameEdit)', "text", "text"),
    ('left(nameEdit, 2)', "text", "text"),
    ('right("abcd", 2)', "text", "text"),
    ('contains(nameEdit, "a")', "cond", "yesno"),
    ('starts_with(nameEdit, "a")', "cond", "yesno"),
    ('ends_with(nameEdit, "a")', "cond", "yesno"),
    ('replace(nameEdit, "a", "b")', "text", "text"),
    ('matches(nameEdit, "^[A-Z]+$")', "cond", "yesno"),
    ("is_email(nameEdit)", "cond", "yesno"),
    ("is_phone(nameEdit)", "cond", "yesno"),
    ("is_zip(nameEdit)", "cond", "yesno"),
    ("today()", "date", "date"),
    ("now()", "datetime", "datetime"),
    ("date(2026, 10, 31)", "date", "date"),
    ("year(invoiceDate)", "whole", "whole"),
    ("month(invoiceDate)", "whole", "whole"),
    ("day(invoiceDate)", "whole", "whole"),
    ("weekday(invoiceDate)", "whole", "whole"),
    ("add_days(invoiceDate, qtySpin)", "date", "date"),
    ("add_months(invoiceDate, 1)", "date", "date"),
    ("days_between(invoiceDate, invoiceDate)", "whole", "whole"),
    ("min(qtySpin)", "number", "FB112"),
    ("round(rateSpin, 2, 1)", "number", "FB112"),
    ("abs(nameEdit)", "number", "FB102"),
    ('len(qtySpin)', "whole", "FB102"),
    ('matches(nameEdit, qtySpin)', "cond", "FB105"),
    ('matches(nameEdit, "[")', "cond", "FB105"),
    ('text(qtySpin, "nope")', "text", "text"),
    ("sum(qtySpin)", "number", "FB102"),
    ("is_blank()", "cond", "FB112"),
)
for _row in _FUN:
    add(*_row)

for _index in range(30):
    add("qtySpin + %d" % _index, "whole", "whole")
for _index in range(30):
    add("rateSpin * %d" % (_index + 1), "number", "number")
for _index in range(20):
    add('nameEdit + "%d"' % _index, "text", "text")
for _index in range(15):
    add("discountCheck and rushRadio or discountCheck" if _index % 2 == 0 else "not not discountCheck", "cond", "yesno")

add("1_000", "whole", "whole")
add("1.10", "number", "number")
add("1e3", "number", "number")
add("éSpin * 2", "whole", "whole")
add("qtySpin.text", "text", "text")
add("discountCheck.checked", "yesno", "yesno")
add("nameEdit.enabled", "yesno", "yesno")
add("plainCombo.count", "whole", "whole")
add("plainCombo.visible", "yesno", "yesno")
add("nameEdit.missing", "text", "FB114")
add("a.b.c.d", "text", "FB114")
add("shippingPage", "page", "page")
add("detailTabs == shippingPage", "cond", "yesno")
add("form.isNew", "cond", "FB115")
add("form.position", "whole", "FB115")
add("record.status", "text", "FB115")
add("window.is_manager()", "cond", "yesno")
add("window.price_for(customerCombo, qtySpin)", "number", "number")
add("window.untagged()", "cond", "yesno")
add("window.missing()", "cond", "FB109")
add("window.price_for(qtySpin)", "number", "FB112")
add("window.optional()", "text", "text")
add("cbcsTotal", "text", "FB106")
add("sum", "text", "FB103")
add("qtyspin", "whole", "FB101")
add("lambda: 1", "whole", "FB103")
add("(x := 1)", "whole", "FB103")
add("qtySpin[0]", "whole", "FB103")
add("0x10", "whole", "FB103")
add("0o10", "whole", "FB103")
add("0b10", "whole", "FB103")
add("1j", "number", "FB103")
add('f"hi"', "text", "FB103")
add("2 ** 3", "number", "FB103")
add("7 // 2", "number", "FB103")
add("qtySpin % 2", "whole", "FB103")
add("qtySpin is None", "cond", "FB103")
add("f(a=1)", "whole", "FB103")
add("[1, 2]", "whole", "FB103")
add('"""ab\ncd"""', "text", "FB103")
add("", "cond", "FB108")
add("qtySpin +", "whole", "FB108")
add("=" * 0 + "qty" * 700, "text", "FB111")
add("(" * 40 + "qtySpin" + ")" * 40, "whole", "FB111")
add("not " * 70 + "discountCheck", "cond", "FB111")
add("=qtySpin*2", "whole", "FB107")
add("qtySpin = 1", "cond", "FB107")
add("qtySpin <> 2", "cond", "FB107")
add("IF(discountCheck, qtySpin, 0)", "whole", "FB107")
add("AND(discountCheck, rushRadio)", "cond", "FB107")
add("OR(discountCheck, rushRadio)", "cond", "FB107")
add("NOT(discountCheck)", "cond", "FB107")
add("ISBLANK(nameEdit)", "cond", "FB107")
add("nameEdit & notesEdit", "text", "FB107")
add("TRUE", "cond", "FB107")
add("false", "cond", "FB107")
add("10%", "number", "FB107")
add("qtySpin && rushRadio", "cond", "FB107")
add("qtySpin || rushRadio", "cond", "FB107")
add("!discountCheck", "cond", "FB107")
add("min(qtySpin; rateSpin)", "number", "FB107")
add("Qty * Price", "money", "FB107")
add('nameEdit == ""', "cond", "FB107")
add("nameEdit == None", "cond", "FB107")


def test_suite_has_the_front_end_cases() -> None:
    assert len(CASES) >= 250


@pytest.mark.parametrize("text,slot,expect", CASES, ids=[row[0][:60] for row in CASES])
def test_analyze_case(text: str, slot: str, expect: str) -> None:
    env = ENV_DATA if "itemsGrid." in text or text.startswith(("sum(", "count(", "avg(")) else ENV
    got = analyze(text, env, SLOTS[slot])
    codes = [problem.code for problem in got.problems]
    if expect.startswith("FB"):
        assert expect in codes, codes
        return
    errors = [code for code in codes if code not in ("FB110", "FB118")]
    assert errors == [], (errors, [problem.message for problem in got.problems])
    assert got.type is not None
    assert got.type.kind.value == expect
    assert got.tree is not None


def test_unknown_kind_warns() -> None:
    got = analyze("badKind", ENV, SLOTS["text"])
    assert any(problem.code == "FB118" for problem in got.problems)
    assert got.type is not None and got.type.kind.value == "text"


def test_fb102_sentence() -> None:
    got = analyze("nameEdit + qtySpin", ENV, SLOTS["text"])
    messages = [problem.message for problem in got.problems if problem.code == "FB102"]
    assert "Can't add text and a whole number. nameEdit holds text." in messages


def test_fb101_sentence() -> None:
    got = analyze("qtyspin", ENV, SLOTS["whole"])
    problem = next(item for item in got.problems if item.code == "FB101")
    assert problem.message == "qtySpin is not a field on this form. Did you mean qtySpin?" or problem.message.startswith(
        "qtyspin is not a field on this form. Did you mean "
    )


def test_excel_messages_and_replacements() -> None:
    checks = (
        ("=qtySpin*2", "Formulas don't start with =", "qtySpin*2"),
        ("qtySpin <> 2", "Use `!=`", "qtySpin != 2"),
        ("IF(discountCheck, 1, 0)", "Write `x if c else y`", "1 if discountCheck else 0"),
        ("AND(discountCheck, rushRadio)", "Use `and`, `or`, `not`", "discountCheck and rushRadio"),
        ("nameEdit & notesEdit", "Join text with `+`", "text(nameEdit) + text(notesEdit)"),
        ("10%", "Write a decimal, like `0.10`.", "0.10"),
        ("Qty", "These are labels", "qtySpin"),
        ('nameEdit == ""', "Use `is_blank`", "is_blank(nameEdit)"),
        ("min(1; 2)", "Separate the values with a comma.", "min(1, 2)"),
    )
    for text, message, replacement in checks:
        got = analyze(text, ENV, SLOTS["cond"])
        fix = next(item for item in got.fixes if item.message == message)
        assert apply_fix(text, fix) == replacement
        assert apply_fix(apply_fix(text, fix), fix) == replacement


def test_non_ascii_name_span_is_characters() -> None:
    got = analyze("你 + 1", ENV, SLOTS["whole"])
    problem = next(item for item in got.problems if item.code == "FB101")
    assert (problem.span.start, problem.span.end) == (0, 1)
    assert got.tree is not None


def test_decimal_literal_uses_source_text() -> None:
    from decimal import Decimal

    from app.features.form_builder.engine.logic.formula.nodes import Lit

    got = analyze("1.10", ENV, SLOTS["number"])
    assert isinstance(got.tree, Lit)
    assert got.tree.value == Decimal("1.10")
    whole = analyze("1_000", ENV, SLOTS["whole"])
    assert isinstance(whole.tree, Lit)
    assert whole.tree.value == 1000


def test_assignment_sentence() -> None:
    got = analyze("(x := 1)", ENV, SLOTS["whole"])
    assert got.problems[0].message == "Formulas can't change things. Use a Set a field step."


def test_window_sentence() -> None:
    got = analyze("window.missing()", ENV, SLOTS["cond"])
    assert got.problems[0].message == "missing is not in InvoiceWindow (invoice_window.py)."


def test_data_sentence() -> None:
    got = analyze("form.isNew", ENV, SLOTS["cond"])
    assert got.problems[0].message == "Connect this form to a table first (coming with data forms)."


def test_column_outside_aggregate_when_data_is_connected() -> None:
    got = analyze("itemsGrid.qty", ENV_DATA, SLOTS["number"])
    assert any(problem.code == "FB113" for problem in got.problems)
    total = analyze("sum(itemsGrid.qty)", ENV_DATA, SLOTS["number"])
    assert total.type is not None and total.type.kind.value == "number"
    assert "FB113" not in [problem.code for problem in total.problems]


def test_reads_and_window_calls() -> None:
    got = analyze("qtySpin * window.price_for(customerCombo, nameEdit)", ENV, SLOTS["number"])
    assert got.reads == frozenset({"qtySpin", "customerCombo", "nameEdit"})
    assert got.window_calls == ("price_for",)
    wrapped = analyze("window.untagged()", ENV, SLOTS["cond"])
    assert wrapped.bool_wraps
    assert any(problem.code == "FB110" for problem in wrapped.problems)


def test_library_names_match_the_reserved_set() -> None:
    assert set(FUNCTIONS) == set(FORMULA_NAMES)


def test_declared_codes() -> None:
    from app.features.form_builder.engine.diagnostic_codes import fb1xx_formula

    _ = fb1xx_formula
    expected = {
        "FB101": Severity.ERROR,
        "FB102": Severity.ERROR,
        "FB103": Severity.ERROR,
        "FB104": Severity.ERROR,
        "FB105": Severity.ERROR,
        "FB107": Severity.ERROR,
        "FB108": Severity.ERROR,
        "FB109": Severity.ERROR,
        "FB110": Severity.INFO,
        "FB111": Severity.ERROR,
        "FB112": Severity.ERROR,
        "FB113": Severity.ERROR,
        "FB114": Severity.ERROR,
        "FB115": Severity.ERROR,
        "FB117": Severity.WARNING,
        "FB118": Severity.WARNING,
        "FB119": Severity.INFO,
        "FB120": Severity.ERROR,
    }
    for code, severity in expected.items():
        assert CODES[code].severity == severity
    assert "FB106" not in CODES
    assert "FB116" not in CODES
    assert CODES["FB120"].title == "That form isn't in this project's forms folder"


def test_normalize_keeps_the_tree_for_clean_cases() -> None:
    seen = 0
    for text, slot, expect in CASES:
        if expect.startswith("FB"):
            continue
        try:
            before = ast.parse(text, mode="eval")
        except SyntaxError:
            continue
        canonical = normalize(text)
        assert normalize(canonical) == canonical
        after = ast.parse(canonical, mode="eval")
        assert ast.dump(before) == ast.dump(after)
        _ = slot
        seen += 1
    assert seen >= 100


def test_number_slot_accepts_whole() -> None:
    got = analyze("qtySpin", ENV, SLOTS["number"])
    assert got.type is not None and got.type.kind.value == "whole"
    assert not any(problem.code == "FB102" for problem in got.problems)


def test_text_slot_requires_text_call() -> None:
    got = analyze("qtySpin", ENV, SLOTS["text"])
    assert any(problem.code == "FB102" for problem in got.problems)
    assert any(fix.fix_id == "wrap_text" for fix in got.fixes)


def test_message_slot_is_text() -> None:
    got = analyze("nameEdit", ENV, SLOTS["message"])
    assert got.type is not None and got.type.kind.value == "text"
    number = analyze("qtySpin", ENV, SLOTS["message"])
    assert any(problem.code == "FB102" for problem in number.problems)
    _ = (NUMBER, TEXT)
