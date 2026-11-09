"""Edit cost stays on the nodes that changed (CONTRACTS.md section 12)."""

from __future__ import annotations

import os
import time
from typing import Callable, List, Tuple

import pytest

from app.features.form_builder.engine.commands.catalog import DeleteNodes, InsertFragment, MoveNodes, SetProperty, Wrap
from app.features.form_builder.engine.commands.placement import InBoxLayout
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.values import StringValue
from tests.form_builder.engine.commands._support import BOX, button_spec, nid, open_log
from tests.form_builder.perf.stats import (
    CPU_TOLERANCE,
    Distribution,
    cpu_within_budget,
    measure,
    sample_until_budget,
)

# Section 12's 3 ms command budget at 1000 widgets. One cold sample has no margin.
_REORDER_BUDGET_MS = 3.0
_REORDER_WARMUP = 2
_REORDER_SAMPLES = 5


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


def _cost_move_container(count: int, monkeypatch: pytest.MonkeyPatch) -> Tuple[int, int]:
    log = open_log(_bulk(count))
    layout = log.document.root.layout
    assert layout is not None
    walked = {"n": 0}
    real = mutate._walk

    def counted(node: object) -> object:
        found = real(node)  # type: ignore[arg-type]
        walked["n"] += len(found)
        return found

    with monkeypatch.context() as patch:
        patch.setattr(mutate, "_walk", counted)
        log.execute(MoveNodes((nid(log.document, "bulk"),), InBoxLayout(layout.id, 0)))
    return walked["n"], mutate.last_touched


def test_insert_and_move_do_not_walk_the_untouched_subtree(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _touched_insert(8) == _touched_insert(200)
    assert _touched_move(8) == _touched_move(200)
    assert _cost_move_container(8, monkeypatch) == _cost_move_container(200, monkeypatch)
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
def test_reordering_a_thousand_siblings_is_one_move() -> None:
    log = open_log(_flat(1000))
    doc = log.document
    layout = doc.root.layout
    assert layout is not None
    one, five, fifteen = os.getloadavg()
    previous = os.environ.get("CBCS_FB_VALIDATE")
    os.environ["CBCS_FB_VALIDATE"] = "0"
    load = "loadavg %.2f/%.2f/%.2f" % (one, five, fifteen)
    try:
        first = nid(doc, "b0")
        last = nid(doc, "b999")
        _assert_reorder_cpu(
            "move to end",
            lambda: log.execute(MoveNodes((first,), InBoxLayout(layout.id, 1000))),
            log,
            load,
        )
        _assert_reorder_cpu(
            "move to start",
            lambda: log.execute(MoveNodes((last,), InBoxLayout(layout.id, 0))),
            log,
            load,
        )
        _assert_reorder_cpu(
            "insert",
            lambda: log.execute(
                InsertFragment(
                    InBoxLayout(layout.id, 500),
                    Fragment(nodes=(button_spec("mid"),)),
                    auto_layout=False,
                )
            ),
            log,
            load,
        )
        log.execute(MoveNodes((first,), InBoxLayout(layout.id, 1000)))
        log.execute(MoveNodes((last,), InBoxLayout(layout.id, 0)))
        outcome = log.execute(
            InsertFragment(
                InBoxLayout(layout.id, 500),
                Fragment(nodes=(button_spec("mid"),)),
                auto_layout=False,
            )
        )
    finally:
        if previous is None:
            os.environ.pop("CBCS_FB_VALIDATE", None)
        else:
            os.environ["CBCS_FB_VALIDATE"] = previous
    assert outcome.noop is False
    assert len(log.entries()[-1].ops) == 1
    names = []
    current = doc.root.layout
    assert current is not None
    for item in current.items:
        content = item.content
        assert isinstance(content, WidgetNode)
        names.append(content.object_name)
    assert names[0] == "b999"
    assert names[-1] == "b0"
    assert names[500] == "mid"


def _assert_reorder_cpu(label: str, command: Callable[[], object], log: CommandLog, load: str) -> None:
    """CPU p95 of one structural command, with the harness tolerance and one retry."""
    seen: List[object] = []

    def timed() -> None:
        seen.append(command())

    def cleanup() -> None:
        outcome = seen[-1]
        assert getattr(outcome, "noop") is False, "%s was a no-op" % label
        ops = len(log.entries()[-1].ops)
        assert ops == 1, "%s produced %d ops" % (label, ops)
        log.undo()

    def once() -> Distribution:
        return measure(
            timed,
            warmup=_REORDER_WARMUP,
            samples=_REORDER_SAMPLES,
            cleanup=cleanup,
        )

    attempt = sample_until_budget(once, _REORDER_BUDGET_MS)
    p95_ms = attempt.distribution.cpu_p95 * 1000.0
    detail = "%s cpu p95 %.3f ms budget %.0f ms tolerance %.2f tries %d %s" % (
        label,
        p95_ms,
        _REORDER_BUDGET_MS,
        CPU_TOLERANCE,
        attempt.tries,
        load,
    )
    print(detail)
    assert cpu_within_budget(p95_ms, _REORDER_BUDGET_MS), detail


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


def test_paste_into_a_long_form_bubbles_each_ancestor_once() -> None:
    log = open_log(_form_rows(390))
    doc = log.document
    layout = doc.by_name("form")[0]
    form = doc.by_name("Form")[0]
    before = doc.fingerprint()
    mutate.trace_ids = []
    try:
        log.execute(InsertFragment(InBoxLayout(layout, 0), Fragment(nodes=(button_spec("extra"),))))
        traced = list(mutate.trace_ids or [])
    finally:
        mutate.trace_ids = None
    assert traced.count(int(layout)) <= 8
    assert traced.count(int(form)) <= 8
    assert log.undo()
    assert doc.fingerprint() == before


def _form_rows(rows: int) -> str:
    items = []
    for index in range(rows):
        items.append(
            '<item row="%d" column="0"><widget class="QLabel" name="l%d">'
            '<property name="text"><string>L</string></property></widget></item>'
            '<item row="%d" column="1"><widget class="QLineEdit" name="e%d"/></item>'
            % (index, index, index, index)
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ui version="4.0"><class>Form</class>'
        '<widget class="QWidget" name="Form">'
        '<layout class="QFormLayout" name="form">%s</layout>'
        "</widget></ui>" % "".join(items)
    )
