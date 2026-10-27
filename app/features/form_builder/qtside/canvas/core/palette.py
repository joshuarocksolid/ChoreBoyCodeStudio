"""The widgets a drop can insert before the full catalog exists.

M4.1 owns ``qtside/insert/catalog/``. This list lives in canvas core so the
gesture can build a fragment without importing Qt. ``qtside/insert/tiles.py``
re-exports it.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.query.drop_target import PayloadKind
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import EnumValue, SizeValue, StringValue

MIME_INSERT = "application/x-cbcs-insert"
MIME_NODE = "application/x-cbcs-node"
MIME_FRAGMENT = "application/x-cbcs-form-fragment"
MIME_DESIGNER_FRAGMENT = "application/x-qt-designer-ui-fragment"

Tile = Tuple[str, PayloadKind, str]

TILES: Tuple[Tile, ...] = (
    ("QLabel", "label", "Label"),
    ("QPushButton", "widget", "Button"),
    ("QLineEdit", "widget", "Line edit"),
    ("QCheckBox", "widget", "Check box"),
    ("QComboBox", "widget", "Combo box"),
    ("QSpinBox", "widget", "Spin box"),
    ("QGroupBox", "widget", "Group box"),
    ("layout-v", "widget", "Vertical layout"),
    ("layout-h", "widget", "Horizontal layout"),
    ("layout-grid", "widget", "Grid layout"),
    ("layout-form", "widget", "Form layout"),
    ("spacer-h", "spacer", "Horizontal spacer"),
    ("spacer-v", "spacer", "Vertical spacer"),
)

# Designer's Layouts category drops a plain widget that already owns the layout.
_LAYOUT_WIDGETS = {
    "layout-v": ("QVBoxLayout", "verticalLayoutWidget", "verticalLayout"),
    "layout-h": ("QHBoxLayout", "horizontalLayoutWidget", "horizontalLayout"),
    "layout-grid": ("QGridLayout", "gridLayoutWidget", "gridLayout"),
    "layout-form": ("QFormLayout", "formLayoutWidget", "formLayout"),
}

_OBJECT_NAMES = {
    "QLabel": "label",
    "QPushButton": "pushButton",
    "QLineEdit": "lineEdit",
    "QCheckBox": "checkBox",
    "QComboBox": "comboBox",
    "QSpinBox": "spinBox",
    "QGroupBox": "groupBox",
}

_TEXT = {
    "QLabel": "Label",
    "QPushButton": "Button",
    "QCheckBox": "Check box",
    "QGroupBox": "Group box",
}


def tile_for(key: str) -> Optional[Tile]:
    for tile in TILES:
        if tile[0] == key:
            return tile
    return None


def matching_tiles(query: str) -> Tuple[Tile, ...]:
    words = query.strip().lower()
    if not words:
        return TILES
    return tuple(tile for tile in TILES if words in tile[2].lower() or words in tile[0].lower())


def fragment_for(key: str) -> Optional[Fragment]:
    tile = tile_for(key)
    if tile is None:
        return None
    class_name, kind, _label = tile
    if key in _LAYOUT_WIDGETS:
        return _layout_widget(key)
    if kind == "spacer":
        vertical = key == "spacer-v"
        name = "verticalSpacer" if vertical else "horizontalSpacer"
        hint = SizeValue(20, 40) if vertical else SizeValue(40, 20)
        orient = "Qt::Vertical" if vertical else "Qt::Horizontal"
        spec = NodeSpec(
            "spacer",
            None,
            (("name", name),),
            (
                PropertyEntry("property", "orientation", EnumValue(orient)),
                PropertyEntry("property", "sizeType", EnumValue("QSizePolicy::Expanding")),
                PropertyEntry("property", "sizeHint", hint, stdset="0"),
            ),
        )
        return Fragment(nodes=(spec,))
    fields = (("class_name", class_name), ("object_name", _OBJECT_NAMES.get(class_name, "widget")))
    text = _TEXT.get(class_name)
    properties = () if text is None else (PropertyEntry("property", "text", StringValue(text)),)
    slots = ()
    if class_name in ("QGroupBox", "QFrame", "QScrollArea", "QWidget"):
        layout = NodeSpec(
            "layout",
            None,
            (("class_name", "QVBoxLayout"), ("object_name", "verticalLayout")),
        )
        slots = (("layout", (layout,)),)
    return Fragment(nodes=(NodeSpec("widget", None, fields, properties, (), slots),))


def _layout_widget(key: str) -> Fragment:
    layout_class, widget_name, layout_name = _LAYOUT_WIDGETS[key]
    layout = NodeSpec("layout", None, (("class_name", layout_class), ("object_name", layout_name)))
    fields = (("class_name", "QWidget"), ("object_name", widget_name))
    return Fragment(nodes=(NodeSpec("widget", None, fields, (), (), (("layout", (layout,)),)),))
