"""Seeded command sequences. Replay, undo and each inverse (CONTRACTS.md section 3.9)."""

from __future__ import annotations

import os
import random
from typing import List, Optional

import pytest

from app.features.form_builder.engine.commands.catalog import (
    AddConnection,
    DeleteNodes,
    InsertFragment,
    MoveNodes,
    Rename,
    SetLayoutStretch,
    SetProperty,
)
from app.features.form_builder.engine.commands.log import replay
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, button_spec, open_log, saved

SEQUENCES = 200
STEPS = 30


def _widgets(doc: UiDocument) -> List[WidgetNode]:
    layout = doc.root.layout
    assert layout is not None
    found = []
    for item in layout.items:
        if isinstance(item.content, WidgetNode):
            found.append(item.content)
    return found


def _command(doc: UiDocument, rng: random.Random, step: int) -> Optional[object]:
    widgets = _widgets(doc)
    if not widgets:
        return None
    layout = doc.root.layout
    assert layout is not None
    roll = rng.randrange(7)
    if roll == 0:
        widget = rng.choice(widgets)
        return SetProperty(widget.id, "text", StringValue("t%s" % step))
    if roll == 1:
        widget = rng.choice(widgets)
        return Rename(widget.id, "n%s" % step)
    if roll == 2 and len(widgets) >= 2:
        return MoveNodes((widgets[0].id,), InBoxLayout(layout.id, len(layout.items)))
    if roll == 3 and len(widgets) < 6:
        spec = button_spec("extra%s" % step, "E")
        return InsertFragment(InBoxLayout(layout.id, 0), Fragment(nodes=(spec,)))
    if roll == 4 and len(widgets) > 1:
        return DeleteNodes((widgets[-1].id,))
    if roll == 5 and len(widgets) >= 2:
        left = widgets[0].object_name
        right = widgets[1].object_name
        return AddConnection(left, "clicked", right, "clear")
    if roll == 6:
        return SetLayoutStretch(layout.id, "stretch", "1,0" if step % 2 == 0 else None)
    return SetProperty(widgets[0].id, "text", StringValue("t%s" % step))


def _inverses_match(before: NodeSpec, entry_ops: object, entry_inverses: object, live: UiDocument) -> None:
    clone = UiDocument.from_spec(before)
    for op, recorded in zip(entry_ops, entry_inverses):  # type: ignore[arg-type]
        fingerprint = clone.fingerprint()
        inverse = mutate.apply(clone, op)
        assert inverse == recorded
        mutate.apply(clone, inverse)
        assert clone.fingerprint() == fingerprint
        mutate.apply(clone, op)
    assert clone.fingerprint() == live.fingerprint()


def _run_sequence(seed: int) -> None:
    log = open_log(BOX)
    doc = log.document
    original_text = saved(doc)
    original_fp = doc.fingerprint()
    rng = random.Random(seed)
    done = 0
    attempts = 0
    while done < STEPS and attempts < STEPS * 4:
        attempts += 1
        if rng.randrange(10) < 2 and log.can_undo():
            assert log.undo()
            done += 1
            continue
        if rng.randrange(10) == 0 and log.can_redo():
            assert log.redo()
            done += 1
            continue
        command = _command(doc, rng, seed * 1000 + attempts)
        if command is None:
            continue
        before = doc.to_spec()
        outcome = log.execute(command)  # type: ignore[arg-type]
        if outcome.noop:
            continue
        entry = log.entries()[-1]
        _inverses_match(before, entry.ops, entry.inverse_ops, doc)
        done += 1
    assert done == STEPS, "seed %s stopped after %s steps" % (seed, done)
    replayed = replay(BOX, log.entries())
    assert replayed.fingerprint() == doc.fingerprint()
    while log.redo():
        pass
    tip = doc.fingerprint()
    while log.undo():
        pass
    assert saved(doc) == original_text
    assert doc.fingerprint() == original_fp
    while log.redo():
        pass
    assert doc.fingerprint() == tip


def test_fast_lane_covers_five_thousand_steps() -> None:
    assert SEQUENCES * STEPS >= 5000


@pytest.mark.timeout(180)
def test_seeded_sequences_replay_undo_and_redo() -> None:
    chosen = os.environ.get("FB_SEED")
    seeds = [int(chosen)] if chosen else list(range(SEQUENCES))
    for seed in seeds:
        _run_sequence(seed)
