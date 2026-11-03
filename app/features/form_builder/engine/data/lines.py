"""Line-item save plan (CONTRACTS.md section 19.5 step 4).

Qt-free. The generated form emits these functions through the helper table, so
the running module and the tests share one algorithm.
"""

from __future__ import annotations

import inspect
from typing import Mapping, Sequence, Tuple


def _cbcs_plan_lines(
    snapshot,
    current,
    deleted,
    key_column,
    position_column,
    stored_columns,
    unique_pair,
):
    """Deletes, data updates, parks, inserts, then final positions.

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
    if unique_pair and movers:
        floor = 0
        for row in snapshot:
            pos = row.get(position_column)
            if type(pos) is int and pos < floor:
                floor = pos
        for ordinal, pair in enumerate(movers):
            ops.append(("park", pair[0], floor - 1 - ordinal))
    for index, row in enumerate(current):
        if row.get(key_column) is not None:
            continue
        values = []
        for column in stored_columns:
            values.append((column, row.get(column)))
        if position_column:
            values.append((position_column, index + 1))
        ops.append(("insert", tuple(values)))
    for key, final in movers:
        ops.append(("position", key, final))
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
