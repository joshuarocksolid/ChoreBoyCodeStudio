"""Curated rows for containers (UX-CONT-010, 012, 013, 014, 015, 018).

A page attribute or the dock side names its parent class, so a plain widget
does not show it. Dock side names the four-segment editor. Starts on is a
drop-down of the container's page titles. A dock outside a main window gets
the Placement caption instead of Dock side.
"""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.pages import page_title, pages
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import BoolValue, NumberValue, SetValue
from app.features.form_builder.qtside.inspector.api import (
    Choice,
    FlagBit,
    GroupId,
    Note,
    Prop,
    Registrar,
    RowSpec,
)

DOCK_PANEL_CAPTION = "Docks only in a main window. In this form it shows as a panel."

_CONTENT = GroupId.CONTENT
_APPEARANCE = GroupId.APPEARANCE
_PLACEMENT = GroupId.PLACEMENT


def register(registrar: Registrar) -> None:
    rows = (
        RowSpec(
            "widgetResizable",
            _CONTENT,
            "Content follows the area's size",
            "On: the content stretches to fill the area and scrolls only when it can't shrink further. "
            "Off: the content keeps its own size.",
            Prop("widgetResizable"),
            classes=("QScrollArea",),
        ),
        RowSpec(
            "horizontalScrollBarPolicy",
            _CONTENT,
            "Horizontal",
            "Scroll bars along the bottom: as needed, always, or never.",
            Prop("horizontalScrollBarPolicy"),
            classes=("QScrollArea",),
        ),
        RowSpec(
            "verticalScrollBarPolicy",
            _CONTENT,
            "Vertical",
            "Scroll bars along the side: as needed, always, or never.",
            Prop("verticalScrollBarPolicy"),
            classes=("QScrollArea",),
        ),
        RowSpec(
            "stepTitle",
            _CONTENT,
            "Step title",
            "The heading of this wizard step.",
            Prop("title"),
            classes=("QWizardPage",),
        ),
        RowSpec(
            "stepSubtitle",
            _CONTENT,
            "Step subtitle",
            "The line under the heading of this wizard step.",
            Prop("subTitle"),
            classes=("QWizardPage",),
        ),
        RowSpec(
            "checkable",
            _CONTENT,
            "Can be switched off",
            "Adds a check box to the title. Unchecking it turns off everything inside.",
            Prop("checkable"),
            classes=("QGroupBox",),
        ),
        RowSpec(
            "startsChecked",
            _CONTENT,
            "Starts switched on",
            "The box starts checked. Unchecking it at run time turns off everything inside.",
            Prop("checked"),
            classes=("QGroupBox",),
            visible=_group_starts_on,
            after="checkable",
        ),
        RowSpec(
            "titleAlignment",
            _APPEARANCE,
            "Title alignment",
            "Where the title sits on the box's border.",
            Prop("alignment"),
            classes=("QGroupBox",),
            choices=_title_alignments,
        ),
        RowSpec(
            "orientation",
            _APPEARANCE,
            "Orientation",
            "The line runs across or down. The frame shape follows it.",
            Prop("orientation"),
            classes=("Line",),
        ),
        RowSpec(
            "frameShadow",
            _APPEARANCE,
            "Shadow",
            "The edge look: plain, raised or sunken.",
            Prop("frameShadow"),
            classes=("QFrame", "Line"),
        ),
        RowSpec(
            "lineWidth",
            _APPEARANCE,
            "Line width",
            "The width of the frame's edge, in pixels.",
            Prop("lineWidth"),
            classes=("QFrame",),
            exclude_classes=("Line",),
        ),
        RowSpec(
            "midLineWidth",
            _APPEARANCE,
            "Middle line width",
            "The width of the line in the middle of a raised or sunken edge.",
            Prop("midLineWidth"),
            classes=("QFrame",),
            exclude_classes=("Line",),
        ),
        RowSpec(
            "dockSide",
            _PLACEMENT,
            "Dock side",
            "Which edge of the main window this dock sits on.",
            Prop("dockWidgetArea", "attribute"),
            classes=("QDockWidget",),
            parent_classes=("QMainWindow",),
            editor="dock_side",
        ),
        RowSpec(
            "dockPanel",
            _PLACEMENT,
            "Panel",
            DOCK_PANEL_CAPTION,
            Note(DOCK_PANEL_CAPTION),
            classes=("QDockWidget",),
            visible=_dock_is_a_panel,
        ),
        RowSpec(
            "canClose",
            _CONTENT,
            "Can close",
            "The user can close this dock.",
            FlagBit("features", "QDockWidget::DockWidgetClosable"),
            classes=("QDockWidget",),
        ),
        RowSpec(
            "canFloat",
            _CONTENT,
            "Can float",
            "The user can drag this dock out of the window.",
            FlagBit("features", "QDockWidget::DockWidgetFloatable"),
            classes=("QDockWidget",),
        ),
        RowSpec(
            "canMove",
            _CONTENT,
            "Can move",
            "The user can drag this dock to another side.",
            FlagBit("features", "QDockWidget::DockWidgetMovable"),
            classes=("QDockWidget",),
        ),
        RowSpec(
            "allowedAreas",
            _CONTENT,
            "Allowed sides",
            "The sides this dock may be moved to.",
            Prop("allowedAreas"),
            classes=("QDockWidget",),
        ),
        RowSpec(
            "startsOn",
            _CONTENT,
            "Starts on",
            "The page the form opens on. Switching pages on the canvas does not change this.",
            Prop("currentIndex"),
            classes=("QTabWidget", "QToolBox", "QStackedWidget"),
            choices=_start_page_choices,
        ),
        RowSpec(
            "tabTitle",
            _CONTENT,
            "Tab title",
            "The text on this tab.",
            Prop("title", "attribute"),
            parent_classes=("QTabWidget",),
        ),
        RowSpec(
            "tabTooltip",
            _CONTENT,
            "Tab tooltip",
            "Shown when the pointer rests on this tab.",
            Prop("toolTip", "attribute"),
            parent_classes=("QTabWidget",),
        ),
        RowSpec(
            "tabHelp",
            _CONTENT,
            "Tab help",
            "Help text for this tab.",
            Prop("whatsThis", "attribute"),
            parent_classes=("QTabWidget",),
        ),
        RowSpec(
            "pageLabel",
            _CONTENT,
            "Page label",
            "The text on this toolbox page.",
            Prop("label", "attribute"),
            parent_classes=("QToolBox",),
        ),
        RowSpec(
            "pageTooltip",
            _CONTENT,
            "Page tooltip",
            "Shown when the pointer rests on this toolbox page.",
            Prop("toolTip", "attribute"),
            parent_classes=("QToolBox",),
        ),
    )
    for spec in rows:
        registrar.row(spec, baseline=True)


def _group_starts_on(document: UiDocument, owners: Tuple[NodeId, ...]) -> bool:
    """Starts switched on is shown only while Can be switched off is on."""
    for owner in owners:
        node = document.node(owner)
        if not isinstance(node, WidgetNode):
            return False
        entry = node.prop("checkable")
        if entry is None or not isinstance(entry.value, BoolValue) or not entry.value.value:
            return False
    return bool(owners)


def _title_alignments(_document: UiDocument, _owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    return (
        Choice("Left", SetValue("Qt::AlignLeft")),
        Choice("Centre", SetValue("Qt::AlignHCenter")),
        Choice("Right", SetValue("Qt::AlignRight")),
    )


def _start_page_choices(document: UiDocument, owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    """Page titles in order. A stacked page uses its object name."""
    if len(owners) != 1:
        return ()
    found = pages(document, owners[0])
    choices = []
    for index, page in enumerate(found):
        title = page_title(document, page.id) or page.object_name or "Page %d" % (index + 1)
        choices.append(Choice(title, NumberValue(index)))
    return tuple(choices)


def _dock_is_a_panel(document: UiDocument, owners: Tuple[NodeId, ...]) -> bool:
    """A dock whose form is not a main window is a panel (UX-CONT-012)."""
    if len(owners) != 1:
        return False
    node = document.node(owners[0])
    if not isinstance(node, WidgetNode) or node.class_name != "QDockWidget":
        return False
    current = document.parent(owners[0])
    while current is not None:
        if isinstance(current, WidgetNode) and current.class_name == "QMainWindow":
            return False
        current = document.parent(current.id)
    return True


