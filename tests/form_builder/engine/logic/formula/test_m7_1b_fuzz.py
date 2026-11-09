"""Evaluate and a generated harness agree on seeded formulas."""

from __future__ import annotations

import ast
import random
import re
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QSpinBox

from app.features.form_builder.engine.logic.formula import (
    EvalBlank,
    analyze,
    compile_formula,
    helper_sources,
    helper_table,
)
from app.features.form_builder.engine.logic.formula.env import SlotKind
from tests.form_builder.engine.logic.formula.test_m7_1b_compile import allowed_names, env_for

_HELPER_RE = re.compile(r"\b(_cbcs_[A-Za-z0-9_]*)\b")


def _close(helper_ids: tuple) -> list:
    table = list(helper_table())
    sources = {helper_id: source for helper_id, source in table}
    order = [helper_id for helper_id, _source in table]
    needed = set(helper_ids)
    changed = True
    while changed:
        changed = False
        for helper_id in list(needed):
            for found in _HELPER_RE.findall(sources[helper_id]):
                if found in sources and found not in needed:
                    needed.add(found)
                    changed = True
    return [helper_id for helper_id in order if helper_id in needed]


def _num(rng: random.Random, depth: int) -> str:
    leaves = (
        "qty",
        "1",
        "2",
        "0",
        "10",
        "window.extra()",
        "abs(qty)",
        "if_blank(qty, 1)",
        "priceEdit",
        "round(qty)",
    )
    if depth <= 0 or rng.random() < 0.45:
        return rng.choice(leaves)
    op = rng.choice(("+", "-", "*", "/"))
    return "(%s %s %s)" % (_num(rng, depth - 1), op, _num(rng, depth - 1))


def _text(rng: random.Random, depth: int) -> str:
    leaves = ("nameEdit", "caption", '"a"', '"hello"', '""', "upper(nameEdit)", "trim(caption)")
    if depth <= 0 or rng.random() < 0.5:
        return rng.choice(leaves)
    if rng.random() < 0.5:
        return "(%s if ok else %s)" % (_text(rng, depth - 1), _text(rng, depth - 1))
    return "(%s + %s)" % (_text(rng, depth - 1), _text(rng, depth - 1))


def _bool(rng: random.Random, depth: int) -> str:
    leaves = (
        "ok",
        "True",
        "False",
        "is_blank(qty)",
        "is_blank(nameEdit)",
        "qty < 3",
        "qty == 0",
        "priceEdit > 0",
        "nameEdit != caption",
    )
    if depth <= 0 or rng.random() < 0.5:
        return rng.choice(leaves)
    choice = rng.choice(("not", "and", "or", "if"))
    if choice == "not":
        return rng.choice(("not ok", "not True", "not is_blank(qty)", "not is_blank(nameEdit)"))
    if choice == "if":
        return "(%s if %s else %s)" % (_bool(rng, depth - 1), _bool(rng, depth - 1), _bool(rng, depth - 1))
    op = "and" if choice == "and" else "or"
    return "(%s %s %s)" % (_bool(rng, depth - 1), op, _bool(rng, depth - 1))


def _formula(rng: random.Random, kind: str) -> str:
    if kind == "num":
        if rng.random() < 0.25:
            return "(%s if ok else %s)" % (_num(rng, 2), _num(rng, 2))
        return _num(rng, 3)
    if kind == "text":
        return _text(rng, 3)
    return _bool(rng, 3)


def _state(rng: random.Random) -> dict:
    return {
        "name": rng.choice(["", "Ada", "  x  ", "hello", " "]),
        "price": rng.choice(["", "$1.50", "2.25", "(3.00)", "-$1.00", "bad", "  "]),
        "qty": rng.randrange(0, 20),
        "ok": bool(rng.randrange(2)),
        "caption": rng.choice(["", "Hi", "Total", "  "]),
        "extra": rng.randrange(0, 9),
    }


def fuzz_plans() -> list:
    rng = random.Random(71031)
    plans = []
    for index in range(40):
        if index % 7 == 0:
            text = "window.extra()"
        else:
            text = _formula(rng, ("num", "text", "bool")[index % 3])
        states = [_state(rng) for _index in range(20)]
        plans.append((text, states))
    return plans


def iter_fuzz_sources() -> list:
    env = env_for()
    sources = []
    for text, _states in fuzz_plans():
        analysis = analyze(text, env, SlotKind("expr"))
        sources.append(compile_formula(analysis, env).source)
    return sources


def fuzz_names() -> set:
    return allowed_names(env_for())


def _harness(source: str, helper_ids: tuple) -> str:
    helpers = helper_sources(_close(helper_ids))
    return (
        "from decimal import Decimal, ROUND_HALF_UP\n"
        "from datetime import date, datetime, time\n"
        "import re\n"
        "class _NeedsValue(Exception):\n"
        "    pass\n"
        "%s\n"
        "class Ui(object):\n"
        "    def run(self):\n"
        "        return %s\n"
    ) % (helpers, source)


def _same(got: object, harness_value: object, harness_exc: object) -> bool:
    if isinstance(got, EvalBlank):
        if harness_exc is None:
            return False
        if got.reason == "needs a window value":
            return harness_exc.__class__.__name__ == "_NeedsValue"
        return got.reason == str(harness_exc)
    return harness_exc is None and got == harness_value


@pytest.mark.unit
@pytest.mark.timeout(180)
def test_fuzz_matches_generated_harness(qapp: object) -> None:
    del qapp
    widgets = {
        "nameEdit": QLineEdit(),
        "priceEdit": QLineEdit(),
        "qty": QSpinBox(),
        "ok": QCheckBox(),
        "caption": QLabel(),
    }
    env = env_for()
    ran = 0
    omitted = 0
    failures = []
    for index, (text, states) in enumerate(fuzz_plans()):
        analysis = analyze(text, env, SlotKind("expr"))
        problems = [(item.code, item.message) for item in analysis.problems]
        assert problems == [], (text, problems)
        emitted = compile_formula(analysis, env)
        for state_index, state in enumerate(states):
            widgets["nameEdit"].setText(state["name"])
            widgets["priceEdit"].setText(state["price"])
            widgets["qty"].setValue(state["qty"])
            widgets["ok"].setChecked(state["ok"])
            widgets["caption"].setText(state["caption"])
            omit = state_index == 0 and "._form." in emitted.source
            window_values = {} if omit else {"extra": state["extra"]}
            if omit:
                omitted += 1
            harness = _harness(emitted.source, emitted.helpers)
            ast.parse(harness, filename="<harness>", feature_version=(3, 9))
            namespace = {}  # type: dict
            exec(harness, namespace)  # noqa: S102
            needs = namespace["_NeedsValue"]

            class _Form(object):
                def extra(self, *_args: object) -> object:
                    if "extra" not in window_values:
                        raise needs()
                    return window_values["extra"]

            ui = namespace["Ui"]()
            ui.nameEdit = widgets["nameEdit"]
            ui.priceEdit = widgets["priceEdit"]
            ui.qty = widgets["qty"]
            ui.ok = widgets["ok"]
            ui.caption = widgets["caption"]
            ui._form = _Form()
            reader = SimpleNamespace(
                nameEdit=widgets["nameEdit"],
                priceEdit=widgets["priceEdit"],
                qty=widgets["qty"],
                ok=widgets["ok"],
                caption=widgets["caption"],
            )
            got = evaluate_safe(emitted, reader, window_values)
            harness_value = None
            harness_exc = None
            try:
                harness_value = ui.run()
            except Exception as exc:
                harness_exc = exc
            ran += 1
            if not _same(got, harness_value, harness_exc) and len(failures) < 8:
                failures.append((index, text, emitted.source, state, got, harness_value, harness_exc))
    assert ran >= 800
    assert omitted >= 1
    assert failures == []


def evaluate_safe(emitted: object, reader: object, window_values: dict) -> object:
    from app.features.form_builder.engine.logic.formula import evaluate

    return evaluate(emitted, reader, window_values)
