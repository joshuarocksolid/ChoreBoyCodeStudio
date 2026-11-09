"""Line-item save plan (CONTRACTS.md section 19.5 step 4).

Qt-free. The generated form emits these functions through the helper table, so
the running module and the tests share one algorithm.
"""

from __future__ import annotations

import inspect
from typing import Mapping, Optional, Sequence, Tuple

from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.formula.check import analyze
from app.features.form_builder.engine.logic.formula.compile import compile_formula
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind
from app.features.form_builder.engine.logic.formula.nodes import Bin
from app.features.form_builder.engine.logic.formula.types import (
    ANY,
    DATE,
    DATETIME,
    MONEY,
    NUMBER,
    TEXT,
    TIME,
    WHOLE,
    YESNO,
    FType,
)


def _cbcs_plan_lines(
    snapshot,
    current,
    deleted,
    key_column,
    position_column,
    stored_columns,
    unique_pair,
):
    """Deletes, data updates, parks, final positions, then inserts.

    ``snapshot`` rows carry the loaded key and the loaded position. ``current``
    is visual order. A new row has no key. Position on a current row is ignored.
    The new position is the visual index plus one. An empty result means the
    stored lines match the snapshot.
    """

    snap = {}
    order = []
    for row in snapshot:
        key = row.get(key_column)
        if key is None or key in snap:
            raise ValueError("snapshot key")
        snap[key] = row
        order.append(key)
    deleted_keys = []
    seen = set()
    for key in deleted:
        if key is None or key in seen or key not in snap:
            raise ValueError("deleted key")
        seen.add(key)
        deleted_keys.append(key)
    current_keys = []
    for row in current:
        key = row.get(key_column)
        if key is None:
            continue
        if key in seen or key not in snap or key in current_keys:
            raise ValueError("current key")
        current_keys.append(key)
    for key in order:
        if key not in seen and key not in set(current_keys):
            raise ValueError("missing key")
    if unique_pair and not position_column:
        raise ValueError("position")
    ops = []
    for key in deleted_keys:
        ops.append(("delete", key))
    for row in current:
        key = row.get(key_column)
        if key is None:
            continue
        original = snap[key]
        changes = []
        for column in stored_columns:
            if row.get(column) != original.get(column):
                changes.append((column, row.get(column)))
        if changes:
            ops.append(("update", key, tuple(changes)))
    movers = []
    if position_column:
        for index, row in enumerate(current):
            key = row.get(key_column)
            if key is None:
                continue
            final = index + 1
            if snap[key].get(position_column) != final:
                movers.append((key, final))
    # Park above every stored position, whether or not the schema cache recorded
    # UNIQUE (link, position). A negative park trips CHECK (position > 0).
    if position_column and movers:
        # First free integer above every stored position. Decimal and float
        # positions count. bool is a Real only because it subclasses int.
        # Imports stay inside so the generated module, which execs this source, has them.
        import decimal
        import math
        import numbers

        ceiling = 1
        for row in snapshot:
            pos = row.get(position_column)
            # Decimal is NUMERIC and is not a numbers.Real. bool is a Real
            # only because it subclasses int.
            if isinstance(pos, bool):
                continue
            if not isinstance(pos, (numbers.Real, decimal.Decimal)):
                continue
            slot = int(math.floor(pos)) + 1
            if slot > ceiling:
                ceiling = slot
        for ordinal, pair in enumerate(movers):
            ops.append(("park", pair[0], ceiling + ordinal))
    for key, final in movers:
        ops.append(("position", key, final))
    for index, row in enumerate(current):
        if row.get(key_column) is not None:
            continue
        values = []
        for column in stored_columns:
            values.append((column, row.get(column)))
        if position_column:
            values.append((position_column, index + 1))
        ops.append(("insert", tuple(values)))
    return tuple(ops)


def _cbcs_lines_differ(snapshot, current, key_column, stored_columns):
    """True when visual order or stored values differ. Position is not compared."""

    def view(rows):
        found = []
        for row in rows:
            found.append((row.get(key_column), tuple(row.get(column) for column in stored_columns)))
        return tuple(found)

    return view(snapshot) != view(current)


def line_plan_source() -> str:
    """The two functions, as the generated module will define them."""

    return inspect.getsource(_cbcs_plan_lines) + "\n" + inspect.getsource(_cbcs_lines_differ)


_KIND_TYPE = {
    "any": ANY,
    "whole": WHOLE,
    "int": WHOLE,
    "money": MONEY,
    "decimal": NUMBER,
    "number": NUMBER,
    "yesno": YESNO,
    "bool": YESNO,
    "date": DATE,
    "time": TIME,
    "datetime": DATETIME,
    "text": TEXT,
    "calc": NUMBER,
}


def column_type(kind: str) -> FType:
    return _KIND_TYPE.get(kind, TEXT)


def type_for_kind(kind_name: str) -> FType:
    """The formula type for a schema column kind. Unknown kinds stay text."""

    return {
        "whole": WHOLE,
        "number": NUMBER,
        "money": MONEY,
        "text": TEXT,
        "date": DATE,
        "time": TIME,
        "datetime": DATETIME,
        "yesno": YESNO,
    }.get(kind_name, TEXT)


def compile_line_formula(
    text: str,
    columns: Sequence[Tuple[str, str]],
    target_kind: str,
    attrs: Optional[Mapping[str, Mapping[str, FType]]] = None,
) -> Tuple[str, Tuple[str, ...], Tuple[Tuple[str, str], ...], Tuple[str, ...], Tuple[str, ...]]:
    """Compile one grid formula. Problems are design-time codes. Source is empty then.

    The result is ``(source, helper ids, imports, problem codes, denominator sources)``.
    """

    stripped = text.strip()
    if not stripped:
        return ("", (), (), (), ())
    mapping = {name: column_type(kind) for name, kind in columns}
    env = FormulaEnv.for_test(row_columns=mapping, row_attrs=attrs or {})
    analysis = analyze(stripped, env, SlotKind.value(column_type(target_kind)))
    problems = []
    for problem in analysis.problems:
        spec = CODES.get(problem.code)
        if spec is None or spec.severity == Severity.ERROR:
            problems.append(problem.code)
    if problems or analysis.tree is None:
        return ("", (), (), tuple(problems), ())
    try:
        emitted = compile_formula(analysis, env)
    except ValueError:
        return ("", (), (), ("FB108",), ())
    denoms = []

    def walk(node: object) -> None:
        if isinstance(node, Bin) and node.op == "/":
            denoms.append(_node_source(node.b, env))
        for child in _formula_children(node):
            walk(child)

    walk(analysis.tree)
    return (emitted.source, tuple(emitted.helpers), tuple(emitted.imports), (), tuple(item for item in denoms if item))


def _node_source(node: object, env: FormulaEnv) -> str:
    from app.features.form_builder.engine.logic.formula.nodes import Analysis

    sub = Analysis(
        text="",
        tree=node,  # type: ignore[arg-type]
        type=getattr(node, "type", None),
        problems=(),
        fixes=(),
        reads=frozenset(),
        window_calls=(),
        bool_wraps=(),
    )
    try:
        return compile_formula(sub, env).source
    except ValueError:
        return ""


def _formula_children(node: object) -> Tuple[object, ...]:
    if isinstance(node, Bin):
        return (node.a, node.b)
    args = getattr(node, "args", None)
    if args is not None:
        return tuple(args)
    child = getattr(node, "x", None)
    if child is not None:
        return (child,)
    test = getattr(node, "test", None)
    if test is not None:
        return (test, getattr(node, "then", None), getattr(node, "other", None))
    return ()


def link_position_unique(unique_keys: Sequence[Sequence[str]], link: str, position: str) -> bool:
    """True when some unique key is exactly the link and the position, either order."""

    if not link or not position:
        return False
    wanted = {link, position}
    for key in unique_keys:
        if set(key) == wanted and len(tuple(key)) == 2:
            return True
    return False


def plan_lines(
    snapshot: Sequence[Mapping[str, object]],
    current: Sequence[Mapping[str, object]],
    deleted: Sequence[object],
    key_column: str,
    position_column: str,
    stored_columns: Tuple[str, ...],
    unique_pair: bool,
) -> Tuple[Tuple[object, ...], ...]:
    """The typed entry the tests call. Same function the form emits."""

    return _cbcs_plan_lines(
        snapshot,
        current,
        deleted,
        key_column,
        position_column,
        stored_columns,
        unique_pair,
    )
