"""Step lists as Python (CONTRACTS section 15.6 "Step-list code", order 100).

Native ``<connection>`` elements are uic's own lines and stay in the core. This
expander writes the other half of an event: every ``cbcsOn<Signal>`` list
becomes one handler on the Ui class and one ``connect`` in ``_cbcs_setup``,
which runs after ``connectSlotsByName``, so native steps run first and the
list after them (the order the Events list shows).

A handler takes ``*args`` and slices them per step: a ``slot`` step passes the
first *k* values (*k* is the slot's parameter count), a ``call`` step passes
``args`` values. A list that can't be read (FB401) or has a step this build
doesn't type, or a step with a condition (FB403, M7.1), generates nothing, so
its run order is never silently changed. A step whose target left the form
(FB405) becomes a comment, because the handler would raise at run time.

Every value from the file that reaches the code is checked first: a target, a
method and a slot name must be plain names (``compat.is_name``, ``is_signature``)
or the list generates nothing, and comment text is one line with no line
break of any kind, so no text in a ``.ui`` file can become a statement.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method, one_line
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.events import signal_of_property
from app.features.form_builder.engine.logic.events_catalog import class_chain, step_words
from app.features.form_builder.engine.logic.events_codec import EventStep, StepList, read_list
from app.features.form_builder.engine.logic.verbs import VerbSpec, default_registry
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node
from app.features.form_builder.engine.ui4.values import StringValue

_PY_TYPES = {"bool": "bool", "int": "int", "double": "float", "QString": "str"}


class StepsExpander:
    expander_id = "steps"
    level = 1
    order = 100

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        classes = QtClassTable.shared()
        connects: List[str] = []
        methods: List[Method] = []
        self._bag = {"helpers": [], "imports": [], "diagnostics": []}
        root = doc.root.object_name
        for node in doc.iter_preorder():
            for entry in node.properties():
                signal_name = signal_of_property(entry.name)
                if signal_name is None or not isinstance(entry.value, StringValue):
                    continue
                if signal_name in ("opened", "closing"):
                    continue
                owner = _owner_name(node)
                expression = self._sender_expression(owner, root, ctx)
                if owner is None or expression is None:
                    continue
                parsed = read_list(entry.value.text)
                if not _generates(parsed) or not compat.is_name(signal_name):
                    continue
                handler = "_cbcs_%s_%s" % (owner, signal_name)
                if not compat.is_name(handler):
                    continue
                selector = _selector(doc, classes, node, signal_name, parsed)
                connects.append("%s.%s%s.connect(self.%s)" % (expression, signal_name, selector, handler))
                source_ref = one_line("%s: When %s" % (owner, signal_name))
                methods.append(
                    Method(
                        name=handler,
                        body=_body(doc, classes, ctx, root, parsed.steps, source_ref, self._bag, owner),
                        source_ref=source_ref,
                        params="*args",
                    )
                )
        if not methods:
            return Contribution()
        bag = getattr(self, "_bag", None) or {}
        return Contribution(
            imports=tuple(bag.get("imports") or ()),
            setup_lines=tuple(connects),
            methods=tuple(methods),
            helpers=tuple(bag.get("helpers") or ()),
            diagnostics=tuple(bag.get("diagnostics") or ()),
            needs_form=True,
        )

    @staticmethod
    def _sender_expression(owner: Optional[str], root: str, ctx: CodegenContext) -> Optional[str]:
        if owner is None:
            return None
        if owner == root:
            return ctx.form_param
        if owner in ctx.attribute_names:
            return "self.%s" % owner
        return None


EXPANDER = StepsExpander()


def _owner_name(node: Node) -> Optional[str]:
    for field in ("object_name", "name"):
        value = node.field(field)
        if isinstance(value, str) and value:
            return value
    return None


def _generates(parsed: StepList) -> bool:
    if parsed.error is not None or not parsed.steps:
        return False
    registry = default_registry()
    for step in parsed.steps:
        spec = registry.get(step.verb)
        if spec is None or spec.blocks_list(step):
            return False
    return True


def _target_of(spec: VerbSpec, step: EventStep, root: str) -> str:
    if any(field.name == "target" for field in spec.fields):
        return step.target
    raw = step.raw
    if raw is not None:
        field = raw.field("field")
        if isinstance(field, str) and field:
            return field
    return root


class _EmitCtx:
    """What a verb's ``emit`` reads. ``root`` is the form's object name."""

    def __init__(
        self,
        ctx: CodegenContext,
        root: str,
        later_on: bool,
        doc: UiDocument,
        classes: QtClassTable,
        bag: dict,
        owner: str,
    ) -> None:
        self.root = root
        self.later_on = later_on
        self.form_param = ctx.form_param
        self.attribute_names = ctx.attribute_names
        self.widgets = ctx.widgets
        self.trace = ctx.trace
        self.window = ctx.window
        self.formats = ctx.formats
        self.forms_dir = ctx.forms_dir
        self.doc = doc
        self.classes = classes
        self.bag = bag
        self.owner = owner
        self.step_number = 0
        self.formula_env = None


def _selector(
    doc: UiDocument, classes: QtClassTable, node: Node, signal_name: str, parsed: StepList
) -> str:
    """``[types]`` when the list's overload is not the one ``widget.signal`` means in PySide6.

    A list is on the overload with the most arguments unless it names another
    (CONTRACTS 15.3). PySide's bare name is the one with the fewest, so a ``clicked``
    list connects as ``clicked[bool]`` and its handler receives ``checked``.
    """
    class_name, declared = compat.node_class(doc, classes, node)
    overloads = compat.overloads_of(compat.signals_of(classes, class_name, declared), signal_name)
    if parsed.signal is not None:
        chosen = compat.split_signature(parsed.signal)[1]
    else:
        widest = compat.widest_overload(overloads)
        chosen = widest[1] if widest is not None else ()
    default = compat.pyside_default(overloads)
    if default is not None and default[1] == chosen:
        return ""
    if not chosen or any(item not in _PY_TYPES for item in chosen):
        return ""
    return "[%s]" % ", ".join(_PY_TYPES[item] for item in chosen)


def _body(
    doc: UiDocument,
    classes: QtClassTable,
    ctx: CodegenContext,
    root: str,
    steps: Sequence[EventStep],
    source_ref: str,
    bag: Optional[dict] = None,
    owner: str = "",
) -> str:
    lines: List[str] = []
    registry = default_registry()
    held = bag if bag is not None else {"helpers": [], "imports": [], "diagnostics": []}
    for number, step in enumerate(steps, 1):
        spec = registry.get(step.verb)
        if spec is None:
            continue
        later_on = any(item.enabled for item in steps[number:])
        has_named = any(field.name in ("target", "field") for field in spec.fields)
        target = _target_of(spec, step, root)
        chain: Tuple[str, ...] = ()
        node = doc.node(doc.by_name(target)[0]) if doc.by_name(target) else None
        if node is not None:
            chain = class_chain(classes, compat.node_class(doc, classes, node)[0])
        words = step_words(step, target, is_form=(target == root), target_chain=chain)
        prefix = "#   %d. " % number
        missing = node is None or (has_named and target != root and target not in ctx.attribute_names)
        emit_ctx = _EmitCtx(ctx, root, later_on, doc, classes, held, owner or root)
        emit_ctx.step_number = number
        body: List[str] = []
        if step.enabled and not missing:
            if step.when:
                guarded, code = _when_lines(step.when, emit_ctx)
                if code:
                    lines.append("# step %d skipped (%s: see Problems)" % (number, code))
                    continue
                body = ["    %s" % line if line else "" for line in spec.emit(step, emit_ctx)]
                body.insert(0, "if %s:" % guarded)
            else:
                body = list(spec.emit(step, emit_ctx))
        if not step.enabled:
            lines.append(one_line("%s(off) %s" % (prefix, words)))
        elif missing:
            lines.append(one_line("%s(missing %s) %s" % (prefix, target, words)))
        else:
            lines.append(one_line(prefix + words))
        if ctx.trace:
            lines.append('self._cbcs_trace("step", %r, %r)' % (one_line(source_ref), one_line(words)))
        if step.enabled and not missing:
            lines.extend(body)
    if lines and all(not line.strip() or line.lstrip().startswith("#") for line in lines):
        lines.append("pass")
    return "\n".join(lines)


def _when_lines(text: str, emit_ctx: _EmitCtx) -> Tuple[str, str]:
    from app.features.form_builder.engine.logic.formula.env import SlotKind
    from app.features.form_builder.engine.logic.verbs.m7 import compile_text

    source, code = compile_text(text, SlotKind.when(), emit_ctx)
    if code or not source:
        return "", code or "FB108"
    return source, ""
