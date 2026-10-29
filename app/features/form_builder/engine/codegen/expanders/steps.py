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
"""

from __future__ import annotations

import keyword
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.events import signal_of_property
from app.features.form_builder.engine.logic.events_catalog import class_chain, step_words
from app.features.form_builder.engine.logic.events_codec import EventStep, StepList, read_list
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
        root = doc.root.object_name
        for node in doc.iter_preorder():
            for entry in node.properties():
                signal_name = signal_of_property(entry.name)
                if signal_name is None or not isinstance(entry.value, StringValue):
                    continue
                owner = _owner_name(node)
                expression = self._sender_expression(owner, root, ctx)
                if owner is None or expression is None:
                    continue
                parsed = read_list(entry.value.text)
                if not _generates(parsed):
                    continue
                handler = "_cbcs_%s_%s" % (owner, signal_name)
                if not handler.isidentifier():
                    continue
                selector = _selector(doc, classes, node, signal_name, parsed)
                connects.append("%s.%s%s.connect(self.%s)" % (expression, signal_name, selector, handler))
                methods.append(
                    Method(
                        name=handler,
                        body=_body(doc, classes, ctx, root, parsed.steps),
                        source_ref="%s: When %s" % (owner, signal_name),
                        params="*args",
                    )
                )
        if not methods:
            return Contribution()
        setup = ["self._form = %s" % ctx.form_param] + connects
        return Contribution(setup_lines=tuple(setup), methods=tuple(methods))

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
    return all(step.verb in ("slot", "call") and step.when is None and step.raw is None for step in parsed.steps)


def _selector(
    doc: UiDocument, classes: QtClassTable, node: Node, signal_name: str, parsed: StepList
) -> str:
    """``[types]`` when the list means an overload other than PySide's default (the widest)."""
    if parsed.signal is None:
        return ""
    class_name, declared = compat.node_class(doc, classes, node)
    overloads = compat.overloads_of(compat.signals_of(classes, class_name, declared), signal_name)
    widest = compat.widest_overload(overloads)
    _name, params = compat.split_signature(parsed.signal)
    if widest is not None and widest[1] == params:
        return ""
    if not params or any(item not in _PY_TYPES for item in params):
        return ""
    return "[%s]" % ", ".join(_PY_TYPES[item] for item in params)


def _body(
    doc: UiDocument,
    classes: QtClassTable,
    ctx: CodegenContext,
    root: str,
    steps: Sequence[EventStep],
) -> str:
    lines: List[str] = []
    for number, step in enumerate(steps, 1):
        later_on = any(item.enabled for item in steps[number:])
        target = root if step.verb == "call" else step.target
        chain: Tuple[str, ...] = ()
        node = doc.node(doc.by_name(target)[0]) if doc.by_name(target) else None
        if node is not None:
            chain = class_chain(classes, compat.node_class(doc, classes, node)[0])
        words = step_words(step, target, is_form=(target == root), target_chain=chain)
        prefix = "#   %d. " % number
        if not step.enabled:
            lines.append("%s(off) %s" % (prefix, words))
            continue
        if node is None or (step.verb == "slot" and target != root and target not in ctx.attribute_names):
            lines.append("%s(missing %s) %s" % (prefix, target, words))
            continue
        lines.append(prefix + words)
        lines.append(_statement(step, root, later_on))
        # The call/slot statement follows its comment.
    return "\n".join(lines)


def _statement(step: EventStep, root: str, later_on: bool) -> str:
    if step.verb == "call":
        call = "self._form.%s(%s)" % (step.method, _args(step.args))
        if later_on:
            return "if %s is False:\n    return" % call
        return call
    name, params = compat.split_signature(step.slot)
    if keyword.iskeyword(name):
        name += "_"
    owner = "self._form" if step.target == root else "self.%s" % step.target
    return "%s.%s(%s)" % (owner, name, _args(len(params)))


def _args(count: int) -> str:
    return "*args[:%d]" % count if count else ""
