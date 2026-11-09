"""SetItems is one undo step per widget and session, and replay matches live."""

from __future__ import annotations

import random

from app.features.form_builder.engine.commands.catalog import SetItems
from app.features.form_builder.engine.commands.log import replay
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.qtside.items.model import (
    add_header,
    add_root,
    add_sibling,
    commit_slots,
    delete_at,
    delete_header,
    flat_paths,
    load_draft,
    move_sibling,
    nest,
    set_cell_text,
    set_header_text,
    set_item_value,
    set_text,
)
from tests.form_builder.engine.commands._support import nid, open_log  # pyright: ignore[reportMissingImports]

SEED = 4401
CASES = 24

FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QComboBox" name="combo"/>
  <widget class="QListWidget" name="list"/>
  <widget class="QTreeWidget" name="tree"/>
  <widget class="QTableWidget" name="table"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def test_item_sessions_replay_and_do_not_merge_across_widgets() -> None:
    """Seed 4401, 24 sessions. Replay equals live. Undo-all equals the original bytes."""
    original = FORM
    log = open_log(original)
    rng = random.Random(SEED)
    names = ("combo", "list", "tree", "table")
    for case in range(CASES):
        name = names[case % len(names)]
        token = "session-%d" % case
        _session(log, name, token, rng)
        assert log.undo_label() == "Edit items of %s" % name
        assert len([entry for entry in log.entries() if entry.merge_token == token]) == 1
    live = write_ui(log.document).text
    replayed = write_ui(replay(original, log.entries())).text
    assert replayed == live
    while log.undo_label() is not None:
        assert log.undo()
    assert write_ui(log.document).text == original
    _session(log, "combo", "a", rng)
    _session(log, "list", "a", rng)
    _session(log, "combo", "b", rng)
    tokens = [entry.merge_token for entry in log.entries()]
    assert tokens.count("a") == 2
    assert tokens.count("b") == 1


def _session(log, name, token, rng):
    widget = nid(log.document, name)
    draft = load_draft(log.document, widget)
    assert draft is not None
    for _step in range(rng.randint(2, 5)):
        draft = _mutate(draft, rng)
        items, rows, columns = commit_slots(draft)
        log.execute(SetItems(widget, items, rows, columns, merge_token=token, widget_name=draft.name))
        fresh = load_draft(log.document, widget)
        assert fresh is not None
        draft = fresh


def _mutate(draft, rng):
    kind = draft.kind
    roll = rng.randrange(6)
    if kind == "table":
        if roll == 0:
            return add_header(draft, "row", len(draft.rows) - 1)
        if roll == 1:
            return add_header(draft, "column", len(draft.columns) - 1)
        if roll == 2 and draft.rows:
            return delete_header(draft, "row", rng.randrange(len(draft.rows)))
        row = rng.randrange(max(1, len(draft.rows)))
        column = rng.randrange(max(1, len(draft.columns)))
        return set_cell_text(draft, row, column, "c%d" % rng.randrange(100))
    if not draft.items:
        return add_root(draft)[0]
    paths = flat_paths(draft.items)
    path, _item = paths[rng.randrange(len(paths))]
    if roll == 0:
        return add_sibling(draft, path)[0]
    if roll == 1 and len(paths) > 1:
        return delete_at(draft, path)
    if roll == 2:
        return move_sibling(draft, path, -1 if rng.randrange(2) else 1)[0]
    if roll == 3 and kind == "tree":
        return nest(draft, path)[0]
    if roll == 4 and kind == "tree":
        return set_header_text(draft, "column", 0, "Col%d" % rng.randrange(5))
    if roll == 5:
        return set_item_value(draft, path, "toolTip", StringValue("tip"))
    return set_text(draft, path, 0, "t%d" % rng.randrange(100))
