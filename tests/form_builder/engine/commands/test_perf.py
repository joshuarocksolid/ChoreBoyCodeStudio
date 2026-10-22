"""Edit cost stays on the nodes that changed (CONTRACTS.md section 12)."""

from __future__ import annotations

import os
import time

import pytest

from app.features.form_builder.engine.commands.catalog import DeleteNodes, InsertFragment, MoveNodes, SetProperty, Wrap
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, button_spec, nid, open_log


def _bulk(count: int) -> str:
    rows = []
    for index in range(count):
        rows.append(
            "<item><widget class=\"QPushButton\" name=\"b%s\">"
            "<property name=\"text\"><string>x</string></property>"
            "</widget></item>" % index
        )
    inner = "".join(rows)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<ui version=\"4.0\"><class>Form</class>"
        "<widget class=\"QWidget\" name=\"Form\">"
        "<layout class=\"QVBoxLayout\" name=\"outer\">"
        "<item><widget class=\"QPushButton\" name=\"target\">"
        "<property name=\"text\"><string>t</string></property>"
        "</widget></item>"
        "<item><widget class=\"QWidget\" name=\"bulk\">"
        "<layout class=\"QVBoxLayout\" name=\"inner\">%s</layout>"
        "</widget></item></layout></widget>"
        "<resources/><connections/></ui>" % inner
    )


def _flat(count: int) -> str:
    rows = []
    for index in range(count):
        rows.append(
            "<item><widget class=\"QPushButton\" name=\"b%s\">"
            "<property name=\"text\"><string>x</string></property>"
            "</widget></item>" % index
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<ui version=\"4.0\"><class>Form</class>"
        "<widget class=\"QWidget\" name=\"Form\">"
        "<layout class=\"QVBoxLayout\" name=\"verticalLayout\">%s</layout>"
        "</widget><resources/><connections/></ui>" % "".join(rows)
    )


def _touched_insert(count: int) -> int:
    log = open_log(_bulk(count))
    layout = log.document.root.layout
    assert layout is not None
    log.execute(
        InsertFragment(
            InBoxLayout(layout.id, 0),
            Fragment(nodes=(button_spec("extra"),)),
            auto_layout=False,
        )
    )
    return mutate.last_touched


def _touched_move(count: int) -> int:
    log = open_log(_bulk(count))
    layout = log.document.root.layout
    assert layout is not None
    log.execute(MoveNodes((nid(log.document, "target"),), InBoxLayout(layout.id, len(layout.items))))
    return mutate.last_touched


def test_insert_and_move_do_not_walk_the_untouched_subtree() -> None:
    assert _touched_insert(8) == _touched_insert(200)
    assert _touched_move(8) == _touched_move(200)
    log = open_log(_bulk(200))
    log.execute(SetProperty(nid(log.document, "target"), "text", StringValue("z")))
    assert mutate.last_touched < 30


def test_naming_a_new_widget_does_not_walk_every_name(monkeypatch: pytest.MonkeyPatch) -> None:
    log = open_log(BOX)
    doc = log.document
    consumed = {"n": 0}
    real = UiDocument.names

    class _Watch:
        def __init__(self, inner: frozenset) -> None:
            self._inner = inner

        def __contains__(self, item: object) -> bool:
            return item in self._inner

        def __iter__(self) -> object:
            consumed["n"] += 1
            return iter(self._inner)

    def names(self: UiDocument) -> _Watch:
        return _Watch(real(self))

    monkeypatch.setattr(UiDocument, "names", names)
    layout = doc.root.layout
    assert layout is not None
    log.execute(
        InsertFragment(
            InBoxLayout(layout.id, 0),
            Fragment(nodes=(button_spec("extra"),)),
            auto_layout=False,
        )
    )
    log.execute(Wrap((nid(doc, "okButton"),), "QFrame", "QVBoxLayout"))
    assert consumed["n"] == 0
    assert "extra" in doc.names()


def test_structural_edits_rebuild_custom_widgets_only_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = open_log(BOX)
    doc = log.document
    calls = {"n": 0}
    real = UiDocument._rebuild_custom_index

    def wrapped(self: UiDocument) -> None:
        calls["n"] += 1
        real(self)

    monkeypatch.setattr(UiDocument, "_rebuild_custom_index", wrapped)
    layout = doc.root.layout
    assert layout is not None
    button = nid(doc, "okButton")
    log.execute(
        InsertFragment(
            InBoxLayout(layout.id, 0),
            Fragment(nodes=(button_spec("extra"),)),
            auto_layout=False,
        )
    )
    log.execute(MoveNodes((button,), InBoxLayout(layout.id, len(layout.items))))
    log.execute(DeleteNodes((nid(doc, "extra"),)))
    assert calls["n"] == 0


@pytest.mark.perf
@pytest.mark.timeout(120)
def test_one_thousand_property_edits_average_under_a_millisecond() -> None:
    log = open_log(_flat(1000))
    owner = nid(log.document, "b0")
    previous = os.environ.get("CBCS_FB_VALIDATE")
    os.environ["CBCS_FB_VALIDATE"] = "0"
    try:
        started = time.process_time()
        for index in range(1000):
            log.execute(SetProperty(owner, "text", StringValue("v%s" % (index % 7))))
        elapsed = time.process_time() - started
    finally:
        if previous is None:
            os.environ.pop("CBCS_FB_VALIDATE", None)
        else:
            os.environ["CBCS_FB_VALIDATE"] = previous
    average = elapsed / 1000.0
    assert average < 0.001, "average %.6f s" % average
