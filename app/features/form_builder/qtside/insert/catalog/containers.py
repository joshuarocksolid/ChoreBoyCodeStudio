"""UX-CAT-002: Containers and pages (UX-CONT-001: titles where the container stores them)."""

from __future__ import annotations

from typing import Callable, Tuple

from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec
from app.features.form_builder.qtside.insert.catalog._build import (
    attr,
    container,
    layout_with_margins,
    enum,
    fragment,
    flag,
    page,
    text,
    widget,
)
from app.features.form_builder.qtside.insert.catalog._model import WIDGET, Entry, Registry

CATEGORY = "Containers"
_SYNONYMS = ("panel", "box", "group", "fieldset", "container")
_PAGE_SYNONYMS = ("tabs", "notebook", "pages")


def _group_box() -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(container("QGroupBox", "groupBox", properties=(text("title", "Group box"),)))

    return build


def _frame() -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(
            container(
                "QFrame",
                "frame",
                properties=(
                    enum("frameShape", "QFrame::StyledPanel"),
                    enum("frameShadow", "QFrame::Raised"),
                ),
            )
        )

    return build


def _plain_widget() -> Callable[[], Fragment]:
    def build() -> Fragment:
        # Qt's default margins, written out: an unwritten margin loads as 0 in our generator (see the M4.2 repro).
        return fragment(widget("QWidget", "widget", layout_spec=layout_with_margins("QVBoxLayout", "verticalLayout", 9)))

    return build


def _pages(
    container_class: str,
    container_name: str,
    pages: Tuple[NodeSpec, ...],
) -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(widget(container_class, container_name, children=pages))

    return build


def _tab_pages() -> Tuple[NodeSpec, ...]:
    return (
        page("QWidget", "tab", attributes=(attr("title", "Tab 1"),)),
        page("QWidget", "tab_2", attributes=(attr("title", "Tab 2"),)),
    )


def _toolbox_pages() -> Tuple[NodeSpec, ...]:
    return (
        page("QWidget", "page", attributes=(attr("label", "Page 1"),)),
        page("QWidget", "page_2", attributes=(attr("label", "Page 2"),)),
    )


def _stacked_pages() -> Tuple[NodeSpec, ...]:
    return (page("QWidget", "page"), page("QWidget", "page_2"))


def _scroll_area() -> Callable[[], Fragment]:
    def build() -> Fragment:
        contents = container("QWidget", "scrollAreaWidgetContents")
        return fragment(
            widget(
                "QScrollArea",
                "scrollArea",
                properties=(flag("widgetResizable", True),),
                children=(contents,),
            )
        )

    return build


def _wizard() -> Callable[[], Fragment]:
    def build() -> Fragment:
        pages = (
            page("QWizardPage", "wizardPage", properties=(text("title", "Step 1"),)),
            page("QWizardPage", "wizardPage_2", properties=(text("title", "Step 2"),)),
        )
        return fragment(widget("QWizard", "wizard", children=pages))

    return build


def _wizard_page() -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(page("QWizardPage", "wizardPage", properties=(text("title", "Step 1"),)))

    return build


def _mdi_area() -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(widget("QMdiArea", "mdiArea"))

    return build


def _dock_widget() -> Callable[[], Fragment]:
    def build() -> Fragment:
        return fragment(widget("QDockWidget", "dockWidget", children=(container("QWidget", "dockWidgetContents"),)))

    return build


def entries() -> Tuple[Entry, ...]:
    return (
        Entry("QGroupBox", "Group box", "QGroupBox", CATEGORY, "groupBox",
              "A titled frame around related widgets.", _SYNONYMS, "group_box", WIDGET, _group_box()),
        Entry("QFrame", "Frame", "QFrame", CATEGORY, "frame",
              "A plain border around a group of widgets.", _SYNONYMS, "frame", WIDGET, _frame()),
        Entry("QWidget", "Widget", "QWidget", CATEGORY, "widget",
              "An empty area that holds a layout.", _SYNONYMS, "widget", WIDGET, _plain_widget()),
        Entry("QTabWidget", "Tab widget", "QTabWidget", CATEGORY, "tabWidget",
              "Pages the user switches with tabs.", _PAGE_SYNONYMS, "tab_widget", WIDGET,
              _pages("QTabWidget", "tabWidget", _tab_pages())),
        Entry("QToolBox", "Toolbox", "QToolBox", CATEGORY, "toolBox",
              "Pages stacked like drawers; one is open at a time.", _PAGE_SYNONYMS + ("drawers",),
              "toolbox", WIDGET, _pages("QToolBox", "toolBox", _toolbox_pages())),
        Entry("QStackedWidget", "Stacked widget", "QStackedWidget", CATEGORY, "stackedWidget",
              "Pages your code switches; one shows at a time.", ("tabs", "pages", "stack"),
              "stacked_widget", WIDGET, _pages("QStackedWidget", "stackedWidget", _stacked_pages())),
        Entry("QScrollArea", "Scroll area", "QScrollArea", CATEGORY, "scrollArea",
              "Scrolls content that is bigger than the space.", ("scroll",), "scroll_area",
              WIDGET, _scroll_area()),
        Entry("QWizard", "Wizard", "QWizard", CATEGORY, "wizard",
              "Steps with Back and Next buttons.", ("wizard", "steps", "assistant"), "wizard",
              WIDGET, _wizard()),
        Entry("QWizardPage", "Wizard page", "QWizardPage", CATEGORY, "wizardPage",
              "One step of a wizard. Goes only into a wizard.", ("steps", "step"), "wizard_page",
              WIDGET, _wizard_page()),
        Entry("QMdiArea", "MDI area", "QMdiArea", CATEGORY, "mdiArea",
              "Several small windows inside one area.", ("mdi", "windows"), "mdi_area",
              WIDGET, _mdi_area()),
        Entry("QDockWidget", "Dock widget", "QDockWidget", CATEGORY, "dockWidget",
              "A panel that docks to a side of a main window.", ("dock", "side panel", "sidepanel"),
              "dock_widget", WIDGET, _dock_widget()),
    )


def register(registry: Registry) -> None:
    for entry in entries():
        registry.add(entry)
