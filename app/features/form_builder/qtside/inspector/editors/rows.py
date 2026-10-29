
from __future__ import annotations

from typing import Tuple

from app.features.form_builder.qtside.inspector.api import (
    CellAlignment,
    GroupId,
    LayoutProp,
    Prop,
    Registrar,
    RowSpec,
)

_CONTENT = GroupId.CONTENT
_INPUT = GroupId.INPUT
_APPEARANCE = GroupId.APPEARANCE
_SIZE = GroupId.SIZE
_PLACEMENT = GroupId.PLACEMENT
_LAYOUT = GroupId.LAYOUT
_ACCESS = GroupId.ACCESSIBILITY

_ROWS: Tuple[RowSpec, ...] = (
    RowSpec("text", _CONTENT, "Text", "The words the widget shows.", Prop("text")),
    RowSpec("plainText", _CONTENT, "Text", "The starting text in the box.", Prop("plainText")),
    RowSpec(
        "placeholderText",
        _CONTENT,
        "Placeholder",
        "Faint text shown while the field is empty.",
        Prop("placeholderText"),
    ),
    # A menu has its own Title row (rows_actions.py); two would list it twice.
    RowSpec("title", _CONTENT, "Title", "The caption on the box's border.", Prop("title"), exclude_classes=("QMenu",)),
    RowSpec(
        "checked",
        _CONTENT,
        "Checked",
        "Whether it starts checked.",
        Prop("checked"),
        exclude_classes=("QGroupBox",),
    ),
    RowSpec(
        "pixmap",
        _CONTENT,
        "Picture",
        "A picture the label shows instead of text.",
        Prop("pixmap"),
        classes=("QLabel",),
    ),
    RowSpec("toolTip", _CONTENT, "Tooltip", "Shown when the pointer rests on it.", Prop("toolTip")),
    RowSpec("echoMode", _INPUT, "Echo mode", "Show, hide or mask what the user types.", Prop("echoMode")),
    RowSpec("maxLength", _INPUT, "Maximum length", "The most characters the user can type.", Prop("maxLength")),
    RowSpec("inputMask", _INPUT, "Input mask", "A pattern the typed text must follow.", Prop("inputMask")),
    RowSpec("readOnly", _INPUT, "Read only", "The user can see the value but not change it.", Prop("readOnly")),
    RowSpec("minimum", _INPUT, "Minimum", "The smallest value allowed.", Prop("minimum")),
    RowSpec("maximum", _INPUT, "Maximum", "The largest value allowed.", Prop("maximum")),
    RowSpec("singleStep", _INPUT, "Step", "How much one arrow press changes the value.", Prop("singleStep")),
    RowSpec("value", _INPUT, "Value", "The starting value.", Prop("value")),
    RowSpec("decimals", _INPUT, "Decimals", "Digits after the decimal point.", Prop("decimals")),
    RowSpec(
        "editable",
        _INPUT,
        "Typing allowed",
        "The user can type a value that is not in the list.",
        Prop("editable"),
    ),
    RowSpec("font", _APPEARANCE, "Font", "Family, size and style of the text.", Prop("font")),
    RowSpec(
        "alignment",
        _APPEARANCE,
        "Text alignment",
        "Where the text sits inside the widget.",
        Prop("alignment"),
        exclude_classes=("QGroupBox",),
    ),
    RowSpec("wordWrap", _APPEARANCE, "Wrap words", "Long text continues on the next line.", Prop("wordWrap")),
    RowSpec(
        "frameShape",
        _APPEARANCE,
        "Frame",
        "The border drawn around the widget.",
        Prop("frameShape"),
        exclude_classes=("Line",),
    ),
    RowSpec("flat", _APPEARANCE, "Flat", "Draw without a raised border.", Prop("flat")),
    RowSpec("textFormat", _APPEARANCE, "Text format", "Plain text, rich text, or detect it.", Prop("textFormat")),
    RowSpec("minimumSize", _SIZE, "Minimum size", "The widget never gets smaller than this.", Prop("minimumSize")),
    RowSpec("maximumSize", _SIZE, "Maximum size", "The widget never gets larger than this.", Prop("maximumSize")),
    RowSpec("sizePolicy", _SIZE, "Size policy", "How the widget grows and shrinks in a layout.", Prop("sizePolicy")),
    RowSpec("geometry", _PLACEMENT, "Position and size", "X, Y, width and height on the page.", Prop("geometry")),
    RowSpec("cell.alignment", _PLACEMENT, "Alignment in cell", "Where the widget sits in its layout cell.", CellAlignment()),
    RowSpec("layout.spacing", _LAYOUT, "Spacing", "Space between the items inside.", LayoutProp("spacing")),
    RowSpec("layout.leftMargin", _LAYOUT, "Left margin", "Space inside the left edge.", LayoutProp("leftMargin")),
    RowSpec("layout.topMargin", _LAYOUT, "Top margin", "Space inside the top edge.", LayoutProp("topMargin")),
    RowSpec("layout.rightMargin", _LAYOUT, "Right margin", "Space inside the right edge.", LayoutProp("rightMargin")),
    RowSpec("layout.bottomMargin", _LAYOUT, "Bottom margin", "Space inside the bottom edge.", LayoutProp("bottomMargin")),
    RowSpec(
        "layout.horizontalSpacing",
        _LAYOUT,
        "Column spacing",
        "Space between columns.",
        LayoutProp("horizontalSpacing"),
    ),
    RowSpec("layout.verticalSpacing", _LAYOUT, "Row spacing", "Space between rows.", LayoutProp("verticalSpacing")),
    RowSpec(
        "accessibleName",
        _ACCESS,
        "Accessible name",
        "What a screen reader says for this widget.",
        Prop("accessibleName"),
    ),
    RowSpec(
        "accessibleDescription",
        _ACCESS,
        "Accessible description",
        "A longer description for a screen reader.",
        Prop("accessibleDescription"),
    ),
    RowSpec("statusTip", _ACCESS, "Status tip", "Shown in the status bar when the pointer rests on it.", Prop("statusTip")),
    RowSpec("whatsThis", _ACCESS, "What's this", "Help shown by the What's This tool.", Prop("whatsThis")),
)

def register(registrar: Registrar) -> None:
    for spec in _ROWS:
        registrar.row(spec, baseline=True)
