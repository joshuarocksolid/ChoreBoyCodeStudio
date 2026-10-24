"""Seeded command sequences for the command log (CONTRACTS.md section 13).

``FB_SEED`` selects one seed. The fast lane calls ``run_sequence`` on a small
grid. The gate calls ``run_many`` for the 5,000 by 50 evidence run.
"""

from __future__ import annotations

import logging
import os
import random
from typing import Any, Dict, List, Optional, Tuple, cast

from app.features.form_builder.engine.commands.base import Command, CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.drop import (
    AdoptIntoBox,
    InsertFormRow,
    SwapFormRows,
    WrapWithNew,
)
from app.features.form_builder.engine.commands.catalog import (
    AddConnection,
    AdjustSize,
    ApplyLayout,
    BreakLayout,
    CreateAction,
    DeleteNodes,
    InsertFragment,
    MorphLayout,
    MorphWidget,
    MoveNodes,
    MovePage,
    Rename,
    ReplaceDocument,
    SetBuddy,
    SetGeometry,
    SetLayoutCell,
    SetLayoutStretch,
    SetLogic,
    SetProperty,
    SetPropertyMany,
    SetTabStops,
    SetZOrder,
    SimplifyGrid,
    Unwrap,
    Wrap,
)
from app.features.form_builder.engine.commands.log import replay
from app.features.form_builder.engine.commands.placement import (
    InBoxLayout,
    InContainer,
    InFormRow,
    InGridCell,
)
from app.features.form_builder.engine.events import (
    ChangeSet,
    DocumentReplaced,
    FieldChanged,
    NodeInserted,
    NodeRemoved,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import form_rows, is_page_container
from app.features.form_builder.engine.ui4 import mutate
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import LayoutNode, WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.engine.ui4.values import RectValue, SizeValue, StringValue
from tests.form_builder.engine.commands._support import (
    BOX,
    FREE,
    GRID,
    SHARED,
    STACK,
    button_spec,
    saved,
)
from tests.form_builder.engine.commands.test_events import ShadowTree

_LOG = logging.getLogger("app.features.form_builder")

NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="grid">
   <item row="0" column="0"><widget class="QLabel" name="l1"><property name="text"><string>a</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="e1"/></item>
   <item row="1" column="0" colspan="2">
    <layout class="QHBoxLayout" name="h">
     <item><widget class="QPushButton" name="p1"/></item>
     <item><spacer name="sp"><property name="orientation"><enum>Qt::Horizontal</enum></property></spacer></item>
     <item><widget class="QPushButton" name="p2"/></item>
    </layout>
   </item>
   <item row="2" column="0" colspan="2">
    <widget class="QGroupBox" name="g">
     <layout class="QFormLayout" name="f">
      <item row="0" column="0"><widget class="QLabel" name="fl"><property name="buddy"><cstring>fe</cstring></property></widget></item>
      <item row="0" column="1"><widget class="QLineEdit" name="fe"/></item>
     </layout>
    </widget>
   </item>
   <item row="3" column="0" colspan="2">
    <widget class="QTabWidget" name="tabs">
     <widget class="QWidget" name="t1"><attribute name="title"><string>One</string></attribute></widget>
     <widget class="QWidget" name="t2"/>
    </widget>
   </item>
  </layout>
 </widget>
 <tabstops><tabstop>e1</tabstop><tabstop>fe</tabstop></tabstops>
 <resources/>
 <connections>
  <connection><sender>p1</sender><signal>clicked()</signal><receiver>e1</receiver><slot>clear()</slot></connection>
 </connections>
</ui>
"""

FORM_ROWS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QGridLayout" name="outer">
   <item row="0" column="0"><widget class="QLabel" name="g0"/></item>
   <item row="0" column="1"><widget class="QLineEdit" name="g1"/></item>
   <item row="0" column="2"><widget class="QPushButton" name="g2"/></item>
   <item row="1" column="0" colspan="3">
    <widget class="QGroupBox" name="box">
     <layout class="QFormLayout" name="form">
      <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="buddy"><cstring>nameEdit</cstring></property></widget></item>
      <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
      <item row="1" column="0" colspan="2"><widget class="QCheckBox" name="wideCheck"/></item>
      <item row="3" column="0"><widget class="QLabel" name="countLabel"/></item>
      <item row="3" column="1">
       <layout class="QHBoxLayout" name="countRow">
        <item><widget class="QSpinBox" name="countSpin"/></item>
        <item><widget class="QPushButton" name="countButton"/></item>
       </layout>
      </item>
     </layout>
    </widget>
   </item>
   <item row="2" column="0" colspan="3">
    <widget class="QFrame" name="bare">
     <widget class="QPushButton" name="loose">
      <property name="geometry"><rect><x>0</x><y>0</y><width>80</width><height>24</height></rect></property>
     </widget>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

FORMS = (BOX, GRID, FREE, STACK, SHARED, NESTED, FORM_ROWS)

_FORM_ROLES = ("label", "field", "spanning")


class _Boom(Exception):
    pass


class _FailAfter:
    """Runs one command, then refuses, so the transaction rolls back mid-way."""

    command_type = "fail_after"
    label = "Fail"
    merge_token = None

    def __init__(self, inner: object) -> None:
        self.inner = inner

    def merge_key(self) -> None:
        return None

    def apply(self, doc: UiDocument, ctx: Any) -> None:
        del doc
        ctx.run(self.inner)
        raise _Boom("mid-way")


def command_for(doc: UiDocument, rng: random.Random, step: int) -> Optional[Any]:
    """One command that is legal often enough to make progress. None skips."""
    widgets = [node for node in doc.iter_preorder() if isinstance(node, WidgetNode) and node.id != doc.root.id]
    layouts = [node for node in doc.iter_preorder() if isinstance(node, LayoutNode)]
    items = [node for node in doc.iter_preorder() if node.kind == "layoutitem"]
    widget = rng.choice(widgets) if widgets else None
    layout = rng.choice(layouts) if layouts else None
    names = [item.object_name for item in widgets if item.object_name]
    forms = [item for item in layouts if item.class_name == "QFormLayout"]
    roll = rng.randrange(40)
    if roll == 0 and widget is not None:
        value = None if rng.randrange(5) == 0 else StringValue("t%d" % step)
        return SetProperty(widget.id, "text", value, merge_token=rng.choice([None, "tok"]))
    if roll == 1 and widget is not None:
        picked = rng.choice(names) if names else "x"
        return Rename(widget.id, rng.choice(["n%d" % step, picked, "same", "n%d" % (step - 1)]))
    if roll == 2 and widget is not None and layout is not None:
        return MoveNodes((widget.id,), InBoxLayout(layout.id, rng.randrange(len(layout.items) + 1)))
    if roll == 3 and layout is not None:
        frag = Fragment(
            nodes=(
                button_spec(rng.choice(["p1", "okButton", "same", "a", "zz"])),
                button_spec(rng.choice(["p1", "b", "zz"])),
            ),
            connections=(
                NodeSpec(
                    "connection",
                    None,
                    (("sender", "p1"), ("signal", "clicked()"), ("receiver", "zz"), ("slot", "clear()")),
                ),
            ),
        )
        return InsertFragment(InBoxLayout(layout.id, 0), frag)
    if roll == 4 and widget is not None:
        chosen = rng.sample(widgets, min(len(widgets), rng.randrange(1, 3)))
        return DeleteNodes(tuple(item.id for item in chosen))
    if roll == 5 and len(names) >= 2:
        return AddConnection(names[0], "clicked", names[-1], "clear")
    if roll == 6 and layout is not None:
        return SetLayoutStretch(layout.id, "stretch", rng.choice(["1,0", None, "0,1"]))
    if roll == 7 and widget is not None and widgets:
        siblings = [item for item in widgets if item.parent_id == widget.parent_id]
        chosen = rng.sample(siblings, min(len(siblings), rng.randrange(1, 3))) if siblings else []
        if chosen:
            return Wrap(
                tuple(item.id for item in chosen),
                rng.choice([None, "QWidget", "QFrame"]),
                rng.choice(["QVBoxLayout", "QGridLayout"]),
            )
    if roll == 8 and widget is not None:
        return Unwrap(widget.id)
    if roll == 9 and layout is not None:
        return BreakLayout(layout.id, ())
    if roll == 10 and layout is not None:
        return MorphLayout(layout.id, rng.choice(["QVBoxLayout", "QHBoxLayout", "QGridLayout", "QFormLayout"]))
    if roll == 11 and widget is not None:
        return MorphWidget(widget.id, rng.choice(["QLabel", "QPushButton", "QFrame", "QWidget"]))
    if roll == 12 and layout is not None:
        return SimplifyGrid(layout.id)
    if roll == 13 and items:
        item = rng.choice(items)
        return SetLayoutCell(item.id, rng.randrange(4), rng.randrange(3))
    if roll == 14 and widget is not None:
        return SetLogic(widget.id, "cbcsEnabledWhen", rng.choice(["1", None, "x > 2"]))
    if roll == 15:
        return ReplaceDocument(saved(doc))
    if roll == 16 and widget is not None:
        return SetGeometry(
            widget.id,
            RectValue(rng.randrange(9), 0, 10, 10),
            merge_token=rng.choice([None, "drag"]),
        )
    if roll == 17 and widget is not None:
        return AdjustSize(widget.id, SizeValue(rng.randrange(5, 50), 20))
    if roll == 18 and widget is not None:
        containers = [
            item
            for item in widgets
            if item.class_name in ("QWidget", "QGroupBox", "QTabWidget", "QStackedWidget", "QFrame")
        ]
        container = rng.choice(containers) if containers else None
        if container is not None:
            return MoveNodes((widget.id,), InContainer(container.id, rng.randrange(3)))
    if roll == 19 and widget is not None:
        grids = [item for item in layouts if item.class_name == "QGridLayout"]
        grid = rng.choice(grids) if grids else None
        if grid is not None:
            return MoveNodes(
                (widget.id,),
                InGridCell(
                    grid.id,
                    rng.randrange(4),
                    rng.randrange(3),
                    mode=rng.choice(["cell", "insert_row", "insert_column"]),
                ),
            )
    if roll == 20 and isinstance(widget, WidgetNode):
        kids = [child.object_name for child in widget.child_widgets if child.object_name]
        if len(kids) >= 2:
            rng.shuffle(kids)
            return SetZOrder(widget.id, tuple(kids))
    if roll == 21 and widgets:
        labels = [item for item in widgets if item.class_name == "QLabel"]
        if labels:
            return SetBuddy(labels[0].id, rng.choice([None] + names))
    if roll == 22 and widgets:
        return SetPropertyMany(tuple(item.id for item in widgets[:3]), "toolTip", StringValue("tip%d" % (step % 3)))
    if roll == 23:
        if not names:
            return SetTabStops(None)
        return SetTabStops(tuple(rng.sample(names, min(2, len(names)))))
    if roll == 24 and widget is not None and is_page_container(doc, widget.id):
        pages = widget.child_widgets
        if len(pages) >= 2:
            return MovePage(widget.id, 0, len(pages) - 1)
    if roll == 25:
        return CreateAction(NodeSpec("action", None, (("name", "act%d" % (step % 7)),)))
    if roll == 26 and widget is not None:
        return SetProperty(widget.id, "text", None, merge_token="tok")
    if roll == 27 and widget is not None and forms:
        row = InFormRow(rng.choice(forms).id, rng.randrange(5), rng.choice(_FORM_ROLES), rng.randrange(2) == 0)
        return MoveNodes((widget.id,), row)
    if roll == 28 and forms:
        row = InFormRow(rng.choice(forms).id, rng.randrange(5), rng.choice(_FORM_ROLES), rng.randrange(2) == 0)
        buttons = tuple(button_spec("formButton") for _ in range(rng.randrange(1, 3)))
        return InsertFragment(row, Fragment(nodes=buttons))
    if roll == 29 and forms:
        form = rng.choice(forms)
        at = InBoxLayout(form.id, rng.randrange(len(form.items) + 1))
        if widget is not None and rng.randrange(2) == 0:
            return MoveNodes((widget.id,), at)
        return InsertFragment(at, Fragment(nodes=(button_spec("formButton"),)))
    if roll == 30 and widget is not None:
        siblings = [item for item in widgets if _sibling_key(doc, item) == _sibling_key(doc, widget)]
        chosen = rng.sample(siblings, min(len(siblings), rng.randrange(1, 4)))
        return Wrap(
            tuple(item.id for item in chosen),
            rng.choice([None, "QWidget"]),
            rng.choice(["QFormLayout", "QVBoxLayout"]),
        )
    if roll == 31:
        others = [item for item in layouts if item.class_name != "QFormLayout"]
        if others:
            return MorphLayout(rng.choice(others).id, "QFormLayout")
    if roll == 32 and forms:
        form = rng.choice(forms)
        if form.items:
            return SetLayoutCell(
                rng.choice(form.items).id,
                rng.randrange(5),
                rng.randrange(2),
                None,
                rng.choice([None, 2]),
            )
    if roll == 33:
        nested = [item for item in layouts if item.parent_slot == "content"]
        holders = [item for item in widgets if item.layout is not None]
        targets = nested + holders
        if targets:
            return Unwrap(rng.choice(targets).id)
    if roll == 34 and forms:
        cell = InGridCell(rng.choice(forms).id, rng.randrange(3), rng.randrange(2))
        return InsertFragment(cell, Fragment(nodes=(button_spec("cellButton"),)))
    if roll == 35:
        bare = [
            item
            for item in [doc.root] + widgets
            if item.class_name in ("QWidget", "QFrame", "QGroupBox") and item.layout is None and item.child_widgets
        ]
        if bare:
            return ApplyLayout(rng.choice(bare).id, "QFormLayout")
    if roll == 36 and forms:
        form = rng.choice(forms)
        row = rng.randrange(max(len(form.items), 1))
        if widget is not None and rng.randrange(2) == 0:
            return InsertFormRow(form.id, row, existing=widget.id)
        return InsertFormRow(form.id, row, fragment=Fragment(nodes=(button_spec("fieldButton"),)))
    if roll == 37 and widget is not None:
        boxes = [item for item in layouts if item.class_name in ("QVBoxLayout", "QHBoxLayout") and item.items]
        if boxes:
            box = rng.choice(boxes)
            content = rng.choice(box.items).content
            if content is not None and content.id != widget.id:
                return WrapWithNew(
                    content.id,
                    rng.choice(["before", "after"]),
                    rng.choice(["QHBoxLayout", "QVBoxLayout"]),
                    existing=widget.id,
                )
    if roll == 38:
        bare = [
            item
            for item in [doc.root] + widgets
            if isinstance(item, WidgetNode)
            and item.layout is None
            and item.class_name in ("QWidget", "QFrame", "QGroupBox")
            and not is_page_container(doc, item.id)
        ]
        if bare:
            return AdoptIntoBox(rng.choice(bare).id, fragment=Fragment(nodes=(button_spec("adopted"),)))
    if roll == 39 and forms:
        form = rng.choice(forms)
        rows = form_rows(doc, form.id)
        if len(rows) >= 2:
            return SwapFormRows(form.id, rng.randrange(len(rows) - 1), 1)
    return None


def _sibling_key(doc: UiDocument, widget: WidgetNode) -> Optional[NodeId]:
    parent = doc.parent(widget.id)
    if parent is not None and parent.kind == "layoutitem":
        return parent.parent_id
    return widget.parent_id



def _fail_on_validation(seed: object, exc: CommandRejected) -> None:
    """FB999 is a broken invariant or a crash inside apply, not a refusal.

    The one expected FB999 is the generator's own injected ``_Boom``.
    """
    if exc.code == "FB999" and not isinstance(exc.error, _Boom):
        raise AssertionError("seed %s entry failed validation: %s" % (seed, exc.error or exc))

def run_sequence(seed: int, steps: int, *, text: Optional[str] = None) -> None:
    """One sequence. Failures name the seed."""
    from tests.form_builder.engine.commands._support import open_log

    rng = random.Random(seed)
    source = text if text is not None else FORMS[seed % len(FORMS)]
    log = open_log(source)
    doc = log.document
    original_text = saved(doc)
    original_fp = doc.fingerprint()
    shadow = ShadowTree(doc)
    fields: Dict[NodeId, Tuple[Tuple[str, object], ...]] = {
        node.id: tuple(sorted(node.fields, key=lambda item: item[0])) for node in doc.iter_preorder()
    }
    seen: List[object] = []
    failures: List[str] = []

    def listener(change_set: ChangeSet) -> None:
        seen.append(change_set)
        shadow.apply(change_set)
        for change in change_set.changes:
            if isinstance(change, FieldChanged):
                current = dict(fields.get(change.node, ()))
                if current.get(change.field) != change.old:
                    raise AssertionError("FieldChanged.old wrong seed %s %s" % (seed, change))
                if change.new is None:
                    current.pop(change.field, None)
                else:
                    current[change.field] = change.new
                fields[change.node] = tuple(sorted(current.items(), key=lambda item: item[0]))
            elif isinstance(change, NodeInserted) and change.spec is not None:
                _remember_spec(fields, change.spec)
            elif isinstance(change, DocumentReplaced):
                fields.clear()
                _remember_spec(fields, change.spec)
            elif isinstance(change, NodeRemoved):
                for node_id in change.subtree:
                    fields.pop(node_id, None)
        live = {
            node.id: tuple(sorted(node.fields, key=lambda item: item[0]))
            for node in doc.iter_preorder()
        }
        if live != fields:
            raise AssertionError("field mirror mismatch seed %s" % (seed,))
        if not shadow.matches(doc):
            raise AssertionError("shadow mismatch seed %s" % (seed,))

    def guarded(change_set: ChangeSet) -> None:
        try:
            listener(change_set)
        except AssertionError as exc:
            failures.append(str(exc))

    log.subscribe(guarded, priority=1)
    done = 0
    for attempt in range(steps * 4):
        if done >= steps:
            break
        roll = rng.randrange(20)
        if roll < 3 and log.can_undo():
            log.undo()
            doc.validate()
            done += 1
            continue
        if roll == 3 and log.can_redo():
            log.redo()
            doc.validate()
            done += 1
            continue
        before_spec = doc.to_spec()
        before_fp = doc.fingerprint()
        event_count = len(seen)
        entry_count = len(log.entries())
        command: Optional[Any] = None
        try:
            if roll in (4, 5):
                commands = [command_for(doc, rng, seed * 1000 + attempt) for _ in range(3)]
                commands = [item for item in commands if item is not None]
                try:
                    with log.transaction("T") as tx:
                        for item in commands:
                            try:
                                tx.execute(cast(Command, item))
                            except CommandRejected as exc:
                                _fail_on_validation(seed, exc)
                        if roll == 5 and commands:
                            tx.execute(cast(Command, _FailAfter(commands[0])))
                except CommandRejected as exc:
                    _fail_on_validation(seed, exc)
                    if doc.fingerprint() != before_fp or len(seen) != event_count:
                        raise AssertionError("transaction rollback diverged seed %s" % (seed,))
                    continue
                if len(log.entries()) > entry_count and log.entries()[-1].label == "T":
                    entry = log.entries()[-1]
                    _inverses_match(before_spec, entry.ops, entry.inverse_ops, doc, seed)
                done += 1
                continue
            command = command_for(doc, rng, seed * 1000 + attempt)
            if command is None:
                continue
            outcome = log.execute(cast(Command, command), continue_gesture=rng.randrange(8) == 0)
        except CommandRejected as exc:
            _fail_on_validation(seed, exc)
            if doc.fingerprint() != before_fp or len(seen) != event_count:
                raise AssertionError("rejected command changed the form seed %s" % (seed,))
            continue
        if outcome.noop:
            if len(seen) != event_count:
                raise AssertionError("noop emitted seed %s" % (seed,))
            continue
        if log.entries() and not outcome.merged and len(log.entries()) > entry_count:
            entry = log.entries()[-1]
            _inverses_match(before_spec, entry.ops, entry.inverse_ops, doc, seed)
        done += 1
    if failures:
        raise AssertionError("seed %s %s" % (seed, failures[0]))
    if done < steps:
        raise AssertionError("seed %s stopped after %s steps" % (seed, done))
    replayed = replay(source, log.entries())
    if replayed.fingerprint() != doc.fingerprint():
        raise AssertionError("replay mismatch seed %s" % (seed,))
    while log.redo():
        doc.validate()
    tip = doc.fingerprint()
    while log.undo():
        doc.validate()
    doc.validate()
    if saved(doc) != original_text or doc.fingerprint() != original_fp:
        raise AssertionError("undo-all mismatch seed %s" % (seed,))
    while log.redo():
        doc.validate()
    doc.validate()
    if doc.fingerprint() != tip:
        raise AssertionError("redo-all mismatch seed %s" % (seed,))


def run_many(count: int, steps: int, *, start: int = 0) -> str:
    """Run ``count`` seeds. The summary is the gate evidence line."""
    chosen = os.environ.get("FB_SEED")
    seeds = [int(chosen)] if chosen else list(range(start, start + count))
    level = _LOG.level
    _LOG.setLevel(logging.CRITICAL)
    failed = 0
    try:
        for seed in seeds:
            try:
                run_sequence(seed, steps)
            except Exception as exc:
                failed += 1
                raise AssertionError("FB_SEED=%s steps=%s %s" % (seed, steps, exc)) from exc
    finally:
        _LOG.setLevel(level)
    return "FB_SEED %s sequences %s steps %s failed %s" % (
        chosen or ("%s..%s" % (start, start + count - 1)),
        len(seeds),
        steps,
        failed,
    )


def _remember_spec(fields: Dict[NodeId, Tuple[Tuple[str, object], ...]], spec: NodeSpec) -> None:
    if spec.id is None:
        return
    fields[spec.id] = tuple(sorted(spec.fields, key=lambda item: item[0]))
    for _name, kids in spec.slots:
        for kid in kids:
            _remember_spec(fields, kid)


def _inverses_match(
    before: NodeSpec,
    ops: Tuple[Any, ...],
    inverses: Tuple[Any, ...],
    live: UiDocument,
    seed: int,
) -> None:
    clone = UiDocument.from_spec(before)
    for op, recorded in zip(ops, inverses):
        fingerprint = clone.fingerprint()
        inverse = mutate.apply(clone, op)
        if inverse != recorded:
            raise AssertionError("inverse mismatch seed %s" % (seed,))
        mutate.apply(clone, inverse)
        if clone.fingerprint() != fingerprint:
            raise AssertionError("inverse is not exact seed %s" % (seed,))
        mutate.apply(clone, op)
    if clone.fingerprint() != live.fingerprint():
        raise AssertionError("clone diverged seed %s" % (seed,))
