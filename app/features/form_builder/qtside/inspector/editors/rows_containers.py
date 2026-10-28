"""Curated rows for containers: scroll areas, wizard steps, group boxes and frames (UX-CONT-010, 013, 014, 015).

Rows only. Each row names a property the Qt class has; the value editors are
the generic ones. The dock side control, "Starts on" and the page attribute
rows need an editor or a parent scope that the registry does not have yet:
see the M4.2 report.
"""

from __future__ import annotations

from app.features.form_builder.qtside.inspector.api import GroupId, Prop, Registrar, RowSpec

_CONTENT = GroupId.CONTENT
_APPEARANCE = GroupId.APPEARANCE


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
    )
    for spec in rows:
        registrar.row(spec, baseline=True)
