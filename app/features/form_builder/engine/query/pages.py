"""Page containers and their pages (UX-CONT-001, CONTRACTS section 3.5).

Pure: reads the document, never edits it. Every container kind stores a page
the way its Qt loader reads it. ``start_index`` is the saved ``currentIndex``
(UX-CONT-006). A wizard has none: Qt always starts a wizard on its first page,
so the start page of a wizard is its first page and cannot be changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue


@dataclass(frozen=True)
class PageKind:
    """How one container class holds its pages.

    ``title_home`` is ``("attribute", name)``, ``("property", name)`` or None
    when the container has no per-page title (stacked widget).
    """

    kind: str
    page_class: str
    name_prefix: str
    title_home: Optional[Tuple[str, str]]
    word: str
    has_start_page: bool


PAGE_KINDS = {
    "QTabWidget": PageKind("tab", "QWidget", "tab", ("attribute", "title"), "Tab", True),
    "QToolBox": PageKind("toolbox", "QWidget", "page", ("attribute", "label"), "Page", True),
    "QStackedWidget": PageKind("stacked", "QWidget", "page", None, "Page", True),
    "QWizard": PageKind("wizard", "QWizardPage", "wizardPage", ("property", "title"), "Step", False),
    "QMdiArea": PageKind("mdi", "QWidget", "subwindow", ("property", "windowTitle"), "Window", False),
}


def page_kind(doc: UiDocument, container_id: NodeId) -> Optional[PageKind]:
    """The page kind of a page container, or None for any other node. O(1)."""
    node = doc.get(container_id)
    if not isinstance(node, WidgetNode):
        return None
    return PAGE_KINDS.get(node.class_name)


def pages(doc: UiDocument, container_id: NodeId) -> Tuple[WidgetNode, ...]:
    """The pages of a container in order. Empty for a node that is not one."""
    if page_kind(doc, container_id) is None:
        return ()
    return doc.node(container_id).child_widgets  # type: ignore[attr-defined]


def innermost_container(doc: UiDocument, node_id: NodeId) -> Optional[NodeId]:
    """The nearest page container at or above ``node_id`` (UX-CONT-002).

    A page container counts as its own innermost container. A page or any
    widget inside one resolves to the container that holds the page.
    """
    current: Optional[NodeId] = node_id
    while current is not None and doc.contains(current):
        if page_kind(doc, current) is not None:
            return current
        parent = doc.parent(current)
        current = parent.id if parent is not None else None
    return None


def start_index(doc: UiDocument, container_id: NodeId) -> Optional[int]:
    """The saved ``currentIndex``, 0 when the file omits it. None when the
    container has no start page (wizard, MDI area)."""
    kind = page_kind(doc, container_id)
    if kind is None or not kind.has_start_page:
        return None
    entry = doc.node(container_id).prop("currentIndex")
    if entry is None or not isinstance(entry.value, NumberValue):
        return 0
    return entry.value.value


def start_page(doc: UiDocument, container_id: NodeId) -> Optional[NodeId]:
    """The page the file starts on. None when there are no pages.

    A saved index past the last page clamps to the last page, as Qt does. A
    wizard has no saved start, so its start page is its first page.
    """
    kind = page_kind(doc, container_id)
    found = pages(doc, container_id)
    if kind is None or not found:
        return None
    if not kind.has_start_page:
        return found[0].id
    index = start_index(doc, container_id)
    assert index is not None
    return found[min(max(index, 0), len(found) - 1)].id


def page_title(doc: UiDocument, page_id: NodeId) -> str:
    """The title the page shows in the outline and on the canvas (UX-CONT-001).

    A stacked page has no title, so its object name is used.
    """
    node = doc.get(page_id)
    if not isinstance(node, WidgetNode):
        return ""
    parent = doc.parent(page_id)
    kind = page_kind(doc, parent.id) if parent is not None else None
    if kind is None or kind.title_home is None:
        return node.object_name or ""
    storage, name = kind.title_home
    entry = node.attr(name) if storage == "attribute" else node.prop(name)
    if entry is None or not isinstance(entry.value, StringValue):
        return ""
    return entry.value.text


def page_widget_count(doc: UiDocument, page_id: NodeId) -> int:
    """Widgets on a page, at any depth. Used by the delete confirmation (UX-CONT-004)."""
    if not doc.contains(page_id):
        return 0
    return sum(1 for node in doc.iter_preorder(page_id) if isinstance(node, WidgetNode)) - 1


def default_title(kind: PageKind, number: int) -> str:
    """"Tab 3", "Page 3", "Step 3" or "Window 3" (UX-CONT-003)."""
    return "%s %d" % (kind.word, number)


def page_name_base(kind: PageKind, number: int) -> str:
    """The first name tried for a new page: ``tab_3``, ``page_3``, ``wizardPage_3``, ``subwindow_3``."""
    return "%s_%d" % (kind.name_prefix, number)


__all__ = [
    "PAGE_KINDS",
    "PageKind",
    "default_title",
    "innermost_container",
    "page_kind",
    "page_name_base",
    "page_title",
    "page_widget_count",
    "pages",
    "start_index",
    "start_page",
]
