"""The property names Qt's style sheet parser knows (UX-STYLE-004). Qt-free.

The list comes from the Qt style sheet reference and from asking Qt itself
about every name (``tests/form_builder/qtside/test_m5_3_style_check.py`` keeps
the two in step). A name outside the list is a warning, never an error: Qt
skips the line and applies the rest.
"""

from __future__ import annotations

from typing import FrozenSet

_SIDES = ("top", "right", "bottom", "left")
_CORNERS = ("top-left", "top-right", "bottom-right", "bottom-left")


def _build() -> FrozenSet[str]:
    names = {
        "alternate-background-color",
        "background",
        "background-color",
        "background-image",
        "background-repeat",
        "background-position",
        "background-attachment",
        "background-clip",
        "background-origin",
        "border",
        "border-color",
        "border-image",
        "border-radius",
        "border-style",
        "border-width",
        "border-collapse",
        "bottom",
        "button-layout",
        "color",
        "dialogbuttonbox-buttons-have-icons",
        "float",
        "font",
        "font-family",
        "font-kerning",
        "font-size",
        "font-style",
        "font-variant",
        "font-weight",
        "gridline-color",
        "height",
        "icon",
        "icon-size",
        "image",
        "image-position",
        "left",
        "letter-spacing",
        "line-height",
        "lineedit-password-character",
        "lineedit-password-mask-delay",
        "list-style",
        "list-style-type",
        "margin",
        "max-height",
        "max-width",
        "messagebox-text-interaction-flags",
        "min-height",
        "min-width",
        "opacity",
        "outline",
        "outline-color",
        "outline-offset",
        "outline-style",
        "outline-radius",
        "padding",
        "page-break-after",
        "page-break-before",
        "paint-alternating-row-colors-for-empty-area",
        "placeholder-text-color",
        "position",
        "right",
        "selection-background-color",
        "selection-color",
        "show-decoration-selected",
        "spacing",
        "subcontrol-origin",
        "subcontrol-position",
        "text-align",
        "text-decoration",
        "text-indent",
        "text-transform",
        "text-underline-style",
        "titlebar-show-tooltips-on-buttons",
        "top",
        "vertical-align",
        "white-space",
        "widget-animation-duration",
        "width",
        "word-spacing",
        "-qt-background-role",
        "-qt-block-indent",
        "-qt-line-height-type",
        "-qt-list-indent",
        "-qt-list-number-prefix",
        "-qt-list-number-suffix",
        "-qt-paragraph-type",
        "-qt-style-features",
        "-qt-table-type",
        "-qt-user-state",
    }
    for side in _SIDES:
        for stem in ("border", "margin", "padding"):
            names.add("%s-%s" % (stem, side))
        names.add("border-%s-color" % side)
        names.add("border-%s-style" % side)
        names.add("border-%s-width" % side)
    for corner in _CORNERS:
        names.add("border-%s-radius" % corner)
        names.add("outline-%s-radius" % corner)
    return frozenset(names)


KNOWN_PROPERTIES: FrozenSet[str] = _build()

#: Prefix of ``qproperty-<name>``, which sets a Qt property from the style sheet.
QPROPERTY_PREFIX = "qproperty-"


def is_known_property(name: str) -> bool:
    lowered = name.lower()
    return lowered in KNOWN_PROPERTIES or (lowered.startswith(QPROPERTY_PREFIX) and len(lowered) > len(QPROPERTY_PREFIX))


#: Qt 5's pseudo-states (``qcssparser.cpp``). A selector with any other state
#: matches nothing in Qt, with or without ``!`` (checked by pixels under Fusion).
KNOWN_STATES: FrozenSet[str] = frozenset(
    (
        "active adjoins-item alternate bottom checked closable closed default disabled edit-focus editable "
        "enabled exclusive first flat floatable focus has-children has-siblings horizontal hover indeterminate "
        "last left maximized middle minimized movable next-selected no-frame non-exclusive off on only-one open "
        "pressed previous-selected read-only right selected top unchecked vertical window"
    ).split()
)


def is_known_state(state: str) -> bool:
    """``state`` without or with its ``!``."""
    return state.lstrip("!").lower() in KNOWN_STATES
