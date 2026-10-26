"""Layout commands: one table of kinds, one request per gesture, one planner per request.

``offers`` is a dry run of the planners. ``carry_out`` runs one planner and
executes its commands as one undo step. Callers pass a request; they never
build ``Wrap`` or ``MorphLayout`` themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    get_args,
)

from app.features.form_builder.engine.commands import catalog
from app.features.form_builder.engine.commands.base import Command, CommandRejected
from app.features.form_builder.engine.commands.catalog_ext.host_wrap import WrapFree, WrapSplitter, WrapTab
from app.features.form_builder.engine.commands.catalog_ext.sizing import ApplySizing, from_write
from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.tree import (
    is_container,
    is_page_container,
    visual_children,
)
from app.features.form_builder.engine.sizing import (
    WORD_HUG,
    encode_axis,
    share_slots,
    splice_stretch,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    LayoutItemNode,
    LayoutNode,
    Node,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.values import (
    EnumValue,
    RectValue,
    SizePolicyValue,
    SizeValue,
)

VERTICAL = "vertical"
HORIZONTAL = "horizontal"
GRID = "grid"
FORM = "form"
HSPLIT = "hsplit"
VSPLIT = "vsplit"
GROUP = "group"
FRAME = "frame"
TAB = "tab"

_BOXES = ("QVBoxLayout", "QHBoxLayout")


@dataclass(frozen=True)
class LayoutShape:
    layout_class: str


@dataclass(frozen=True)
class SplitterShape:
    orientation: str


@dataclass(frozen=True)
class ContainerShape:
    container_class: str


@dataclass(frozen=True)
class TabShape:
    title: str


Shape = Union[LayoutShape, SplitterShape, ContainerShape, TabShape]


@dataclass(frozen=True)
class Kind:
    label: str
    noun: str
    shape: Shape


KINDS: Mapping[str, Kind] = {
    VERTICAL: Kind("Vertical", "a vertical layout", LayoutShape("QVBoxLayout")),
    HORIZONTAL: Kind("Horizontal", "a horizontal layout", LayoutShape("QHBoxLayout")),
    GRID: Kind("Grid", "a grid", LayoutShape("QGridLayout")),
    FORM: Kind("Form", "a form layout", LayoutShape("QFormLayout")),
    HSPLIT: Kind("Horizontal splitter", "a horizontal splitter", SplitterShape("Qt::Horizontal")),
    VSPLIT: Kind("Vertical splitter", "a vertical splitter", SplitterShape("Qt::Vertical")),
    GROUP: Kind("Group box", "a group box", ContainerShape("QGroupBox")),
    FRAME: Kind("Frame", "a frame", ContainerShape("QFrame")),
    TAB: Kind("Tab widget", "a tab widget", TabShape("Tab 1")),
}

KEYBOARD: Tuple[str, ...] = (HORIZONTAL, VERTICAL, HSPLIT, VSPLIT, GRID, FORM)
POPOVER: Tuple[str, ...] = (VERTICAL, HORIZONTAL, GRID, FORM, HSPLIT, VSPLIT, GROUP, FRAME, TAB)
SEGMENTS: Tuple[str, ...] = (VERTICAL, HORIZONTAL, GRID, FORM)

_KIND_OF_LAYOUT = {
    kind.shape.layout_class: kind_id
    for kind_id, kind in KINDS.items()
    if isinstance(kind.shape, LayoutShape)
}

LOCK_MINIMUM = "minimum"
LOCK_MAXIMUM = "maximum"
LOCK_BOTH = "both"
LOCKS: Tuple[Tuple[str, str], ...] = (
    (LOCK_MINIMUM, "Set minimum to current size"),
    (LOCK_MAXIMUM, "Set maximum to current size"),
    (LOCK_BOTH, "Fix at current size"),
)


@dataclass(frozen=True)
class MorphTarget:
    class_name: str
    phrase: str

    @property
    def label(self) -> str:
        bare = self.phrase.split(" ", 1)[1]
        return bare[:1].upper() + bare[1:]


# A widget only changes class inside its family, so the new class can hold
# what the old one held: pages stay pages, item views keep no item lists.
FAMILIES: Tuple[Tuple[MorphTarget, ...], ...] = (
    (
        MorphTarget("QLineEdit", "a line edit"),
        MorphTarget("QTextEdit", "a text box"),
        MorphTarget("QPlainTextEdit", "a plain text box"),
        MorphTarget("QTextBrowser", "a text browser"),
    ),
    (
        MorphTarget("QPushButton", "a push button"),
        MorphTarget("QToolButton", "a tool button"),
        MorphTarget("QCheckBox", "a check box"),
        MorphTarget("QRadioButton", "a radio button"),
        MorphTarget("QCommandLinkButton", "a command link"),
    ),
    (
        MorphTarget("QSpinBox", "a spin box"),
        MorphTarget("QDoubleSpinBox", "a decimal spin box"),
        MorphTarget("QDateEdit", "a date edit"),
        MorphTarget("QTimeEdit", "a time edit"),
        MorphTarget("QDateTimeEdit", "a date and time edit"),
    ),
    (
        MorphTarget("QSlider", "a slider"),
        MorphTarget("QDial", "a dial"),
        MorphTarget("QScrollBar", "a scroll bar"),
    ),
    (
        MorphTarget("QWidget", "a plain widget"),
        MorphTarget("QFrame", "a frame"),
        MorphTarget("QGroupBox", "a group box"),
    ),
    (
        MorphTarget("QTabWidget", "a tab widget"),
        MorphTarget("QStackedWidget", "a stacked widget"),
        MorphTarget("QToolBox", "a toolbox"),
    ),
    (
        MorphTarget("QListView", "a list view"),
        MorphTarget("QTreeView", "a tree view"),
        MorphTarget("QTableView", "a table view"),
        MorphTarget("QColumnView", "a column view"),
    ),
)

_FAMILY_OF: Dict[str, Tuple[MorphTarget, ...]] = {
    target.class_name: family for family in FAMILIES for target in family
}

MIXED_PARENT = "Select widgets in the same layout to wrap them."
_GONE = "That widget is no longer in the form."
_ROOT_WRAP = "The form can't be wrapped."
_DOES_NOT_APPLY = "That doesn't apply to this selection."
_NOTHING_TO_CHANGE = "Nothing to change."


@dataclass(frozen=True)
class ApplyKind:
    kind_id: str


@dataclass(frozen=True)
class PickWrap:
    kind_id: str


@dataclass(frozen=True)
class InspectedKind:
    kind_id: str


@dataclass(frozen=True)
class Unwrap:
    pass


@dataclass(frozen=True)
class RemoveLayout:
    pass


@dataclass(frozen=True)
class Simplify:
    pass


@dataclass(frozen=True)
class Adjust:
    pass


@dataclass(frozen=True)
class KeepContent:
    pass


@dataclass(frozen=True)
class LockSize:
    which: str


@dataclass(frozen=True)
class ChangeTo:
    class_name: str


Request = Union[
    ApplyKind,
    PickWrap,
    InspectedKind,
    Unwrap,
    RemoveLayout,
    Simplify,
    Adjust,
    KeepContent,
    LockSize,
    ChangeTo,
]


@dataclass(frozen=True)
class OpenWrap:
    """Ctrl+Shift+G. Opens the wrap popover; the popover sends a ``PickWrap``."""


_REQUESTS: Mapping[str, object] = {
    "form.action.layoutHorizontal": ApplyKind(HORIZONTAL),
    "form.action.layoutVertical": ApplyKind(VERTICAL),
    "form.action.layoutHorizontalSplitter": ApplyKind(HSPLIT),
    "form.action.layoutVerticalSplitter": ApplyKind(VSPLIT),
    "form.action.layoutGrid": ApplyKind(GRID),
    "form.action.layoutForm": ApplyKind(FORM),
    "form.action.wrap": OpenWrap(),
    "form.action.unwrap": Unwrap(),
    "form.action.removeLayout": RemoveLayout(),
    "form.action.adjustSize": Adjust(),
    "form.action.simplifyGrid": Simplify(),
    "form.action.keepAtContentSize": KeepContent(),
}


def request_for(command_id: str) -> Optional[object]:
    """The request a Form command row sends, or None when the row has no gesture."""
    return _REQUESTS.get(command_id)


@dataclass(frozen=True)
class Measure:
    """A live widget's geometry, size hint, and class default size policies."""

    rect: RectValue
    hint: SizeValue
    policies: Tuple[str, str] = ("Preferred", "Preferred")


Measured = Mapping[NodeId, Measure]


def measure_ids(doc: UiDocument, ids: Sequence[NodeId]) -> Tuple[NodeId, ...]:
    """The widgets a planner may read a ``Measure`` for."""
    found: List[NodeId] = []
    targets = [node_id for node_id in ids if doc.contains(node_id)] or [doc.root.id]
    for node_id in targets:
        node = doc.node(node_id)
        if isinstance(node, LayoutNode):
            owner = node.owner_widget_id()
            wanted = ([owner] if owner is not None else []) + list(_contents(node))
        else:
            wanted = [node_id] + list(visual_children(doc, node_id))
        for candidate in wanted:
            if candidate not in found and isinstance(doc.node(candidate), WidgetNode):
                found.append(candidate)
    return tuple(found)


@dataclass(frozen=True)
class Done:
    sentence: str


@dataclass(frozen=True)
class NeedsConfirm:
    text: str
    accept: str
    cancel: str = "Cancel"


@dataclass(frozen=True)
class Refused:
    reason: str


@dataclass(frozen=True)
class Current:
    """The selection already looks like the request. Nothing is written."""


Outcome = Union[Done, NeedsConfirm, Refused, Current]


@dataclass(frozen=True)
class _Ready:
    label: str
    commands: Tuple[Command, ...]
    sentence: str


@dataclass(frozen=True)
class _Confirm:
    text: str
    accept: str
    ready: _Ready


_Plan = Union[_Ready, _Confirm, Refused, Current]


@dataclass(frozen=True)
class Offer:
    enabled: bool
    reason: str = ""


@dataclass(frozen=True)
class OfferSheet:
    offers: Mapping[object, Offer]
    current_kind: Optional[str]
    morphs: Tuple[MorphTarget, ...]


def offers(
    doc: UiDocument, ids: Sequence[NodeId], measured: Measured, only: Optional[Sequence[object]] = None
) -> OfferSheet:
    """Every request the selection could take, or just ``only``, planned and not executed."""
    live = all(doc.contains(node_id) for node_id in ids)
    morphs = _morph_targets(doc, ids) if live else ()
    if only is None:
        requests: List[object] = [ApplyKind(kind_id) for kind_id in KEYBOARD]
        requests += [PickWrap(kind_id) for kind_id in POPOVER]
        requests += [InspectedKind(kind_id) for kind_id in SEGMENTS]
        requests += [Unwrap(), RemoveLayout(), Simplify(), Adjust(), KeepContent()]
        requests += [LockSize(which) for which, _label in LOCKS]
        requests += [ChangeTo(target.class_name) for target in morphs]
    else:
        requests = list(only)
    sheet: Dict[object, Offer] = {}
    for request in requests:
        sheet[request] = _offer(_prepare(doc, ids, request, measured))
    target = _container_target(doc, ids) if live else None
    layout = target[1] if target is not None else None
    current = _KIND_OF_LAYOUT.get(layout.class_name) if layout is not None else None
    return OfferSheet(sheet, current, morphs)


def takes_layout(doc: UiDocument, ids: Sequence[NodeId]) -> bool:
    """True when ``ids`` is one container or one layout, so an ``InspectedKind`` has a subject."""
    return bool(ids) and all(doc.contains(node_id) for node_id in ids) and _container_target(doc, ids) is not None


def gate(sheet: OfferSheet, request: object) -> Offer:
    """Whether a menu row or tile for ``request`` is enabled, and why not."""
    if isinstance(request, OpenWrap):
        tiles = [sheet.offers.get(PickWrap(kind_id)) for kind_id in POPOVER]
        if any(tile is not None and tile.enabled for tile in tiles):
            return Offer(True)
        reasons = {tile.reason for tile in tiles if tile is not None and tile.reason}
        return Offer(False, reasons.pop() if len(reasons) == 1 else "Nothing here can be wrapped.")
    found = sheet.offers.get(request)
    if found is None:
        return Offer(False, _DOES_NOT_APPLY)
    return found


Execute = Callable[[str, Tuple[Command, ...]], Sequence[Any]]


def carry_out(
    doc: UiDocument,
    ids: Sequence[NodeId],
    request: object,
    measured: Measured,
    execute: Execute,
    confirmed: str = "",
) -> Outcome:
    """Plan ``request`` and run it as one step.

    A plan that needs a confirm returns ``NeedsConfirm`` and writes nothing.
    Call again with ``confirmed`` set to the accepted text; when the plan's
    text has changed since, nothing is written.
    """
    plan = _prepare(doc, ids, request, measured)
    if confirmed:
        if not isinstance(plan, _Confirm) or plan.text != confirmed:
            return Refused("The form changed while you were deciding, so nothing was changed.")
        plan = plan.ready
    if isinstance(plan, _Confirm):
        return NeedsConfirm(plan.text, plan.accept)
    if isinstance(plan, (Refused, Current)):
        return plan
    try:
        results = execute(plan.label, plan.commands)
    except CommandRejected as exc:
        return Refused(str(exc))
    dropped: List[str] = []
    for command, result in zip(plan.commands, results):
        if isinstance(command, catalog.MorphWidget) and result:
            dropped.extend(result)
    return Done(toast_for(plan.sentence, tuple(dropped)))


def transact(log: CommandLog) -> Execute:
    """An ``Execute`` that runs the commands in one ``log`` transaction."""

    def run(label: str, commands: Tuple[Command, ...]) -> Tuple[Any, ...]:
        results = []
        with log.transaction(label) as txn:
            for command in commands:
                results.append(txn.execute(command))
        return tuple(results)

    return run


def toast_for(sentence: str, dropped: Sequence[str]) -> str:
    if not dropped:
        return sentence
    noun = "property" if len(dropped) == 1 else "properties"
    return "%s %d %s didn't apply: %s" % (sentence, len(dropped), noun, ", ".join(dropped))


def spans_cleared(doc: UiDocument, layout_id: NodeId, new_class: str) -> int:
    """How many widgets lose a row or column span when the layout changes class."""
    layout = doc.get(layout_id)
    if not isinstance(layout, LayoutNode):
        return 0
    old = layout.class_name
    if old not in ("QGridLayout", "QFormLayout") or old == new_class:
        return 0
    if new_class in _BOXES:
        columns_too = True
    elif old == "QGridLayout" and new_class == "QFormLayout":
        columns_too = False
    else:
        return 0
    count = 0
    for item in layout.items:
        if item.content is None or isinstance(item.content, SpacerNode):
            continue
        if (item.rowspan or 1) > 1 or (columns_too and (item.colspan or 1) > 1):
            count += 1
    return count


def _offer(plan: _Plan) -> Offer:
    if isinstance(plan, Refused):
        return Offer(False, plan.reason)
    if isinstance(plan, Current):
        return Offer(False, _NOTHING_TO_CHANGE)
    return Offer(True)


def _prepare(doc: UiDocument, ids: Sequence[NodeId], request: object, measured: Measured) -> _Plan:
    planner = _PLANNERS.get(type(request))
    if planner is None:
        return Refused(_DOES_NOT_APPLY)
    if any(not doc.contains(node_id) for node_id in ids):
        return Refused(_GONE)
    return planner(doc, tuple(ids), request, measured)


def _plan_apply_kind(doc: UiDocument, ids: Tuple[NodeId, ...], request: ApplyKind, measured: Measured) -> _Plan:
    kind = KINDS.get(request.kind_id)
    if kind is None:
        return Refused(_DOES_NOT_APPLY)
    shape = kind.shape
    target = _container_target(doc, ids)
    widget, layout = target if target is not None else (None, None)
    if isinstance(shape, LayoutShape):
        if layout is not None:
            return _morph(doc, layout, shape.layout_class)
        if widget is not None:
            return _lay_out(doc, widget, kind, measured)
    if isinstance(shape, SplitterShape):
        splitter = _single_widget(doc, ids)
        if splitter is None or splitter.class_name != "QSplitter":
            splitter = _shared_widget_parent(doc, ids)
            if splitter is not None and len(ids) != len(splitter.child_widgets):
                splitter = None
        if splitter is not None and splitter.class_name == "QSplitter":
            return _orient(splitter, shape, kind)
        if widget is not None:
            contents = tuple(
                node_id for node_id in visual_children(doc, widget.id) if isinstance(doc.node(node_id), WidgetNode)
            )
            if not contents:
                return Refused("There is nothing inside to put in a splitter.")
            return _wrap(doc, contents, kind, measured)
    return _wrap(doc, ids, kind, measured)


def _plan_pick_wrap(doc: UiDocument, ids: Tuple[NodeId, ...], request: PickWrap, measured: Measured) -> _Plan:
    kind = KINDS.get(request.kind_id)
    if kind is None:
        return Refused(_DOES_NOT_APPLY)
    return _wrap(doc, ids, kind, measured)


def _plan_inspected_kind(
    doc: UiDocument, ids: Tuple[NodeId, ...], request: InspectedKind, measured: Measured
) -> _Plan:
    kind = KINDS.get(request.kind_id)
    if kind is None or not isinstance(kind.shape, LayoutShape):
        return Refused(_DOES_NOT_APPLY)
    target = _container_target(doc, ids)
    if target is None:
        return Refused("Select one container to change its layout.")
    widget, layout = target
    if layout is not None:
        return _morph(doc, layout, kind.shape.layout_class)
    if widget is None:
        return Refused("Select a container to give it a layout.")
    return _lay_out(doc, widget, kind, measured)


def _plan_unwrap(doc: UiDocument, ids: Tuple[NodeId, ...], request: Unwrap, measured: Measured) -> _Plan:
    del request, measured
    if not ids or doc.root.id in ids:
        return Refused("The form can't be unwrapped.")
    if len(ids) != 1:
        return Refused("Select one container to unwrap it.")
    node = doc.node(ids[0])
    if isinstance(node, LayoutNode):
        owner = node.owner_widget_id()
        if owner is None:
            return _Ready("Unwrap", (catalog.Unwrap(node.id),), "Unwrapped %s" % _name(doc, node))
        if owner == doc.root.id:
            return Refused("The form can't be unwrapped.")
        node = doc.node(owner)
    if not isinstance(node, WidgetNode):
        return Refused("Select a container to unwrap it.")
    if is_page_container(doc, node.id):
        return Refused("This container can't be unwrapped.")
    if node.layout is None:
        return Refused("Only a container with a layout can be unwrapped.")
    if doc.containing_layout_item(node.id) is None:
        return Refused("Only a container that sits in a layout can be unwrapped.")
    return _Ready("Unwrap", (catalog.Unwrap(node.id),), "Unwrapped %s" % _name(doc, node))


def _plan_remove_layout(
    doc: UiDocument, ids: Tuple[NodeId, ...], request: RemoveLayout, measured: Measured
) -> _Plan:
    del request
    target = _container_target(doc, ids)
    widget, layout = target if target is not None else (None, None)
    if layout is None:
        return Refused("Select a container that has a layout.")
    if layout.owner_widget_id() is None or widget is None:
        return _Ready("Remove layout", (catalog.BreakLayout(layout.id),), "Removed the layout")
    contents = [item.content for item in layout.items if item.content is not None]
    if any(isinstance(content, LayoutNode) for content in contents):
        return Refused("Remove the inner layouts first.")
    spacers = tuple(content.id for content in contents if isinstance(content, SpacerNode))
    widgets = [content.id for content in contents if isinstance(content, WidgetNode)]
    geometries = tuple(
        (node_id, measured[node_id].rect) for node_id in widgets if node_id in measured
    )
    commands: Tuple[Command, ...] = (catalog.BreakLayout(layout.id, geometries),)
    if spacers:
        commands = (catalog.DeleteNodes(spacers),) + commands
    ready = _Ready("Remove layout", commands, "Removed the layout")
    if not widgets:
        return ready
    if len(widgets) == 1:
        tail = "Its widget keeps its current position and size, but it won't follow the window any more."
    else:
        tail = (
            "Its %d widgets keep their current position and size, but they won't follow the window any more."
            % len(widgets)
        )
    text = "Remove the layout from %s? %s" % (_name(doc, widget), tail)
    return _Confirm(text, "Remove layout", ready)


def _plan_simplify(doc: UiDocument, ids: Tuple[NodeId, ...], request: Simplify, measured: Measured) -> _Plan:
    del request, measured
    layout = _grid_target(doc, ids)
    if layout is None or layout.class_name != "QGridLayout":
        return Refused("Select a grid layout to simplify it.")
    rows, columns = _grid_gaps(layout)
    if not rows and not columns:
        return Refused("This grid has no empty rows or columns.")
    commands: List[Command] = [catalog.SimplifyGrid(layout.id)]
    for field, gaps in (
        ("rowstretch", rows),
        ("rowminimumheight", rows),
        ("columnstretch", columns),
        ("columnminimumwidth", columns),
    ):
        current = layout.field(field)
        if not isinstance(current, str) or not gaps:
            continue
        closed = _close_gaps(current, gaps)
        if closed != current:
            commands.append(catalog.SetLayoutStretch(layout.id, field, closed))  # type: ignore[arg-type]
    parts = []
    if rows:
        parts.append(_count(len(rows), "empty row", "empty rows"))
    if columns:
        parts.append(_count(len(columns), "empty column", "empty columns"))
    return _Ready("Simplify grid", tuple(commands), "Removed %s" % " and ".join(parts))


def _plan_adjust(doc: UiDocument, ids: Tuple[NodeId, ...], request: Adjust, measured: Measured) -> _Plan:
    del request
    if len(ids) > 1:
        return Refused("Select one widget to adjust its size.")
    node = doc.node(ids[0]) if ids else doc.root
    if isinstance(node, LayoutNode):
        owner = node.owner_widget_id()
        if owner is None:
            return Refused("A layout inside a layout takes its size from the outer one.")
        node = doc.node(owner)
    if not isinstance(node, WidgetNode):
        return Refused("Select a widget to adjust its size.")
    if doc.containing_layout_item(node.id) is not None:
        return Refused("A widget in a layout takes its size from the layout.")
    parent = doc.parent(node.id)
    if parent is not None and is_page_container(doc, parent.id):
        return Refused("A page takes its size from its container.")
    measure = measured.get(node.id)
    if measure is None:
        return Refused("Its size isn't known yet.")
    geometry = node.value("geometry")
    hint = measure.hint
    if isinstance(geometry, RectValue) and (geometry.width, geometry.height) == (hint.width, hint.height):
        return Current()
    return _Ready(
        "Adjust size",
        (catalog.AdjustSize(node.id, hint),),
        "Resized %s to fit its content" % _name(doc, node),
    )


def _plan_keep_content(
    doc: UiDocument, ids: Tuple[NodeId, ...], request: KeepContent, measured: Measured
) -> _Plan:
    del request
    node = _single_widget(doc, ids)
    if node is None:
        return Refused("Select one widget to keep it at its content size.")
    if node.id == doc.root.id:
        return Refused("Select a widget inside the form.")
    measure = measured.get(node.id)
    policies = measure.policies if measure is not None else ("Preferred", "Preferred")
    policy = node.value("sizePolicy")
    minimum = node.value("minimumSize")
    maximum = node.value("maximumSize")
    current_policy = policy if isinstance(policy, SizePolicyValue) else None
    current_minimum = minimum if isinstance(minimum, SizeValue) else None
    current_maximum = maximum if isinstance(maximum, SizeValue) else None
    write = encode_axis(
        axis="v",
        word=WORD_HUG,
        pixels=None,
        current_policy=current_policy,
        current_minimum=current_minimum,
        current_maximum=current_maximum,
        class_default_h=policies[0],
        class_default_v=policies[1],
    )
    layout_id: Optional[NodeId] = None
    field: Optional[str] = None
    stretch: Optional[str] = None
    for slot in share_slots(doc, node.id):
        if slot.axis != "v":
            continue
        text = doc.node(slot.layout).field(slot.field)
        current = text if isinstance(text, str) else None
        spliced = splice_stretch(current, slot.index, 0, slot.index + 1)
        if spliced != current:
            layout_id, field, stretch = slot.layout, slot.field, spliced
    unchanged = (
        write.policy == current_policy
        and write.minimum == current_minimum
        and write.maximum == current_maximum
        and layout_id is None
    )
    if unchanged:
        return Current()
    command = from_write(node.id, write, layout=layout_id, stretch_field=field, stretch=stretch)
    return _Ready("Size", (command,), "%s now keeps its content height" % _subject(doc, node))


def _plan_lock_size(doc: UiDocument, ids: Tuple[NodeId, ...], request: LockSize, measured: Measured) -> _Plan:
    node = _single_widget(doc, ids)
    if node is None:
        return Refused("Select one widget to lock its size.")
    measure = measured.get(node.id)
    if measure is None:
        return Refused("Its size isn't known yet.")
    size = SizeValue(measure.rect.width, measure.rect.height)
    touch_minimum = request.which in (LOCK_MINIMUM, LOCK_BOTH)
    touch_maximum = request.which in (LOCK_MAXIMUM, LOCK_BOTH)
    if not touch_minimum and not touch_maximum:
        return Refused(_DOES_NOT_APPLY)
    if (not touch_minimum or node.value("minimumSize") == size) and (
        not touch_maximum or node.value("maximumSize") == size
    ):
        return Current()
    command = ApplySizing(
        node.id,
        minimum=size if touch_minimum else None,
        maximum=size if touch_maximum else None,
        touch_minimum=touch_minimum,
        touch_maximum=touch_maximum,
    )
    dims = "%d \u00d7 %d" % (size.width, size.height)
    subject = _subject(doc, node)
    if request.which == LOCK_MINIMUM:
        sentence = "%s can't shrink below %s" % (subject, dims)
    elif request.which == LOCK_MAXIMUM:
        sentence = "%s can't grow past %s" % (subject, dims)
    else:
        sentence = "%s stays at %s" % (subject, dims)
    return _Ready("Size", (command,), sentence)


def _plan_change_to(doc: UiDocument, ids: Tuple[NodeId, ...], request: ChangeTo, measured: Measured) -> _Plan:
    del measured
    node = _single_widget(doc, ids)
    if node is None or node.id == doc.root.id:
        return Refused("Select one widget inside the form to change its class.")
    if node.class_name == request.class_name:
        return Current()
    target = next(
        (item for item in _FAMILY_OF.get(node.class_name, ()) if item.class_name == request.class_name),
        None,
    )
    if target is None:
        return Refused("%s can only change to a related widget." % _subject(doc, node))
    return _Ready(
        "Change widget",
        (catalog.MorphWidget(node.id, target.class_name),),
        "Changed to %s." % target.phrase,
    )


_PLANNERS: Mapping[type, Callable[..., _Plan]] = {
    ApplyKind: _plan_apply_kind,
    PickWrap: _plan_pick_wrap,
    InspectedKind: _plan_inspected_kind,
    Unwrap: _plan_unwrap,
    RemoveLayout: _plan_remove_layout,
    Simplify: _plan_simplify,
    Adjust: _plan_adjust,
    KeepContent: _plan_keep_content,
    LockSize: _plan_lock_size,
    ChangeTo: _plan_change_to,
}


@dataclass(frozen=True)
class _Siblings:
    parent: NodeId
    in_layout: bool
    ids: Tuple[NodeId, ...]


def _siblings(doc: UiDocument, ids: Sequence[NodeId]) -> Union[_Siblings, Refused]:
    if not ids or doc.root.id in ids:
        return Refused(_ROOT_WRAP)
    parents = set()
    carriers: List[Tuple[int, NodeId]] = []
    for node_id in ids:
        node = doc.node(node_id)
        parent = doc.parent(node_id)
        carrier: Node = parent if isinstance(parent, LayoutItemNode) else node
        holder = doc.parent(carrier.id)
        if holder is None or carrier.parent_slot not in ("layout_items", "children"):
            return Refused("Select widgets to wrap them.")
        parents.add(holder.id)
        carriers.append((carrier.slot_index, node_id))
    if len(parents) != 1:
        return Refused(MIXED_PARENT)
    parent_id = next(iter(parents))
    if is_page_container(doc, parent_id):
        return Refused("Pages can't be wrapped.")
    parent = doc.node(parent_id)
    if isinstance(parent, WidgetNode) and parent.class_name == "QMainWindow":
        return Refused("Main window parts can't be wrapped.")
    ordered = tuple(node_id for _index, node_id in sorted(carriers))
    return _Siblings(parent_id, isinstance(parent, LayoutNode), ordered)


def _wrap(doc: UiDocument, ids: Tuple[NodeId, ...], kind: Kind, measured: Measured) -> _Plan:
    siblings = _siblings(doc, ids)
    if isinstance(siblings, Refused):
        return siblings
    shape = kind.shape
    if isinstance(shape, (SplitterShape, TabShape)) and any(
        not isinstance(doc.node(node_id), WidgetNode) for node_id in siblings.ids
    ):
        return Refused("Only widgets can go in %s." % kind.noun)
    rects = _rects(doc, siblings.ids, measured)
    geometry: Optional[RectValue] = None
    if not siblings.in_layout:
        geometry = _bounds([rects[node_id] for node_id in siblings.ids if node_id in rects])
        if geometry is None:
            return Refused("Its size isn't known yet.")
    command: Command
    if isinstance(shape, SplitterShape):
        command = WrapSplitter(siblings.ids, shape.orientation, geometry)
    elif isinstance(shape, TabShape):
        command = WrapTab(siblings.ids, shape.title, geometry)
    elif siblings.in_layout and isinstance(shape, ContainerShape):
        command = catalog.Wrap(siblings.ids, shape.container_class)
    elif siblings.in_layout:
        assert isinstance(shape, LayoutShape)
        command = catalog.Wrap(siblings.ids, None, shape.layout_class, _named_cells(siblings.ids, shape, rects))
    else:
        assert geometry is not None
        if isinstance(shape, ContainerShape):
            host, layout_class = shape.container_class, "QVBoxLayout"
        else:
            host, layout_class = "QWidget", shape.layout_class
        order, cells = _arrange(siblings.ids, layout_class, rects)
        command = WrapFree(siblings.ids, host, layout_class, geometry, order, cells)
    sentence = "Wrapped %s in %s" % (_count(len(siblings.ids), "widget", "widgets"), kind.noun)
    return _Ready("Wrap", (command,), sentence)


def _named_cells(
    ids: Tuple[NodeId, ...], shape: LayoutShape, rects: Mapping[NodeId, RectValue]
) -> Optional[Tuple[Tuple[NodeId, int, int], ...]]:
    if shape.layout_class == "QFormLayout":
        return _form_cells(ids, rects)
    if shape.layout_class == "QGridLayout":
        return tuple((node_id, row, column) for node_id, row, column, _rs, _cs in _grid_cells(ids, rects))
    return None


def _lay_out(doc: UiDocument, widget: WidgetNode, kind: Kind, measured: Measured) -> _Plan:
    shape = kind.shape
    assert isinstance(shape, LayoutShape)
    if widget.class_name == "QMainWindow":
        return Refused("Lay out the central widget instead.")
    children = tuple(child.id for child in widget.child_widgets)
    order, cells = _arrange(children, shape.layout_class, _rects(doc, children, measured))
    command = catalog.ApplyLayout(widget.id, shape.layout_class, order, cells)
    return _Ready("Lay out", (command,), "Laid out %s in %s" % (_name(doc, widget), kind.noun))


def _arrange(
    ids: Tuple[NodeId, ...], layout_class: str, rects: Mapping[NodeId, RectValue]
) -> Tuple[Tuple[NodeId, ...], Optional[Tuple[Tuple[NodeId, int, int, int, int], ...]]]:
    """Reading order and ``ApplyLayout`` cells for free widgets about to share a layout."""
    order = _reading_order(ids, rects, vertical=layout_class != "QHBoxLayout")
    if layout_class == "QGridLayout":
        return order, _grid_cells(order, rects)
    if layout_class == "QFormLayout":
        form = _form_cells(order, rects)
        return order, None if form is None else tuple((node_id, row, column, 1, 1) for node_id, row, column in form)
    return order, None


def _morph(doc: UiDocument, layout: LayoutNode, new_class: str) -> _Plan:
    if layout.class_name == new_class:
        return Current()
    command = catalog.MorphLayout(layout.id, new_class)
    lost = spans_cleared(doc, layout.id, new_class)
    if not lost:
        return _Ready("Change layout", (command,), "Changed the layout")
    ready = _Ready(
        "Change layout",
        (command,),
        "Changed the layout and removed spans from %s" % _count(lost, "widget", "widgets"),
    )
    return _Confirm("Spans will be removed from %s." % _count(lost, "widget", "widgets"), "Change layout", ready)


def _orient(splitter: WidgetNode, shape: SplitterShape, kind: Kind) -> _Plan:
    current = splitter.value("orientation")
    text = current.text if isinstance(current, EnumValue) else "Qt::Horizontal"
    if text == shape.orientation:
        return Current()
    command = catalog.SetProperty(splitter.id, "orientation", EnumValue(shape.orientation))
    return _Ready("Change layout", (command,), "Made %s %s" % (splitter.object_name or "the splitter", kind.noun))


def _grid_cells(
    ids: Tuple[NodeId, ...], rects: Mapping[NodeId, RectValue]
) -> Tuple[Tuple[NodeId, int, int, int, int], ...]:
    """Rows and columns from the widgets' bands; one column when they collide."""
    one_column = tuple((node_id, index, 0, 1, 1) for index, node_id in enumerate(ids))
    if not ids or any(node_id not in rects for node_id in ids):
        return one_column
    rows = _bands([(rects[node_id].y, rects[node_id].y + rects[node_id].height) for node_id in ids])
    columns = _bands([(rects[node_id].x, rects[node_id].x + rects[node_id].width) for node_id in ids])
    taken = set()
    cells = []
    for node_id, (row, rowspan), (column, colspan) in zip(ids, rows, columns):
        covered = {(r, c) for r in range(row, row + rowspan) for c in range(column, column + colspan)}
        if not taken.isdisjoint(covered):
            return one_column
        taken |= covered
        cells.append((node_id, row, column, rowspan, colspan))
    return tuple(cells)


def _form_cells(
    ids: Tuple[NodeId, ...], rects: Mapping[NodeId, RectValue]
) -> Optional[Tuple[Tuple[NodeId, int, int], ...]]:
    """Label and field pairs per row band. None lets the form place them in order."""
    if not ids or any(node_id not in rects for node_id in ids):
        return None
    rows = _bands([(rects[node_id].y, rects[node_id].y + rects[node_id].height) for node_id in ids])
    by_row: Dict[int, List[Tuple[int, NodeId]]] = {}
    for node_id, (row, _span) in zip(ids, rows):
        by_row.setdefault(row, []).append((rects[node_id].x, node_id))
    cells = []
    for row_index, row in enumerate(sorted(by_row)):
        members = [node_id for _x, node_id in sorted(by_row[row])]
        if len(members) > 2:
            return None
        if len(members) == 1:
            cells.append((members[0], row_index, 1))
        else:
            cells.append((members[0], row_index, 0))
            cells.append((members[1], row_index, 1))
    return tuple(cells)


def _bands(intervals: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """(first band, band count) per interval. The shortest intervals found the bands."""
    spans = [(start, max(end, start + 1)) for start, end in intervals]
    bands: List[Tuple[int, int]] = []
    for span in sorted(spans, key=lambda item: (item[1] - item[0], item[0])):
        if not any(_overlaps(span, band) for band in bands):
            bands.append(span)
    bands.sort()
    placed = []
    for span in spans:
        hits = [index for index, band in enumerate(bands) if _overlaps(span, band)]
        placed.append((hits[0], hits[-1] - hits[0] + 1))
    return placed


def _overlaps(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    shared = min(a[1], b[1]) - max(a[0], b[0])
    return 2 * shared > min(a[1] - a[0], b[1] - b[0])


def _reading_order(
    ids: Tuple[NodeId, ...], rects: Mapping[NodeId, RectValue], *, vertical: bool
) -> Tuple[NodeId, ...]:
    def key(node_id: NodeId) -> Tuple[int, int, int]:
        rect = rects.get(node_id)
        if rect is None:
            return (1, 0, 0)
        return (0, rect.y, rect.x) if vertical else (0, rect.x, rect.y)

    return tuple(sorted(ids, key=key))


def _rects(doc: UiDocument, ids: Sequence[NodeId], measured: Measured) -> Dict[NodeId, RectValue]:
    """Live rects, or the stored geometry of a free widget that was not measured."""
    found: Dict[NodeId, RectValue] = {}
    for node_id in ids:
        measure = measured.get(node_id)
        stored = doc.node(node_id).value("geometry")
        if measure is not None:
            found[node_id] = measure.rect
        elif isinstance(stored, RectValue):
            found[node_id] = stored
    return found


def _bounds(rects: Sequence[RectValue]) -> Optional[RectValue]:
    if not rects:
        return None
    left = min(rect.x for rect in rects)
    top = min(rect.y for rect in rects)
    right = max(rect.x + rect.width for rect in rects)
    bottom = max(rect.y + rect.height for rect in rects)
    return RectValue(left, top, right - left, bottom - top)


def _grid_gaps(layout: LayoutNode) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    rows = set()
    columns = set()
    for item in layout.items:
        row = item.row or 0
        column = item.column or 0
        rows.update(range(row, row + (item.rowspan or 1)))
        columns.update(range(column, column + (item.colspan or 1)))
    if not rows:
        return (), ()
    return (
        tuple(value for value in range(max(rows) + 1) if value not in rows),
        tuple(value for value in range(max(columns) + 1) if value not in columns),
    )


def _close_gaps(text: str, gaps: Sequence[int]) -> Optional[str]:
    kept = [piece.strip() for index, piece in enumerate(text.split(",")) if index not in gaps]
    if all(piece.lstrip("-") in ("", "0") for piece in kept):
        return None
    return ",".join(kept)


def _container_target(
    doc: UiDocument, ids: Sequence[NodeId]
) -> Optional[Tuple[Optional[WidgetNode], Optional[LayoutNode]]]:
    """The container a layout gesture acts on, and its layout. None for anything else.

    No selection is the form. A picked layout is that layout and its owner,
    when it has one.
    """
    if not ids:
        return doc.root, doc.root.layout
    if len(ids) != 1:
        return None
    node = doc.node(ids[0])
    if isinstance(node, LayoutNode):
        owner = node.owner_widget_id()
        widget = doc.node(owner) if owner is not None else None
        return (widget if isinstance(widget, WidgetNode) else None), node
    if isinstance(node, WidgetNode) and is_container(doc, node.id) and not is_page_container(doc, node.id):
        return node, node.layout
    return None


def _grid_target(doc: UiDocument, ids: Sequence[NodeId]) -> Optional[LayoutNode]:
    target = _container_target(doc, ids)
    if target is not None and target[1] is not None:
        return target[1]
    siblings = _siblings(doc, ids)
    if isinstance(siblings, _Siblings) and siblings.in_layout:
        parent = doc.node(siblings.parent)
        return parent if isinstance(parent, LayoutNode) else None
    return None


def _single_widget(doc: UiDocument, ids: Sequence[NodeId]) -> Optional[WidgetNode]:
    if len(ids) != 1:
        return None
    node = doc.node(ids[0])
    return node if isinstance(node, WidgetNode) else None


def _shared_widget_parent(doc: UiDocument, ids: Sequence[NodeId]) -> Optional[WidgetNode]:
    parents = {node.id: node for node in (doc.parent(node_id) for node_id in ids) if node is not None}
    if len(parents) != 1 or not ids:
        return None
    parent = next(iter(parents.values()))
    return parent if isinstance(parent, WidgetNode) else None


def _morph_targets(doc: UiDocument, ids: Sequence[NodeId]) -> Tuple[MorphTarget, ...]:
    node = _single_widget(doc, ids)
    if node is None or node.id == doc.root.id:
        return ()
    return tuple(item for item in _FAMILY_OF.get(node.class_name, ()) if item.class_name != node.class_name)


def _contents(layout: LayoutNode) -> Tuple[NodeId, ...]:
    return tuple(item.content.id for item in layout.items if item.content is not None)


def _name(doc: UiDocument, node: Node) -> str:
    if node.id == doc.root.id:
        return "the form"
    if isinstance(node, (WidgetNode, LayoutNode)) and node.object_name:
        return node.object_name
    return "the layout" if isinstance(node, LayoutNode) else "the widget"


def _subject(doc: UiDocument, node: Node) -> str:
    name = _name(doc, node)
    return "The" + name[3:] if name.startswith("the ") else name


def _count(number: int, one: str, many: str) -> str:
    return "%d %s" % (number, one if number == 1 else many)


def _check_tables() -> None:
    for name, order in (("KEYBOARD", KEYBOARD), ("POPOVER", POPOVER), ("SEGMENTS", SEGMENTS)):
        if len(set(order)) != len(order) or not set(order) <= set(KINDS):
            raise RuntimeError("%s must name each kind in KINDS once" % name)
    if set(POPOVER) != set(KINDS):
        raise RuntimeError("POPOVER must offer every kind")
    if any(not isinstance(KINDS[kind_id].shape, LayoutShape) for kind_id in SEGMENTS):
        raise RuntimeError("SEGMENTS must be layout kinds")
    missing = [request.__name__ for request in get_args(Request) if request not in _PLANNERS]
    if missing:
        raise RuntimeError("no planner for %s" % ", ".join(missing))
    classes = [target.class_name for family in FAMILIES for target in family]
    if len(set(classes)) != len(classes):
        raise RuntimeError("a class sits in two morph families")


_check_tables()
