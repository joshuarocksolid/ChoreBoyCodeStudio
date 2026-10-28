"""UX-CAT-002 FreeCAD category.

Base classes and headers come from FreeCAD's own ``.ui`` files on the development
Mac (``/Applications/FreeCAD.app/Contents/Resources/Mod``), counted there:
QuantitySpinBox 18 files, InputField 6, FileChooser 2, IntSpinBox 2, DoubleSpinBox 2.
ColorButton and UrlLabel appear in no ``.ui`` file in that install. Their base
classes (QPushButton and QLabel) and the header ``Gui/Widgets.h`` were checked
on FreeCAD 1.1.3.
"""

from __future__ import annotations

from typing import Callable, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.insert.catalog._build import declaration, fragment, widget
from app.features.form_builder.qtside.insert.catalog._model import WIDGET, Entry, Registry

CATEGORY = "FreeCAD"
_NEEDS_FREECAD = "Needs FreeCAD's window at run time."

# (friendly, class, object name, base class, header, verified in a .ui file, synonyms, glyph, sentence)
_FACTS: Tuple[Tuple[str, str, str, str, str, bool, Tuple[str, ...], str, str], ...] = (
    ("Quantity spin box", "Gui::QuantitySpinBox", "quantitySpinBox", "QWidget",
     "Gui/QuantitySpinBox.h", True, ("quantity", "unit", "length"), "fc_quantity",
     "A number with a unit, such as 5 mm. " + _NEEDS_FREECAD),
    ("Input field", "Gui::InputField", "inputField", "QLineEdit",
     "Gui/InputField.h", True, ("formula", "expression"), "fc_input",
     "A text field that reads units and expressions. " + _NEEDS_FREECAD),
    ("File chooser", "Gui::FileChooser", "fileChooser", "QWidget",
     "Gui/FileDialog.h", True, ("file", "path", "browse", "folder"), "fc_file",
     "A path with a Browse button. " + _NEEDS_FREECAD),
    ("Color button", "Gui::ColorButton", "colorButton", "QPushButton",
     "Gui/Widgets.h", True, ("colour", "color", "swatch"), "fc_color",
     "A button that shows and picks a colour. " + _NEEDS_FREECAD),
    ("URL label", "Gui::UrlLabel", "urlLabel", "QLabel",
     "Gui/Widgets.h", True, ("url", "link"), "fc_url",
     "A label with a link that opens in a browser. " + _NEEDS_FREECAD),
    ("Integer spin box", "Gui::IntSpinBox", "intSpinBox", "QWidget",
     "Gui/SpinBox.h", True, ("integer", "whole number"), "fc_int",
     "A whole number with a unit. " + _NEEDS_FREECAD),
    ("Double spin box (FreeCAD)", "Gui::DoubleSpinBox", "doubleSpinBox", "QWidget",
     "Gui/SpinBox.h", True, ("decimal", "float"), "fc_double",
     "A number with decimals and an optional unit. " + _NEEDS_FREECAD),
)


def _builder(qt_class: str, object_name: str, base: str, header: str) -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(
            widget(qt_class, object_name),
            customwidgets=(declaration(qt_class, base, header),),
        )

    return build


def entries() -> Tuple[Entry, ...]:
    found = []
    for friendly, qt_class, object_name, base, header, _verified, synonyms, glyph, sentence in _FACTS:
        found.append(
            Entry(
                qt_class, friendly, qt_class, CATEGORY, object_name, sentence, synonyms, glyph,
                WIDGET, _builder(qt_class, object_name, base, header),
                base_class=base, header=header, freecad=True,
            )
        )
    return tuple(found)


def verified_facts() -> Tuple[str, ...]:
    """Classes whose base and header were read from a FreeCAD ``.ui`` file."""
    return tuple(item[1] for item in _FACTS if item[5])


def register(registry: Registry) -> None:
    for entry in entries():
        registry.add(entry)
