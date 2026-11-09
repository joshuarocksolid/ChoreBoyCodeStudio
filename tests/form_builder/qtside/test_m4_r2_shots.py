# pyright: reportAttributeAccessIssue=false
"""M4.2 round-2 screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Tuple

import pytest

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.canvas import FormCanvas
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.canvas.core.gesture import PlaceAsked, ZoomAsked
from app.features.form_builder.qtside.canvas.core.place import payload_for
from app.features.form_builder.qtside.canvas.core.space import CanvasPoint, ZoomTo
from app.features.form_builder.qtside.inspector import InspectorPane
from app.features.form_builder.qtside.inspector.api import GROUP_ORDER, GroupId
from app.features.form_builder.qtside.realize.api import Realizer
from app.qt.QtWidgets import QApplication, QLabel, QScrollArea, QWidget
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_m4_empty_pages import EMPTY
from tests.form_builder.qtside.test_m4_mdi import MDI
from tests.form_builder.qtside.test_m4_pages_canvas import TABS, _Host
from tests.form_builder.qtside.test_m4_pages_keyboard import (
    _canvas as _surface_canvas,
    _click_widget,
    _close,
    _flush,
    _open_menu,
    _pages,
    _pick,
    _surface,
)
from tests.form_builder.qtside.test_m4_scroll_area import AREA
from tests.form_builder.qtside.test_m4_stand_ins import STAND
from tests.form_builder.qtside.test_m4_wizard_canvas import WIZARD

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]

_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")
_SCALES = ((100, 1.0), (200, 2.0))

_DOCK = form(
    'class="QMainWindow" name="Main"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>640</width><height>420</height></rect></property>
  <widget class="QWidget" name="centralwidget"/>
  <widget class="QDockWidget" name="dock">
   <attribute name="dockWidgetArea"><number>1</number></attribute>
   <widget class="QWidget" name="dockContents"/>
  </widget>
""",
)


def test_m4_r2_screenshots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        for scale, factor in _SCALES:
            _canvas_shot(tokens, folder, "page-shown-vs-start", TABS, mode, scale, factor, _show_second)
            _canvas_shot(tokens, folder, "pages-empty", EMPTY % ("QTabWidget", "tabs"), mode, scale, factor, None)
            _canvas_shot(tokens, folder, "scroll-area-scrolled", AREA, mode, scale, factor, _scroll)
            _canvas_shot(tokens, folder, "mdi-windows", MDI, mode, scale, factor, _tile_then_show)
            _canvas_shot(tokens, folder, "dock-bands", _DOCK, mode, scale, factor, _bands)
            _canvas_shot(tokens, folder, "wizard-canvas", WIZARD, mode, scale, factor, _show_second)
            _canvas_shot(tokens, folder, "stand-ins", STAND, mode, scale, factor, None)
        _menu_shot(qapp, tokens, folder, mode, tmp_path)
        _confirm_shot(qapp, tokens, folder, mode, tmp_path)
        _inspector_shot(tokens, folder, "container-rows-dock", _DOCK, "dock", (GroupId.PLACEMENT, GroupId.CONTENT), mode)
        _inspector_shot(tokens, folder, "container-rows-tab", TABS, "tabs", (GroupId.CONTENT,), mode)
        _inspector_shot(tokens, folder, "container-rows-page", TABS, "tab_a", (GroupId.CONTENT,), mode)
        _inspector_shot(tokens, folder, "container-rows-scroll", AREA, "scroll", (GroupId.CONTENT,), mode)


def _canvas_shot(
    tokens: ShellThemeTokens,
    folder: Path,
    stem: str,
    text: str,
    mode: str,
    scale: int,
    factor: float,
    prepare: Callable[[FormSession, FormCanvas], None] | None,
) -> None:
    host = _Host()
    with opened(text) as (session, realizer):
        parent = QWidget()
        parent.resize(1800, 1400)
        canvas = FormCanvas(session, realizer, host, parent)
        canvas.resize(1800, 1400)
        parent.show()
        canvas.setFocus()
        _flush()
        canvas.apply_theme(tokens)
        if factor != 1.0:
            canvas.send(ZoomAsked(ZoomTo(factor)))
            _flush()
        if prepare is not None:
            prepare(session, canvas)
            _flush()
        canvas.grab().save(str(folder / ("%s-%s-%d.png" % (stem, mode, scale))))
        canvas.dispose()
        parent.deleteLater()
        _flush()


def _show_second(session: FormSession, canvas: FormCanvas) -> None:
    """Show the next page through the canvas, so the chip is the switched page."""
    document = session.document
    for name in ("inside_a", "inside_one", "notes"):
        found = document.by_name(name)
        if found:
            canvas._controller._show_page_step(1, found[0])
            return


def _tile_then_show(session: FormSession, canvas: FormCanvas) -> None:
    area = session.document.by_name("mdi")[0]
    canvas._controller.tile_windows(area)
    _show_second(session, canvas)


def _scroll(session: FormSession, canvas: FormCanvas) -> None:
    del session
    root = canvas.page_widget()
    assert root is not None
    area = root.findChild(QScrollArea, "scroll")
    assert area is not None
    bar = area.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    canvas._index.invalidate("scroll")


def _bands(session: FormSession, canvas: FormCanvas) -> None:
    canvas._controller._index.ensure_fresh()
    main = session.document.by_name("Main")[0]
    dock = session.document.by_name("dock")[0]
    rect = canvas._controller._index.rect_of(main)
    assert rect is not None
    view = canvas._controller._stage.view_map()
    point = CanvasPoint(
        int(view.page_origin.x + (rect.x + 8) * view.factor),
        int(view.page_origin.y + (rect.y + rect.height // 2) * view.factor),
    )
    canvas.send(PlaceAsked(point, payload_for(session.document, (dock,))))


def _menu_shot(qapp: QApplication, tokens: ShellThemeTokens, folder: Path, mode: str, tmp_path: Path) -> None:
    del qapp
    parent, surface = _surface(tmp_path, "menu-%s" % mode)
    try:
        surface.apply_theme(tokens)
        canvas = _surface_canvas(surface)
        root = canvas.page_widget()
        label = root.findChild(QWidget, "inside_a")
        assert label is not None
        _click_widget(canvas, label)
        menu = _pages(_open_menu(canvas, surface))
        _flush()
        target = menu.window()
        target.grab().save(str(folder / ("pages-menu-%s.png" % mode)))
    finally:
        _close(parent, surface)


def _confirm_shot(qapp: QApplication, tokens: ShellThemeTokens, folder: Path, mode: str, tmp_path: Path) -> None:
    del qapp
    parent, surface = _surface(tmp_path, "confirm-%s" % mode)
    try:
        surface.apply_theme(tokens)
        canvas = _surface_canvas(surface)
        root = canvas.page_widget()
        label = root.findChild(QWidget, "inside_a")
        assert label is not None
        _click_widget(canvas, label)
        _pick(_pages(_open_menu(canvas, surface)), "Delete page")
        _flush()
        surface.grab().save(str(folder / ("page-delete-confirm-%s.png" % mode)))
    finally:
        _close(parent, surface)


def _inspector_shot(
    tokens: ShellThemeTokens,
    folder: Path,
    stem: str,
    text: str,
    name: str,
    groups: Tuple[GroupId, ...],
    mode: str,
) -> None:
    with opened(text) as (session, realizer):
        window, pane = _inspector(session, realizer)
        try:
            pane.apply_chrome(chrome_for(tokens))
            wanted = set(groups)
            for group in GROUP_ORDER:
                pane.set_group_expanded(group, group in wanted)
            found = session.document.by_name(name)
            assert found, name
            session.selection.set((found[0],), source=SelectionSource.PROGRAM)
            pane.flush()
            _flush()
            _reveal_row(pane, "Dock side" if "dock" in stem else "Starts on" if stem.endswith("tab") else "")
            pane.grab().save(str(folder / ("%s-%s-236.png" % (stem, mode))))
        finally:
            pane.dispose()
            window.close()
            window.deleteLater()
            _flush()


def _reveal_row(pane: InspectorPane, text: str) -> None:
    if not text:
        return
    area = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    if not isinstance(area, QScrollArea):
        return
    for label in pane.findChildren(QLabel):
        if label.text() == text:
            area.ensureWidgetVisible(label, 0, 12)
            _flush()
            return


def _inspector(session: FormSession, realizer: Realizer) -> Tuple[QWidget, InspectorPane]:
    window = QWidget()
    pane = InspectorPane(session, realizer, data_tab=False, on_leave=lambda: None, parent=window)
    pane.setFixedWidth(236)
    window.resize(236, 640)
    window.show()
    _flush()
    return window, pane
