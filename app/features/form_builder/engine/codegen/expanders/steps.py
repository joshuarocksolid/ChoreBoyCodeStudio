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

import re
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
                if not _generates(parsed) or not compat.is_name(signal_name):
                    continue
                handler = "_cbcs_%s_%s" % (owner, signal_name)
                if not compat.is_name(handler):
                    continue
                selector = _selector(doc, classes, node, signal_name, parsed)
                connects.append("%s.%s%s.connect(self.%s)" % (expression, signal_name, selector, handler))
                methods.append(
                    Method(
                        name=handler,
                        body=_body(doc, classes, ctx, root, parsed.steps),
                        source_ref=_one_line("%s: When %s" % (owner, signal_name)),
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
    return all(
        step.verb in ("slot", "call")
        and step.when is None
        and step.raw is None
        and _names_ok(step)
        for step in parsed.steps
    )


def _names_ok(step: EventStep) -> bool:
    """Only plain names reach the generated code; anything else keeps the whole list out."""
    if step.verb == "call":
        return compat.is_name(step.method) and 0 <= step.args <= 99
    return compat.is_name(step.target) and compat.is_signature(step.slot)


#: Every character Python or ``str.splitlines`` treats as a line break, and other control characters.
_BREAKS = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _one_line(text: str) -> str:
    """Text for a ``#`` comment: one line, whatever the file held."""
    return _BREAKS.sub(" ", text)


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
            lines.append(_one_line("%s(off) %s" % (prefix, words)))
            continue
        if node is None or (step.verb == "slot" and target != root and target not in ctx.attribute_names):
            lines.append(_one_line("%s(missing %s) %s" % (prefix, target, words)))
            continue
        lines.append(_one_line(prefix + words))
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
    owner = "self._form" if step.target == root else "self.%s" % step.target
    return "%s.%s(%s)" % (owner, name, _args(len(params)))


def _args(count: int) -> str:
    return "*args[:%d]" % count if count else ""
