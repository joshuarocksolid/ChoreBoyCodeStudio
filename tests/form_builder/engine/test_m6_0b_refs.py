"""M6.0b: formula tokens and step targets (CONTRACTS.md section 15.8).

The rename property: for random formulas built from known pieces, a rename changes exactly
the characters of the NAME tokens that refer to the old name, and nothing else.
"""

from __future__ import annotations

import os
import random
from typing import List, Tuple

import pytest

from app.features.form_builder.engine.logic.codec import parse_steps
from app.features.form_builder.engine.logic.refs import (
    declare_name_fields,
    formula_mentions,
    formula_names,
    opaque_mentions,
    rename_formula,
    rename_formulas_in_logic,
    rename_step_targets,
    step_target_names,
)


def _seed() -> int:
    raw = os.environ.get("FB_SEED")
    return int(raw) if raw else 20261029


@pytest.mark.parametrize(
    "text,expected",
    [
        ("qtySpin * priceSpin", "qty * priceSpin"),
        ("qtySpin.text + 1", "qty.text + 1"),
        ("form.qtySpin", "form.qtySpin"),
        ('"qtySpin" + \'qtySpin\'', '"qtySpin" + \'qtySpin\''),
        ("  qtySpin   *\tqtySpin", "  qty   *\tqty"),
        ("round(qtySpin, 2)", "round(qty, 2)"),
        ("f(qtySpin=1, other=qtySpin)", "f(qtySpin=1, other=qty)"),
        ("(qtySpin == 1)", "(qty == 1)"),
        ("[qtySpin for qtySpin in x]", "[qty for qty in x]"),
        ("qtySpin # qtySpin", "qty # qtySpin"),
        ("qtySpin +", "qty +"),
        ("a if qtySpin else b", "a if qty else b"),
        ("not qtySpin", "not qty"),
        ("qtySpinner + qtySpin2", "qtySpinner + qtySpin2"),
        ("f(\n  qtySpin,\n  qtySpin=2)", "f(\n  qty,\n  qtySpin=2)"),
        ("é + qtySpin", "é + qty"),
        ("", ""),
    ],
)
def test_rename_formula_token_rules(text: str, expected: str) -> None:
    assert rename_formula(text, {"qtySpin": "qty"}) == expected


@pytest.mark.parametrize("text", ["qtySpin 'unterminated", "qtySpin $ 1", "(qtySpin", "qtySpin ?", '"""qtySpin'])
def test_text_that_does_not_tokenize_is_left_unchanged(text: str) -> None:
    assert rename_formula(text, {"qtySpin": "qty"}) == text
    assert not formula_mentions(text, "qtySpin")


def test_a_simultaneous_swap_does_not_chain() -> None:
    assert rename_formula("a + b + a", {"a": "b", "b": "a"}) == "b + a + b"
    assert rename_formula("a + b", {"a": "b", "b": "c"}) == "b + c"


def test_names_and_mentions() -> None:
    assert formula_names("a.b + c(d=e, f) + 'g'") == ("a", "c", "e", "f")
    assert formula_mentions("a.b", "a") and not formula_mentions("a.b", "b")


def test_json_formulas_and_step_targets_rename_through_the_codec() -> None:
    steps = (
        '[{"do": "slot", "target": "x", "slot": "clear()"},'
        ' {"do": "set", "field": "x", "formula": "x + y", "when": "y > x"},'
        ' {"do": "clear", "fields": ["x", "y", "x"]},'
        ' {"do": "openForm", "form": "x", "key": "x"}]'
    )
    renamed = rename_step_targets(steps, {"x": "z"})
    assert renamed is not None
    read = parse_steps(renamed)
    assert read.steps[0].field("target") == "z"
    assert read.steps[1].field("field") == "z" and read.steps[1].field("formula") == "x + y"
    assert read.steps[2].field("fields") == ("z", "y", "z")
    assert read.steps[3].field("form") == "x" and read.steps[3].field("key") == "x"  # a module name; key not declared
    formulas = rename_formulas_in_logic("cbcsOnClicked", steps, {"x": "z"})
    assert formulas is not None
    after = parse_steps(formulas)
    assert after.steps[1].when == "y > z" and after.steps[1].field("formula") == "z + y"
    assert after.steps[1].field("field") == "x"
    assert step_target_names(steps) == ("x", "y")
    assert rename_step_targets(steps, {"q": "r"}) is None
    declare_name_fields("openForm", ("key",))
    try:
        again = rename_step_targets(steps, {"x": "z"})
        assert again is not None and parse_steps(again).steps[3].field("key") == "z"
    finally:
        declare_name_fields("openForm", ())


def test_json_formulas_in_checks_and_rows() -> None:
    checks = '[{"check": "range", "min": "a + 1", "max": 5, "message": "a"}, {"check": "formula", "formula": "a > b", "message": "a b"}]'
    renamed = rename_formulas_in_logic("cbcsValidate", checks, {"a": "n"})
    assert renamed is not None
    assert '"min": "n + 1"' in renamed and '"formula": "n > b"' in renamed
    assert '"message": "a"' in renamed and '"message": "a b"' in renamed
    rows = '{"table": "t", "columns": [{"name": "x", "formula": "qty * price", "default": "qty"}]}'
    got = rename_formulas_in_logic("cbcsRows", rows, {"qty": "count"})
    assert got is not None and '"formula": "count * price"' in got and '"default": "count"' in got
    assert rename_formulas_in_logic("cbcsEnabledWhen", "a and b", {"a": "c"}) == "c and b"
    assert rename_formulas_in_logic("cbcsKind", "a", {"a": "c"}) is None
    assert rename_formulas_in_logic("cbcsOnClicked", "[1, 2", {"a": "c"}) is None


def test_opaque_search_finds_names_in_unknown_structures() -> None:
    assert opaque_mentions('{"version": 9, "later": {"who": ["nameEdit"], "rule": "x > nameEdit.value"}}', "nameEdit")
    assert opaque_mentions('{"rule": "nameEdit.value > 1"}', "nameEdit")
    assert not opaque_mentions('{"rule": "other.nameEdit", "n": 3}', "nameEdit")
    # unknown text is searched, not understood, so a sentence that holds the word counts too
    assert opaque_mentions('{"text": "nameEdit is bad"}', "nameEdit")
    assert opaque_mentions("useName and total", "total")
    assert not opaque_mentions("not json at all {", "nameEdit")


# --- the property ----------------------------------------------------------

_NAMES = ["qtySpin", "priceSpin", "a", "total", "x1"]
_NEW_NAMES = ["renamed", "Q_2", "\u00e9"]


def _formula(rng: random.Random, old: str, new: str) -> Tuple[str, str]:
    """A formula that tokenizes, and the text it must become after ``old`` -> ``new``."""
    before: List[str] = []
    after: List[str] = []
    for _ in range(rng.randrange(1, 9)):
        previous = before[-1] if before else ""
        gap = rng.choice([" ", "  ", "\t", ""]) if previous and not previous[-1].isalnum() else " "
        roll = rng.randrange(9)
        if roll <= 2:
            name = rng.choice(_NAMES + [old, old])
            piece, changed = name, new if name == old else name
        elif roll == 3:
            piece = changed = "w." + old  # an attribute, never a reference
        elif roll == 4:
            piece = changed = '"%s"' % old  # a string
        elif roll == 5:
            piece = changed = "f(%s=1)" % old  # a keyword argument's name
        elif roll == 6:
            piece, changed = "f(k=%s)" % old, "f(k=%s)" % new
        elif roll == 7:
            piece = changed = str(rng.randrange(100))
        else:
            piece = changed = rng.choice(["+", "*", "==", "and", "or", "not"])
            gap = " "
        before.append(gap + piece)
        after.append(gap + changed)
    return "".join(before), "".join(after)


def test_rename_changes_exactly_the_name_tokens() -> None:
    rng = random.Random(_seed())
    for _ in range(800):
        old = rng.choice(_NAMES)
        new = rng.choice(_NEW_NAMES)
        text, expected = _formula(rng, old, new)
        got = rename_formula(text, {old: new})
        assert got == expected, text
        # only token spans moved, so renaming back restores every byte
        assert rename_formula(got, {new: old}) == text
