"""Page commands for tab widgets, toolboxes, stacked widgets, wizards and MDI areas.

``InsertPage`` writes each page where its container's loader reads it
(UX-CONT-001, UX-CONT-003). ``DeletePage`` removes a page with the
``DeleteNodes`` reference rules and keeps the start page on the same page,
or clamps it when the start page itself was deleted (UX-CONT-004).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional, Tuple

from app.features.form_builder.engine.commands import planning
from app.features.form_builder.engine.commands.base import CommandRejected, PlanContext
from app.features.form_builder.engine.commands.catalog import _CommandBase
from app.features.form_builder.engine.commands.placement import InBoxLayout, InContainer
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.pages import (
    PageKind,
    default_title,
    page_kind,
    page_name_base,
    pages,
    start_index,
)
from app.features.form_builder.engine.ui4.document import UiDocument, next_object_name
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(InsertPage)
    add(DeletePage)
    add(FillScrollArea)


#: Undo name for "Start on this page" (UX_SPEC 13.1.6). The start page is
#: ``SetProperty currentIndex`` on the container, run by the Pages menu and the
#: inspector Pages group alike.
START_PAGE_LABEL = "Change start page"


@dataclass(frozen=True)
class InsertPage(_CommandBase):
    """Insert a page at ``index`` (default: after the last page).

    ``currentIndex`` stays on the page it was on. The new page gets a vertical
    layout and is selected; it does not become the start page.
    """

    command_type: ClassVar[str] = "insert_page"
    _label_text: ClassVar[str] = "Insert page"
    container: NodeId
    index: Optional[int] = None
    fragment: Optional[Fragment] = None
    existing: Tuple[NodeId, ...] = ()
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        if not doc.contains(self.container):
            raise CommandRejected("That object is no longer in the form.")
        kind = page_kind(doc, self.container)
        if kind is None:
            raise CommandRejected("That is not a page container.")
        count = len(pages(doc, self.container))
        index = count if self.index is None else self.index
        if index < 0 or index > count:
            raise CommandRejected("That page position is outside the container.")
        if self.existing and any(not doc.contains(node_id) for node_id in self.existing):
            raise CommandRejected("That object is no longer in the form.")
        stored = start_index(doc, self.container)
        # The page the file starts on, as Qt reads it (an index past the end clamps).
        old_current = None if stored is None or count == 0 else min(max(stored, 0), count - 1)
        name = next_object_name(page_name_base(kind, count + 1), _taken_names(doc))
        title = _title_entry(kind, default_title(kind, index + 1))
        properties = (title,) if title is not None and title.kind == "property" else ()
        attributes = (title,) if title is not None and title.kind == "attribute" else ()
        spec = NodeSpec(
            "widget",
            None,
            (("class_name", kind.page_class), ("object_name", name)),
            properties,
            attributes,
        )
        ids, _, _, _ = planning.insert_fragment(
            doc, ctx, InContainer(self.container, index), Fragment((spec,)), False
        )
        page_id = ids[0]
        if old_current is not None:
            kept = old_current + 1 if old_current >= index else old_current
            if kept != stored:
                planning.set_property(doc, ctx, self.container, "currentIndex", NumberValue(kept))
        layout_id = planning.apply_layout_command(doc, ctx, page_id, "QVBoxLayout", (), None)
        if self.existing:
            planning.move_nodes(doc, ctx, self.existing, InBoxLayout(layout_id, 0))
            for node_id in self.existing:
                _clear_geometry(doc, ctx, node_id)
            ctx.select(self.existing, self.existing[0])
            return page_id
        if self.fragment is not None:
            planning.insert_fragment(doc, ctx, InBoxLayout(layout_id, 0), self.fragment, False)
        ctx.select((page_id,), page_id)
        return page_id


@dataclass(frozen=True)
class DeletePage(_CommandBase):
    """Delete the page at ``index`` and its subtree.

    The start page stays the same page. When the start page itself is deleted,
    the next page takes its index (or the previous page, when it was last).
    The selection goes to the next page, else the previous one, else the container.
    """

    command_type: ClassVar[str] = "delete_page"
    _label_text: ClassVar[str] = "Delete page"
    container: NodeId
    index: int
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> None:
        if not doc.contains(self.container):
            raise CommandRejected("That object is no longer in the form.")
        if page_kind(doc, self.container) is None:
            raise CommandRejected("That is not a page container.")
        found = pages(doc, self.container)
        if self.index < 0 or self.index >= len(found):
            raise CommandRejected("That page is no longer in the form.")
        page = found[self.index]
        current = start_index(doc, self.container)
        if current is not None:
            if self.index < current:
                new_current: Optional[int] = current - 1
            elif self.index == current:
                new_current = min(current, len(found) - 2)
            else:
                new_current = current
            if new_current != current:
                planning.set_property(
                    doc,
                    ctx,
                    self.container,
                    "currentIndex",
                    NumberValue(max(new_current, 0)) if len(found) > 1 else None,
                )
        if self.index + 1 < len(found):
            after: NodeId = found[self.index + 1].id
        elif self.index > 0:
            after = found[self.index - 1].id
        else:
            after = self.container
        planning.delete_nodes(doc, ctx, (page.id,))
        ctx.select((after,), after)


@dataclass(frozen=True)
class FillScrollArea(_CommandBase):
    """Give an empty scroll area its content widget, then put the drop in it (UX-CONT-010).

    The content is ``scrollAreaWidgetContents`` with a vertical layout. One undo step.
    """

    command_type: ClassVar[str] = "fill_scroll_area"
    _label_text: ClassVar[str] = "Insert"
    container: NodeId
    fragment: Optional[Fragment] = None
    existing: Tuple[NodeId, ...] = ()
    merge_token: Optional[str] = None

    def apply(self, doc: UiDocument, ctx: PlanContext) -> NodeId:
        if not doc.contains(self.container):
            raise CommandRejected("That object is no longer in the form.")
        host = doc.node(self.container)
        if not isinstance(host, WidgetNode) or host.class_name != "QScrollArea":
            raise CommandRejected("That is not a scroll area.")
        if host.child_widgets:
            raise CommandRejected("That scroll area already has its content.")
        if self.existing and any(not doc.contains(node_id) for node_id in self.existing):
            raise CommandRejected("That object is no longer in the form.")
        name = next_object_name("scrollAreaWidgetContents", _taken_names(doc))
        spec = NodeSpec("widget", None, (("class_name", "QWidget"), ("object_name", name)), ())
        ids, _, _, _ = planning.insert_fragment(doc, ctx, InContainer(self.container, 0), Fragment((spec,)), False)
        content = ids[0]
        layout_id = planning.apply_layout_command(doc, ctx, content, "QVBoxLayout", (), None)
        if self.existing:
            planning.move_nodes(doc, ctx, self.existing, InBoxLayout(layout_id, 0))
            for node_id in self.existing:
                _clear_geometry(doc, ctx, node_id)
            ctx.select(self.existing, self.existing[0])
            return content
        if self.fragment is not None:
            planning.insert_fragment(doc, ctx, InBoxLayout(layout_id, 0), self.fragment, False)
        ctx.select((content,), content)
        return content


def _title_entry(kind: PageKind, title: str) -> Optional[PropertyEntry]:
    if kind.title_home is None:
        return None
    storage, name = kind.title_home
    return PropertyEntry(storage, name, StringValue(title))


def _taken_names(doc: UiDocument) -> set:
    """Every object name in the document: a page name must not reuse a layout's either."""
    taken = set()
    for node in doc.iter_preorder():
        name = getattr(node, "object_name", "")
        if name:
            taken.add(name)
    return taken


def _clear_geometry(doc: UiDocument, ctx: PlanContext, node_id: NodeId) -> None:
    if doc.contains(node_id) and doc.node(node_id).prop("geometry") is not None:
        planning.set_property(doc, ctx, node_id, "geometry", None)


__all__ = ["START_PAGE_LABEL", "DeletePage", "FillScrollArea", "InsertPage", "register"]
