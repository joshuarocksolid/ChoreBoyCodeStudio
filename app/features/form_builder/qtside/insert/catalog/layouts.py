"""UX-CAT-002: Layouts and spacers."""

from __future__ import annotations

from typing import Callable, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.insert.catalog._build import (
    fragment,
    layout,
    orientation,
    spacer,
    widget,
)
from app.features.form_builder.qtside.insert.catalog._model import (
    SPACER,
    WIDGET,
    Entry,
    Registry,
)

CATEGORY = "Layouts and spacers"


def _layout_widget(container: str, layout_class: str, layout_name: str) -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(widget("QWidget", container, layout_spec=layout(layout_class, layout_name)))

    return build


def _splitter(horizontal: bool) -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(widget("QSplitter", "splitter", properties=(orientation(horizontal),)))

    return build


def _spacer(horizontal: bool) -> Callable[[], Fragment]:
    name = "horizontalSpacer" if horizontal else "verticalSpacer"

    def build() -> Fragment:
        return fragment(spacer(name, horizontal))

    return build


def _entries() -> Tuple[Entry, ...]:
    return (
        Entry(
            "layout-v", "Vertical layout", "QVBoxLayout", CATEGORY, "verticalLayoutWidget",
            "Stacks widgets from top to bottom.", ("vbox", "vertical box"), "layout_v",
            WIDGET, _layout_widget("verticalLayoutWidget", "QVBoxLayout", "verticalLayout"),
        ),
        Entry(
            "layout-h", "Horizontal layout", "QHBoxLayout", CATEGORY, "horizontalLayoutWidget",
            "Puts widgets side by side.", ("hbox", "horizontal box"), "layout_h",
            WIDGET, _layout_widget("horizontalLayoutWidget", "QHBoxLayout", "horizontalLayout"),
        ),
        Entry(
            "layout-grid", "Grid layout", "QGridLayout", CATEGORY, "gridLayoutWidget",
            "Rows and columns, like a table.", ("gridbox",), "layout_grid",
            WIDGET, _layout_widget("gridLayoutWidget", "QGridLayout", "gridLayout"),
        ),
        Entry(
            "layout-form", "Form layout", "QFormLayout", CATEGORY, "formLayoutWidget",
            "Labels on the left, fields on the right.", ("form", "labels"), "layout_form",
            WIDGET, _layout_widget("formLayoutWidget", "QFormLayout", "formLayout"),
        ),
        Entry(
            "splitter-h", "Horizontal splitter", "QSplitter", CATEGORY, "splitter",
            "Side-by-side panes the user can resize.", ("split", "splitter", "resizable panes"),
            "splitter_h", WIDGET, _splitter(True),
        ),
        Entry(
            "splitter-v", "Vertical splitter", "QSplitter", CATEGORY, "splitter",
            "Stacked panes the user can resize.", ("split", "splitter", "resizable panes"),
            "splitter_v", WIDGET, _splitter(False),
        ),
        Entry(
            "spacer-h", "Horizontal spacer", "spacer", CATEGORY, "horizontalSpacer",
            "Empty space that pushes its neighbours apart.",
            ("space", "gap", "stretch", "spring", "spacer"), "spacer_h", SPACER, _spacer(True),
        ),
        Entry(
            "spacer-v", "Vertical spacer", "spacer", CATEGORY, "verticalSpacer",
            "Empty space that pushes its neighbours up or down.",
            ("space", "gap", "stretch", "spring", "spacer"), "spacer_v", SPACER, _spacer(False),
        ),
    )


def register(registry: Registry) -> None:
    registry.family("spacer", "Spacer")
    registry.family("QSplitter", "Splitter")
    for entry in _entries():
        registry.add(entry)
