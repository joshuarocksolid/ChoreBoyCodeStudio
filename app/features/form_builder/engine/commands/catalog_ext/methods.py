"""Remove one method declaration from the form. The window file is not touched."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import PlanContext
from app.features.form_builder.engine.commands.ops import SetFieldOp
from app.features.form_builder.engine.logic.compat import split_signature
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.phrases import used_by_steps
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.schema import SlotsDecl
from app.features.form_builder.engine.commands.base import CommandRejected


@dataclass(frozen=True)
class RemoveMethodDeclaration:
    """One undo step. Refused while a step still calls the method."""

    command_type: ClassVar[str] = "remove_method_declaration"
    method: str
    undo_label: str = ""

    @property
    def label(self) -> str:
        return self.undo_label or "Remove method declaration %s" % self.method

    def merge_key(self) -> None:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        used = 0
        for state in read_events(doc):
            for step in state.steps:
                if step.verb == "call" and step.method == self.method:
                    used += 1
        if used:
            raise CommandRejected(used_by_steps(self.method, used))
        declared = doc.ui.field("form_slots")
        signals = declared.signals if isinstance(declared, SlotsDecl) else ()
        slots = declared.slots if isinstance(declared, SlotsDecl) else ()
        kept = tuple(slot for slot in slots if split_signature(slot)[0] != self.method)
        planning.set_form_slots(doc, ctx, tuple(signals), kept)


@dataclass(frozen=True)
class MethodUndoMark:
    """A form-side partner for a stub written onto a step that already exists.

    The mark is not written into the ``.ui``. Each call stores a new value, so
    the log keeps every one and one undo removes that stub.
    """

    command_type: ClassVar[str] = "method_undo_mark"
    method: str

    @property
    def label(self) -> str:
        return "Create method %s" % self.method

    def merge_key(self) -> None:
        return None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        previous = doc.ui.field("method_undo_mark")
        count = 0
        if isinstance(previous, str) and previous.isdigit():
            count = int(previous)
        ctx.do(SetFieldOp(doc.ui.id, "method_undo_mark", str(count + 1)))


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if callable(add):
        add(RemoveMethodDeclaration)
        add(MethodUndoMark)
