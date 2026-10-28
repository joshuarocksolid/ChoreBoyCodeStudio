"""Curated rows for containers (UX-CONT-010, 012, 013, 014, 015, 018).

Rows only. A page attribute or the dock side names its parent class, so a
plain widget does not show it. Dock side's four-segment editor is registered
separately. The row still binds through the property's own value editor until
the inspector can pick an editor key per row.
"""

from __future__ import annotations

from app.features.form_builder.qtside.inspector.api import GroupId, Prop, Registrar, RowSpec

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
            "frameShadow",
            _APPEARANCE,
            "Shadow",
            "The edge look: plain, raised or sunken.",
            Prop("frameShadow"),
            classes=("QFrame",),
        ),
        RowSpec(
            "lineWidth",
            _APPEARANCE,
            "Line width",
            "The width of the frame's edge, in pixels.",
            Prop("lineWidth"),
            classes=("QFrame",),
        ),
        RowSpec(
            "midLineWidth",
            _APPEARANCE,
            "Middle line width",
            "The width of the line in the middle of a raised or sunken edge.",
            Prop("midLineWidth"),
            classes=("QFrame",),
        ),
        RowSpec(
            "dockSide",
            _PLACEMENT,
            "Dock side",
            "Which edge of the main window this dock sits on.",
            Prop("dockWidgetArea", "attribute"),
            classes=("QDockWidget",),
            parent_classes=("QMainWindow",),
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
