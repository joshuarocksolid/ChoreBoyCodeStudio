# pyright: reportAttributeAccessIssue=false
"""Review repro (M3.7a gate): the ChangeSet-scoped hit index must equal a full rebuild."""
from __future__ import annotations

import random
from typing import Callable, Iterator, List, Tuple

import pytest

from app.qt.QtWidgets import QApplication
from app.features.form_builder.engine.commands.catalog import DeleteNodes, SetLayoutStretch, SetProperty
from app.features.form_builder.engine.events import PRIORITY_HIT_INDEX
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.hit_index import HitIndex
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue
from app.features.form_builder.qtside.canvas.geometry import HitIndexInvalidator, LiveGeometrySource
from app.features.form_builder.qtside.realize import Realizer
from tests.form_builder.qtside.support import opened
from tests.form_builder.qtside.test_geometry import NESTED

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def live() -> Iterator[Tuple[FormSession, Realizer, HitIndex]]:
    with opened(NESTED) as (session, realizer):
        root = realizer.root_widget
        assert root is not None
        root.show()
        QApplication.processEvents()
        index = HitIndex(LiveGeometrySource(realizer))
        subscription = session.log.subscribe(HitIndexInvalidator(index).on_changeset, priority=PRIORITY_HIT_INDEX)
        try:
            index.ensure_fresh()
            yield session, realizer, index
        finally:
            subscription.close()
            root.hide()


def _id(session: FormSession, name: str) -> NodeId:
    return session.document.by_name(name)[0]


def _table(entries) -> List[Tuple[object, str, object, bool]]:
    return sorted(
        ((entry.node, entry.kind, entry.rect, entry.visible) for entry in entries),
        key=repr,
    )


def _assert_matches_full(realizer: Realizer, index: HitIndex) -> None:
    index.ensure_fresh()
    full = HitIndex(LiveGeometrySource(realizer))
    full.ensure_fresh()
    assert _table(index._entries) == _table(full._entries)


EDITS: List[Tuple[str, Callable[[FormSession], object]]] = [
    ("label text", lambda s: s.log.execute(SetProperty(_id(s, "label"), "text", StringValue("A much longer label text")))),
    ("layout spacing", lambda s: s.log.execute(SetProperty(_id(s, "formLayout"), "spacing", NumberValue(40)))),
    ("layout margin", lambda s: s.log.execute(SetProperty(_id(s, "groupLayout"), "topMargin", NumberValue(40)))),
    ("layout stretch", lambda s: s.log.execute(SetLayoutStretch(_id(s, "formLayout"), "stretch", "0,4,1"))),
    ("delete laid label", lambda s: s.log.execute(DeleteNodes((_id(s, "label"),)))),
    ("tab currentIndex", lambda s: s.log.execute(SetProperty(_id(s, "tabs"), "currentIndex", NumberValue(1)))),
]


@pytest.mark.parametrize(("name", "edit"), EDITS, ids=[name for name, _ in EDITS])
def test_incremental_index_equals_full_rebuild(live: Tuple[FormSession, Realizer, HitIndex], name: str, edit) -> None:
    session, realizer, index = live
    edit(session)
    _assert_matches_full(realizer, index)


@pytest.mark.parametrize(("name", "edit"), EDITS, ids=[name for name, _ in EDITS])
def test_incremental_index_equals_full_rebuild_after_undo(
    live: Tuple[FormSession, Realizer, HitIndex], name: str, edit
) -> None:
    session, realizer, index = live
    edit(session)
    index.ensure_fresh()
    session.log.undo()
    _assert_matches_full(realizer, index)


def test_random_edits_and_undo_match_a_full_rebuild(live: Tuple[FormSession, Realizer, HitIndex]) -> None:
    session, realizer, index = live
    rng = random.Random(37)
    for _step in range(24):
        kind = rng.randrange(5)
        if kind == 0:
            session.log.execute(SetProperty(_id(session, "label"), "text", StringValue("n%d" % rng.randrange(50))))
        elif kind == 1:
            session.log.execute(SetProperty(_id(session, "formLayout"), "spacing", NumberValue(rng.randrange(2, 24))))
        elif kind == 2:
            session.log.execute(
                SetProperty(_id(session, "groupLayout"), "topMargin", NumberValue(rng.randrange(0, 20)))
            )
        elif kind == 3:
            session.log.execute(SetProperty(_id(session, "tabs"), "currentIndex", NumberValue(rng.randrange(2))))
        elif not session.log.undo():
            session.log.redo()
        _assert_matches_full(realizer, index)
