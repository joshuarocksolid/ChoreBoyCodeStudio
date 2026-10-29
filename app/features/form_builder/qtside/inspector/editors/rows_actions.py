"""Curated rows for the main-window parts (UX-MAIN-013, R3 138, 143).

Menu: title, tear-off and tooltips. Menu bar: native menu bar. Toolbar: side,
new row, button style, can move, can float. Status bar: size grip and a caption.
Action rows (UX-MAIN-012) need the inspector to accept an action as an owner;
that lives in ``inspector/model.py``, which this lane does not own.
"""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import EnumValue
from app.features.form_builder.qtside.inspector.api import Choice, GroupId, Note, Prop, Registrar, RowSpec

STATUS_BAR_CAPTION = (
    "Status tips of actions and widgets show here while the pointer is on them. "
    "Your code can show other messages."
)
_CONTENT = GroupId.CONTENT


def _sides(_document: UiDocument, _owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    return tuple(
        Choice(label, EnumValue("Qt::%sToolBarArea" % label)) for label in ("Top", "Bottom", "Left", "Right")
    )


def _button_styles(_document: UiDocument, _owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    return (
        Choice("Icon only", EnumValue("Qt::ToolButtonIconOnly")),
        Choice("Text only", EnumValue("Qt::ToolButtonTextOnly")),
        Choice("Text beside icon", EnumValue("Qt::ToolButtonTextBesideIcon")),
        Choice("Text under icon", EnumValue("Qt::ToolButtonTextUnderIcon")),
    )


def register(registrar: Registrar) -> None:
    rows = (
        RowSpec("menuTitle", _CONTENT, "Title", "The menu's title. Put & before a letter to open it with Alt and that letter.", Prop("title"), classes=("QMenu",)),
        RowSpec("menuIcon", _CONTENT, "Icon", "A picture beside the menu's title in a submenu.", Prop("icon"), classes=("QMenu",)),
        RowSpec("tearOff", _CONTENT, "Tear-off", "A dashed line at the top lets the user drag the menu out as a small window.", Prop("tearOffEnabled"), classes=("QMenu",)),
        RowSpec("menuTips", _CONTENT, "Shows tooltips", "Entries show their tooltip while the pointer rests on them.", Prop("toolTipsVisible"), classes=("QMenu",)),
        RowSpec("nativeMenuBar", _CONTENT, "Native menu bar", "Only matters on macOS.", Prop("nativeMenuBar"), classes=("QMenuBar",)),
        RowSpec(
            "toolbarSide",
            _CONTENT,
            "Toolbar side",
            "Which edge of the window the toolbar starts on.",
            Prop("toolBarArea", "attribute"),
            classes=("QToolBar",),
            choices=_sides,
        ),
        RowSpec("toolbarBreak", _CONTENT, "Starts on a new row", "The toolbar starts a new row on its side.", Prop("toolBarBreak", "attribute"), classes=("QToolBar",)),
        RowSpec(
            "toolbarStyle",
            _CONTENT,
            "Button style",
            "Whether the buttons show an icon, text, or both.",
            Prop("toolButtonStyle"),
            classes=("QToolBar",),
            choices=_button_styles,
        ),
        RowSpec("toolbarMovable", _CONTENT, "Can move", "The user can drag the toolbar to another place.", Prop("movable"), classes=("QToolBar",)),
        RowSpec("toolbarFloatable", _CONTENT, "Can float", "The user can drag the toolbar out of the window.", Prop("floatable"), classes=("QToolBar",)),
        RowSpec("sizeGrip", _CONTENT, "Size grip", "A small grip at the right end that resizes the window.", Prop("sizeGripEnabled"), classes=("QStatusBar",)),
        RowSpec("statusBarCaption", _CONTENT, "Messages", STATUS_BAR_CAPTION, Note(STATUS_BAR_CAPTION), classes=("QStatusBar",)),
    )
    for spec in rows:
        registrar.row(spec, baseline=True)
