"""Selection follows ChangeSets and notifies only after the log finishes."""

from __future__ import annotations

import os
import random

import pytest

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import DeleteNodes, InsertFragment, MoveNodes
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS
from app.features.form_builder.engine.query.selection import SelectionSource, SelectionState
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment
from tests.form_builder.engine.commands._support import button_spec
from tests.form_builder.qtside.support import open_session
from tests.support.form_builder.gen import NESTED, command_for

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QHBoxLayout" name="row">
   <item>
    <widget class="QWidget" name="leftPane">
     <layout class="QVBoxLayout" name="left">
      <item><widget class="QLabel" name="stay"><property name="text"><string>a</string></property></widget></item>
     </layout>
    </widget>
   </item>
   <item>
    <widget class="QWidget" name="rightPane">
     <layout class="QVBoxLayout" name="right">
      <item><widget class="QPushButton" name="moved"><property name="text"><string>Go</string></property></widget></item>
     </layout>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""


def _named(session, name):
    found = session.document.by_name(name)
    assert found, name
    return found[0]


def test_delete_drops_the_id_and_undo_restores_the_snapshot() -> None:
    session = open_session(_FORM)
    button = _named(session, "moved")
    session.selection.set((button,), source=SelectionSource.CANVAS)
    ancestors = []
    node = session.document.get(button)
    while node is not None and node.parent_id is not None:
        ancestors.append(node.parent_id)
        node = session.document.get(node.parent_id)
    session.log.execute(DeleteNodes((button,)))
    state = session.selection.state
    assert button not in state.ids
    assert state.current is None or state.current in ancestors
    assert all(session.document.contains(node_id) for node_id in state.ids)
    assert state.current is None or state.current in state.ids
    assert session.log.undo()
    assert session.selection.state.current == button
    assert session.log.redo()
    assert button not in session.selection.state.ids


def test_a_move_keeps_the_moved_widget_selected() -> None:
    session = open_session(_FORM)
    button = _named(session, "moved")
    left = _named(session, "leftPane")
    layout = session.document.get(left)
    assert isinstance(layout, WidgetNode)
    box = layout.layout
    assert isinstance(box, LayoutNode)
    session.selection.set((button,), source=SelectionSource.OUTLINE)
    session.log.execute(MoveNodes((button,), InBoxLayout(box.id, 0)))
    assert session.selection.state.current == button


def test_listeners_run_after_the_rest_of_the_log() -> None:
    session = open_session(_FORM)
    left = _named(session, "leftPane")
    layout = session.document.get(left)
    assert isinstance(layout, WidgetNode) and isinstance(layout.layout, LayoutNode)
    box_id = layout.layout.id
    seen = []
    during = []

    def on_selection(change) -> None:
        seen.append(change.source)

    def during_log(_changeset) -> None:
        during.append(len(seen))

    session.selection.subscribe(on_selection)
    session.log.subscribe(during_log, priority=PRIORITY_DIAGNOSTICS)
    fragment = Fragment(nodes=(button_spec("added"),))
    try:
        session.log.execute(InsertFragment(InBoxLayout(box_id, 0), fragment))
    except CommandRejected as exc:
        raise AssertionError("insert was rejected: %s" % exc)
    assert during == [0]
    assert seen


def test_removing_current_moves_to_the_nearest_ancestor() -> None:
    session = open_session(_FORM)
    button = _named(session, "moved")
    chain = []
    node = session.document.get(button)
    while node is not None and node.parent_id is not None:
        chain.append(node.parent_id)
        node = session.document.get(node.parent_id)
    session.selection.set((button,), source=SelectionSource.CANVAS)
    session.log.execute(DeleteNodes((button,)))
    expected = next(node_id for node_id in chain if session.document.contains(node_id))
    state = session.selection.state
    assert state.current == expected
    assert state.current in state.ids
    assert button not in state.ids


@pytest.mark.timeout(60)
def test_selection_follows_random_sequences() -> None:
    chosen = os.environ.get("FB_SEED")
    seeds = [int(chosen)] if chosen else range(200)
    forms = (NESTED, _FORM)
    for seed in seeds:
        rng = random.Random(seed)
        session = open_session(forms[seed % len(forms)])
        session.selection.set((session.document.root.id,), source=SelectionSource.PROGRAM)
        for step in range(30):
            command = command_for(session.document, rng, step)
            if command is None:
                continue
            try:
                session.log.execute(command)
            except CommandRejected:
                continue
            _assert_selection(session)
            if not session.log.can_undo():
                continue
            before = session.log.entries()[-1].selection_before
            after = session.log.entries()[-1].selection_after
            assert session.log.undo()
            _assert_selection(session)
            assert session.selection.state == SelectionState(before.ids, before.current)
            assert session.log.redo()
            _assert_selection(session)
            assert session.selection.state == SelectionState(after.ids, after.current)


def _assert_selection(session) -> None:
    state = session.selection.state
    assert all(session.document.contains(node_id) for node_id in state.ids)
    if not state.ids:
        assert state.current is None
        return
    assert state.current in state.ids
