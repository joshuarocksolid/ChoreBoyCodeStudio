"""The Behavior tab: a host for registered sections (UX-BEH-001, M6.0s).

``behavior_ext`` holds the sections. This host owns the order, the colors and
the layout, builds a section's widget the first time it applies, and calls the
optional hooks a section defines (see ``behavior_ext``). The inspector pane
talks to this class only: ``paint``, ``apply_colors``, ``set_refresh``,
``has_draft``, ``discard_draft`` and ``note_focus``.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from app.features.form_builder.qtside.inspector._services import Services
from app.features.form_builder.qtside.inspector.behavior_ext import (
    BehaviorSection,
    SectionHost,
    SectionInputs,
    SectionRegistry,
    default_registry,
)
from app.features.form_builder.qtside.inspector.model import BehaviorView
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtGui import QShowEvent
from app.qt.QtWidgets import QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


def _legacy_section() -> Optional[BehaviorSection]:
    """The M3 list, until M6.1b deletes its file."""
    try:
        from app.features.form_builder.qtside.inspector.behavior_ext import _legacy_connections
    except ImportError:
        return None
    return _legacy_connections.SECTION


class BehaviorPage(QWidget):
    def __init__(
        self,
        services: Services,
        realizer: Realizer,
        parent: QWidget,
        registry: Optional[SectionRegistry] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.behaviorBody")
        self._services = services
        self._realizer = realizer
        self._registry = registry if registry is not None else default_registry()
        self._widgets: Dict[str, QWidget] = {}
        self._failed: Dict[str, bool] = {}
        self._colors: Optional[tuple] = None
        self._refresh: Optional[Callable[[], None]] = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)

    # -------------------------------------------------------------- sections

    def sections(self) -> List[BehaviorSection]:
        """The registered sections in display order, with the M3 list standing in for Events."""
        found = list(self._registry.sections())
        if self._registry.get("events") is None:
            legacy = _legacy_section()
            if legacy is not None and all(section.section_id != legacy.section_id for section in found):
                found.append(legacy)
                found.sort(key=lambda section: (section.order, section.section_id))
        return found

    def section_widget(self, section_id: str) -> Optional[QWidget]:
        return self._widgets.get(section_id)

    def shown_sections(self) -> List[str]:
        return [section_id for section_id, widget in self._widgets.items() if not widget.isHidden()]

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        # Sections stay hidden until this page is the current tab. A click on
        # the tab does not flush by itself, so ask the pane to paint now.
        refresh = self._refresh
        if refresh is not None and self._widgets:
            refresh()

    def paint(self, view: BehaviorView) -> None:
        inputs = SectionInputs(view, self._services, tuple(self._services.session.selection.state.ids))
        position = 0
        for section in self.sections():
            widget = self._widget_for(section, inputs)
            if widget is None:
                continue
            try:
                shown = bool(section.applies(inputs))
            except Exception:
                logger.exception("behavior section %s predicate failed", section.section_id)
                shown = False
            if shown:
                if self._layout.indexOf(widget) != position:
                    self._layout.removeWidget(widget)
                    self._layout.insertWidget(position, widget)
                position += 1
                # Showing a section under a hidden tab clears focus. The
                # canvas timer then takes it. Keep the widget until the page
                # is actually on screen.
                if self.isVisible():
                    widget.show()
                else:
                    widget.hide()
                self._call(section, widget, "paint", inputs)
            else:
                self._layout.removeWidget(widget)
                widget.hide()

    def _widget_for(self, section: BehaviorSection, inputs: SectionInputs) -> Optional[QWidget]:
        found = self._widgets.get(section.section_id)
        if found is not None:
            return found
        if self._failed.get(section.section_id):
            return None
        try:
            if not section.applies(inputs):
                return None
            widget = section.create(SectionHost(self._services, self._realizer, self))
        except Exception:
            logger.exception("behavior section %s could not be built", section.section_id)
            self._failed[section.section_id] = True
            return None
        self._widgets[section.section_id] = widget
        widget.hide()
        refresh = self._refresh
        if refresh is not None:
            self._call(section, widget, "set_refresh", refresh)
        colors = self._colors
        if colors is not None:
            self._call(section, widget, "apply_colors", *colors)
        return widget

    def _call(self, section: BehaviorSection, widget: QWidget, hook: str, *args: object) -> object:
        method = getattr(widget, hook, None)
        if not callable(method):
            return None
        try:
            return method(*args)
        except Exception:
            logger.exception("behavior section %s: %s failed", section.section_id, hook)
            return None

    # ----------------------------------------------------------------- hooks

    def apply_colors(self, panel: str, text: str) -> None:
        self.setStyleSheet(
            "QWidget#formBuilder\\.behaviorBody { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            % (panel, text, text)
        )
        self._colors = (panel, text)
        for section in self.sections():
            widget = self._widgets.get(section.section_id)
            if widget is not None:
                self._call(section, widget, "apply_colors", panel, text)

    def set_refresh(self, refresh: Callable[[], None]) -> None:
        self._refresh = refresh
        for section in self.sections():
            widget = self._widgets.get(section.section_id)
            if widget is not None:
                self._call(section, widget, "set_refresh", refresh)

    def has_draft(self) -> bool:
        return any(
            bool(self._call(section, widget, "has_draft"))
            for section in self.sections()
            for widget in (self._widgets.get(section.section_id),)
            if widget is not None
        )

    def discard_draft(self) -> bool:
        discarded = False
        for section in self.sections():
            widget = self._widgets.get(section.section_id)
            if widget is not None and self._call(section, widget, "discard_draft"):
                discarded = True
        return discarded

    def note_focus(self, focus: object) -> None:
        for section in self.sections():
            widget = self._widgets.get(section.section_id)
            if widget is not None:
                self._call(section, widget, "note_focus", focus)
