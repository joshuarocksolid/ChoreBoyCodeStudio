"""Use your own class, and go back to the base class (UX-CUST-004, 005).

Designer calls these Promote and Demote. ``UseOwnClass`` declares the class
once per form (``<customwidget>`` with ``<header location="local">`` holding the
module as ``widgets/till_display.h``) and sets each widget's ``class``.
``UseBaseClass`` sets the widgets back to the declared base and drops a
declaration nothing uses. Every other child of an existing declaration
(``sizehint``, ``slots``, ``propertyspecifications``...) is kept as written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional, Set, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import _CommandBase
from app.features.form_builder.engine.commands.ops import RemoveNodeOp
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.custom_widgets import (
    RegistryEntry,
    declaration_spec,
    valid_class_name,
)
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(UseOwnClass)
    add(UseBaseClass)


def _for(names: Tuple[str, ...], count: int) -> str:
    if count == 1 and names and names[0]:
        return names[0]
    return "%d widgets" % count


@dataclass(frozen=True)
class UseOwnClass(_CommandBase):
    """Set ``ids`` to ``class_name`` and declare it once. One undo step: "Use class {Class} for {name}"."""

    command_type: ClassVar[str] = "use_own_class"
    _label_text: ClassVar[str] = "Use own class"
    ids: Tuple[NodeId, ...]
    class_name: str
    module: str
    extends: str
    container: bool = False
    size: Optional[Tuple[int, int]] = None
    #: Object names for the undo label, in the order of ``ids``.
    names: Tuple[str, ...] = ()
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        return "Use class %s for %s" % (self.class_name, _for(self.names, len(self.ids)))

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if not self.ids:
            raise CommandRejected("Select a widget first.")
        if not valid_class_name(self.class_name):
            raise CommandRejected("Use a class name like TillDisplay: letters, digits and _, starting with a letter.")
        entry = RegistryEntry(self.class_name, self.module, self.extends, self.container, size=self.size)
        try:
            spec = declaration_spec(entry)
        except ValueError:
            raise CommandRejected("Use a module path like widgets.till_display.") from None
        previous: Set[str] = set()
        for node_id in self.ids:
            node = doc.get(node_id)
            if not isinstance(node, WidgetNode):
                raise CommandRejected("That object is no longer in the form.")
            if node.id == doc.root.id:
                raise CommandRejected("The form itself can't use your own class.")
            if node.class_name != self.class_name and doc.custom_widget(node.class_name) is not None:
                previous.add(node.class_name)
        existing = doc.custom_widget(self.class_name)
        if existing is not None and existing.field("extends") != self.extends:
            raise CommandRejected(
                "%s is already used on this form, based on %s." % (self.class_name, existing.field("extends"))
            )
        planning.promote(doc, ctx, self.ids, self.class_name, spec)
        _drop_declarations(doc, ctx, previous, exclude=self.ids, keep=self.class_name)


@dataclass(frozen=True)
class UseBaseClass(_CommandBase):
    """Back to the base class (Designer's Demote). One undo step: "Use {friendly base} for {name}"."""

    command_type: ClassVar[str] = "use_base_class"
    _label_text: ClassVar[str] = "Use base class"
    ids: Tuple[NodeId, ...]
    friendly: str = ""
    names: Tuple[str, ...] = ()
    merge_token: Optional[str] = None

    @property
    def label(self) -> str:
        shown = self.friendly or "base class"
        return "Use %s for %s" % (shown, _for(self.names, len(self.ids)))

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if not self.ids:
            raise CommandRejected("Select a widget first.")
        planning.promote(doc, ctx, self.ids, None, None)


def _drop_declarations(doc: UiDocument, ctx: PlanContext, classes: Set[str], exclude: Tuple[NodeId, ...], keep: str) -> None:
    """Remove the declarations of ``classes`` that no widget outside ``exclude`` still uses."""
    if not classes:
        return
    changed = set(exclude)
    still = {node.class_name for node in doc.iter_widgets() if node.id not in changed}
    for name in classes:
        if name == keep or name in still:
            continue
        declared = doc.custom_widget(name)
        if declared is not None:
            ctx.do(RemoveNodeOp(declared.id))


__all__ = ["UseBaseClass", "UseOwnClass", "register"]
