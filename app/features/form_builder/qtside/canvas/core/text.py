"""Which text the in-place editor edits, and the command that writes it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Literal, Mapping, Optional

from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import BoolValue, StringValue
from app.features.form_builder.qtside.canvas.core.structure import (
    effective_class,
    first_child,
)

TextSite = Literal["widget", "page_tab", "menu_title"]

_PAGE_PARENTS = frozenset({"QTabWidget", "QToolBox"})


@dataclass(frozen=True)
class TextTarget:
    owner: NodeId
    name: str
    kind: Literal["property", "attribute"]
    site: TextSite
    multiline: bool
    original: Optional[StringValue]


TEXT_PROPERTY: Mapping[str, str] = {
    "QLabel": "text",
    "QPushButton": "text",
    "QToolButton": "text",
    "QRadioButton": "text",
    "QCheckBox": "text",
    "QCommandLinkButton": "text",
    "QGroupBox": "title",
    "QLineEdit": "text",
}

LIST_TEXT_CLASSES: FrozenSet[str] = frozenset({"QComboBox", "QListWidget", "QFontComboBox"})


def text_target(document: UiDocument, node: NodeId, site: TextSite) -> Optional[TextTarget]:
    found = document.get(node)
    if not isinstance(found, WidgetNode):
        return None
    if site == "page_tab":
        return _attribute_target(found, _page_attribute(document, found), "page_tab")
    if site == "menu_title":
        return _property_target(found, "title", "menu_title", False)
    class_name = effective_class(document, found)
    if class_name in LIST_TEXT_CLASSES:
        return None
    if class_name == "QMenu":
        return _property_target(found, "title", "menu_title", False)
    prop = TEXT_PROPERTY.get(class_name)
    if prop is None:
        return None
    if class_name == "QLineEdit" and not _string_text(found, "text"):
        prop = "placeholderText"
    multiline = class_name == "QLabel" and _word_wrap(found)
    return _property_target(found, prop, "widget", multiline)


def page_title_target(document: UiDocument, node: NodeId) -> Optional[TextTarget]:
    """The title of a selected page, on the storage its container reads (UX-CONT-008).

    Tab widget ``title`` and toolbox ``label`` are attributes; a wizard page's
    ``title`` is a property. A stacked page has no title.
    """
    found = document.get(node)
    if not isinstance(found, WidgetNode):
        return None
    parent = document.parent(found.id)
    if not isinstance(parent, WidgetNode):
        return None
    container = effective_class(document, parent)
    if container in ("QTabWidget", "QToolBox"):
        return _attribute_target(found, _page_attribute(document, found), "page_tab")
    if container == "QWizard" and found.class_name == "QWizardPage":
        return _property_target(found, "title", "page_tab", False)
    if container == "QMdiArea":
        return _property_target(found, "windowTitle", "page_tab", False)
    return None


def enter_opens_editor(document: UiDocument, node: NodeId) -> bool:
    """A container or a layout takes Enter as "select the first child"."""
    found = document.get(node)
    if not isinstance(found, WidgetNode):
        return False
    if first_child(document, node) is not None:
        return False
    return text_target(document, node, "widget") is not None


def next_text_target(document: UiDocument, after: NodeId, backwards: bool) -> Optional[TextTarget]:
    widgets = [node.id for node in document.iter_preorder() if isinstance(node, WidgetNode)]
    if not widgets:
        return None
    if after in widgets:
        start = widgets.index(after)
    else:
        start = 0
    step = -1 if backwards else 1
    count = len(widgets)
    for offset in range(1, count):
        node_id = widgets[(start + step * offset) % count]
        target = _any_target(document, node_id)
        if target is not None:
            return target
    return None


def text_commit(target: TextTarget, text: str) -> Optional[SetProperty]:
    original = "" if target.original is None else target.original.text
    if text == original:
        return None
    previous = target.original
    value = StringValue(
        text,
        notr=None if previous is None else previous.notr,
        comment=None if previous is None else previous.comment,
        extracomment=None if previous is None else previous.extracomment,
        id=None if previous is None else previous.id,
    )
    return SetProperty(target.owner, target.name, value, kind=target.kind)


def _any_target(document: UiDocument, node_id: NodeId) -> Optional[TextTarget]:
    found = document.get(node_id)
    if not isinstance(found, WidgetNode):
        return None
    parent = document.parent(found.id)
    if isinstance(parent, WidgetNode) and effective_class(document, parent) in _PAGE_PARENTS:
        return text_target(document, node_id, "page_tab")
    if effective_class(document, found) == "QMenu":
        return text_target(document, node_id, "menu_title")
    return text_target(document, node_id, "widget")


def _page_attribute(document: UiDocument, node: WidgetNode) -> str:
    parent = document.parent(node.id)
    if isinstance(parent, WidgetNode) and effective_class(document, parent) == "QToolBox":
        return "label"
    return "title"


def _attribute_target(node: WidgetNode, name: str, site: TextSite) -> TextTarget:
    entry = node.attr(name)
    original = entry.value if entry is not None and isinstance(entry.value, StringValue) else None
    return TextTarget(node.id, name, "attribute", site, False, original)


def _property_target(node: WidgetNode, name: str, site: TextSite, multiline: bool) -> TextTarget:
    entry = node.prop(name)
    original = entry.value if entry is not None and isinstance(entry.value, StringValue) else None
    return TextTarget(node.id, name, "property", site, multiline, original)


def _string_text(node: WidgetNode, name: str) -> str:
    entry = node.prop(name)
    if entry is None or not isinstance(entry.value, StringValue):
        return ""
    return entry.value.text


def _word_wrap(node: WidgetNode) -> bool:
    entry = node.prop("wordWrap")
    return entry is not None and isinstance(entry.value, BoolValue) and entry.value.value
