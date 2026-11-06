# pyright: reportAttributeAccessIssue=false
"""M9.5 visual tour of the real Code Studio window.

Re-run from the repo root. The command writes
``docs/form_builder/orch/shots_m9_5/<NN>-<surface>-<state>-<theme>-<scale>.png``
and ``index.html`` beside those files. ``100`` is light, dark, and
high-contrast dark. ``200`` is light only, and only for the dense surfaces.
Unset ``CBCS_FB_SCREENSHOT_DIR`` and the test skips.

    export PYTHONNOUSERSITE=1 QT_QPA_PLATFORM=offscreen CBCS_DISABLE_BACKGROUND_RUNTIME=1
    export PYTHONPATH="$PWD:/Users/local/Projects/ChoreBoyCodeStudio_artifacts/vendor_py39"
    export CBCS_FB_SCREENSHOT_DIR="$PWD/docs/form_builder/orch/shots_m9_5"
    /Applications/FreeCAD.app/Contents/Resources/bin/python -s -m pytest \\
        -p no:cacheprovider --import-mode=importlib --timeout 900 -q \\
        tests/form_builder/qtside/test_m9_5_shots.py
"""

from __future__ import annotations

import html
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence
from xml.sax.saxutils import escape

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.engine.data.source import (  # noqa: E402
    DataColumn,
    RecordSource,
    Rows,
    write_rows,
)
from app.features.form_builder.engine.query.drop_target import DOCK_REFUSAL  # noqa: E402
from app.features.form_builder.engine.query.selection import SelectionSource  # noqa: E402
from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog  # noqa: E402
from app.features.form_builder.qtside.inspector import TabId  # noqa: E402
from app.features.form_builder.qtside.preview.try_log import TryLine  # noqa: E402
from app.features.form_builder.qtside.preview.what_ran import TryChrome  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtGui import QPixmap  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from app.shell.main_window import MainWindow  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.form_builder.engine.logic.test_m7_8a_uses import invoice_text, window_source  # noqa: E402
from tests.form_builder.engine.test_m8_2_scenario import _xml  # noqa: E402
from tests.form_builder.engine.test_m8_3d_from_table import _shop  # noqa: E402
from tests.form_builder.perf.reference import reference_form  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import (  # noqa: E402
    _NoMouse,
    _close,
    _open,
    _project,
    _require,
)
from tests.form_builder.qtside.test_m7_2b1_shots import (  # noqa: E402
    _apply_inspector_width,
    _pump,
    _theme,
    _with_pytest_path,
)
from tests.form_builder.qtside.test_m8_3d_shots import _select  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(900)]

_LIGHT = constants.UI_THEME_MODE_LIGHT
_DARK = constants.UI_THEME_MODE_DARK
_HC_DARK = constants.UI_THEME_MODE_HIGH_CONTRAST_DARK
_THEMES = (_LIGHT, _DARK, _HC_DARK)
_ORDER = {_LIGHT: 0, _DARK: 1, _HC_DARK: 2}


def _file(number: int, surface: str, state: str, theme: str, scale: str) -> str:
    return "%02d-%s-%s-%s-%s.png" % (number, surface, state, theme, scale)


def _want(scale: str, dense: bool) -> bool:
    if scale == "200":
        return dense
    return True


def _modes(scale: str) -> Sequence[str]:
    if scale == "200":
        return (_LIGHT,)
    return _THEMES


class _Tour:
    def __init__(self, qapp: QApplication, folder: Path, scale: str) -> None:
        self.qapp = qapp
        self.folder = folder
        self.scale = scale
        self.misses: List[str] = []

    def paint(
        self,
        window: QWidget,
        number: int,
        surface: str,
        state: str,
        target: Callable[[], Optional[QWidget]],
        *,
        dense: bool = False,
    ) -> None:
        if not _want(self.scale, dense):
            return
        for mode in _modes(self.scale):
            try:
                _theme(window, mode, self.qapp)
                widget = target()
                if widget is None or widget.width() < 2 or widget.height() < 2:
                    raise AssertionError("nothing to grab")
                _grab_on_theme(window, widget, self.folder / _file(number, surface, state, mode, self.scale))
            except Exception as exc:
                self._miss("%02d %s %s %s: %s" % (number, surface, state, mode, exc))

    def note(self, number: int, surface: str, state: str, text: str) -> None:
        if _want(self.scale, False):
            self._miss("%02d %s %s: %s" % (number, surface, state, text))

    def _miss(self, line: str) -> None:
        self.misses.append(line)
        with (self.folder / "misses.txt").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


_POPUP_GRABS = frozenset({"formBuilder.logic.uses", "formBuilder.goToWidget"})


def _theme_fill(window: QWidget) -> str:
    tokens = window._shell_theme_workflow.resolve_theme_tokens()  # type: ignore[attr-defined]
    return (
        getattr(tokens, "window_bg", "")
        or getattr(tokens, "editor_bg", "")
        or getattr(tokens, "panel_bg", "")
        or "#FFFFFF"
    )


def _compose_window(widget: QWidget, fill: str) -> QPixmap:
    """A native popup's own grab is an opaque black store. Its children still paint."""

    from app.qt.QtCore import QPoint
    from app.qt.QtGui import QColor, QPainter

    pixmap = QPixmap(max(widget.width(), 1), max(widget.height(), 1))
    pixmap.fill(QColor(fill))
    painter = QPainter(pixmap)
    for child in widget.findChildren(QWidget):
        if child.parentWidget() is not widget or not child.isVisible():
            continue
        if child.width() < 1 or child.height() < 1:
            continue
        painter.drawPixmap(child.mapTo(widget, QPoint(0, 0)), child.grab())
    painter.end()
    return pixmap


def _flatten_clear_pixels(path: Path, fill: str) -> None:
    from app.qt.QtGui import QColor, QImage, QPainter, QPixmap

    image = QImage(str(path))
    if image.isNull() or not image.hasAlphaChannel():
        return
    found = False
    for y in range(0, image.height(), 13):
        for x in range(0, image.width(), 13):
            if image.pixelColor(x, y).alpha() < 250:
                found = True
                break
        if found:
            break
    if not found:
        return
    base = QPixmap(image.size())
    base.fill(QColor(fill))
    painter = QPainter(base)
    painter.drawImage(0, 0, image)
    painter.end()
    if not base.save(str(path)):
        raise AssertionError("could not write %s" % path.name)


def _grab_on_theme(window: QWidget, widget: QWidget, path: Path) -> None:
    from app.qt.QtCore import QPoint
    from app.qt.QtGui import QPainter

    fill = _theme_fill(window)
    if widget.objectName() in _POPUP_GRABS:
        pixmap = _compose_window(widget, fill)
    else:
        pixmap = widget.grab()
    popover = window.findChild(QWidget, "formBuilder.layoutPopover")
    if (
        widget.objectName() == "formBuilder.canvas"
        and popover is not None
        and popover is not widget
        and popover.isVisible()
        and popover.width() > 2
    ):
        from app.qt.QtGui import QColor, QPixmap

        origin = widget.mapToGlobal(QPoint(0, 0))
        top = popover.mapToGlobal(QPoint(0, 0))
        shot = popover.grab()
        base = QPixmap(pixmap.size())
        base.fill(QColor(fill))
        painter = QPainter(base)
        painter.drawPixmap(0, 0, pixmap)
        painter.drawPixmap(QPoint(top.x() - origin.x(), top.y() - origin.y()), shot)
        painter.end()
        pixmap = base
    path.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(path)):
        raise AssertionError("could not write %s" % path.name)
    _flatten_clear_pixels(path, fill)


def _boot(tmp: Path, qapp: QApplication) -> tuple:
    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    root = tmp / "shop"
    window = MainWindow(state_root=str((tmp / "state").resolve()))
    _project(window, root)
    guard = _NoMouse()
    qapp.installEventFilter(guard)
    return root, window, guard


def _shutdown(window: MainWindow, qapp: QApplication, guard: _NoMouse) -> None:
    _close(window, qapp, guard)


def _reveal(widget: QWidget) -> None:
    page = widget  # type: Optional[QWidget]
    while page is not None:
        page.setVisible(True)
        parent = page.parentWidget()
        if parent is not None and hasattr(parent, "indexOf") and hasattr(parent, "setCurrentWidget"):
            try:
                if parent.indexOf(page) >= 0:  # type: ignore[attr-defined]
                    parent.setCurrentWidget(page)  # type: ignore[attr-defined]
            except Exception:
                pass
        page = parent


def _child(window: QWidget, name: str) -> QWidget:
    found = window.findChild(QWidget, name)
    if found is None:
        raise AssertionError(name)
    return found


def _select_name(surface: object, name: str) -> None:
    session = surface.session  # type: ignore[attr-defined]
    found = session.document.by_name(name)
    if not found:
        raise AssertionError(name)
    session.selection.set((found[0],), source=SelectionSource.PROGRAM)
    surface.workbench.inspector.flush()  # type: ignore[attr-defined]


def _bottom_panel(window: QWidget, open_panel: bool) -> None:
    """Full-window shots keep the Python Console collapsed unless a shot asks for it."""
    splitter = getattr(window, "_vertical_splitter", None)
    if splitter is None:
        return
    height = max(int(window.height()), 1)
    if open_panel:
        splitter.setSizes([int(height * 0.62), max(1, int(height * 0.38))])
        return
    splitter.setSizes([height, 0])


def _open_groups(inspector: QWidget) -> None:
    for button in inspector.findChildren(QToolButton):
        if button.objectName().startswith("formBuilder.group.") and not button.isChecked():
            button.setChecked(True)


def _welcome(tour: _Tour, tmp: Path) -> None:
    _require()
    window = MainWindow(state_root=str((tmp / "welcome-state").resolve()))
    window.resize(1400, 900)
    window.show()
    _pump(tour.qapp)
    try:
        tour.paint(window, 1, "start", "welcome", lambda: _child(window, "shell.welcome") if window.findChild(QWidget, "shell.welcome") else window)
    finally:
        window.close()
        _pump(tour.qapp)


def _new_form(tour: _Tour, tmp: Path) -> None:
    if not _want(tour.scale, True) and tour.scale == "200":
        return
    root, window, guard = _boot(tmp / "new", tour.qapp)
    try:
        window._open_new_form()  # noqa: SLF001
        window.resize(1400, 900)
        window.show()
        _pump(tour.qapp, 8)
        panel = _child(window, "formBuilder.newForm")
        _reveal(panel)
        _pump(tour.qapp, 4)

        def _cards() -> QWidget:
            found = _child(window, "formBuilder.newForm")
            _reveal(found)
            return found

        tour.paint(window, 2, "start", "templates", _cards, dense=True)

        def _hovered_card() -> QWidget:
            from app.qt.QtCore import QPointF
            from app.qt.QtGui import QEnterEvent

            cards = [
                card
                for card in window.findChildren(QWidget)
                if card.objectName().startswith("formBuilder.newForm.card.")
            ]
            focused = cards[0] if cards else _cards()
            hovered = cards[1] if len(cards) > 1 else focused
            point = QPointF(hovered.width() / 2.0, hovered.height() / 2.0)
            hovered.enterEvent(QEnterEvent(point, point, point))
            focused.setFocus()
            return _cards()

        tour.paint(window, 64, "start", "card-hover-focus", _hovered_card)
        from app.features.form_builder.engine.project.user_templates import TemplateInfo

        _cards().set_user_templates(  # type: ignore[attr-defined]
            (TemplateInfo("user", "invoice", "Invoice copy", "Header, lines, and a save button"),)
        )
        _pump(tour.qapp)
        tour.paint(window, 3, "start", "your-templates", _cards)
        _from_table(tour, window, root)
    finally:
        _shutdown(window, tour.qapp, guard)


def _from_table(tour: _Tour, window: MainWindow, root: Path) -> None:
    if tour.scale == "200":
        # The filled dialog is dense. The empty list is not.
        _from_table_filled(tour, window, root)
        return
    tokens = tokens_from_palette(tour.qapp.palette(), force_mode=_LIGHT)
    empty = FromTableDialog(
        project_root=str(root),
        stem="invoice",
        chrome=chrome_for(tokens),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
        parent=window,
    )
    try:
        empty.resize(1100, 680)
        empty.show()
        _pump(tour.qapp)
        tour.paint(window, 4, "start", "from-table-empty", lambda: empty)
    finally:
        empty.close()
    _from_table_filled(tour, window, root)


def _from_table_filled(tour: _Tour, window: MainWindow, root: Path) -> None:
    shop, _schema = _shop(root / "filled")
    tokens = tokens_from_palette(tour.qapp.palette(), force_mode=_LIGHT)
    dialog = FromTableDialog(
        project_root=str(shop),
        stem="invoice",
        chrome=chrome_for(tokens),
        date_format="yyyy-MM-dd",
        name_reason=lambda: None,
        parent=window,
    )
    try:
        dialog.set_database(str(shop / "data" / "shop.db"), "shop")
        _select(dialog, "invoices")
        if dialog._lines.isChecked():  # noqa: SLF001
            dialog._lines.setChecked(False)  # noqa: SLF001
        dialog.resize(1100, 680)
        dialog.show()
        _pump(tour.qapp)

        def _rechrome(mode: str) -> None:
            fresh = tokens_from_palette(tour.qapp.palette(), force_mode=mode)
            dialog._chrome = chrome_for(fresh)  # noqa: SLF001
            dialog._apply_chrome()  # noqa: SLF001

        original = _theme

        def themed(host: QWidget, mode: str, qapp: QApplication) -> None:
            original(host, mode, qapp)
            _rechrome(mode)

        # Paint uses _theme from the module. Rechrome inside the target instead.
        def grab_filled() -> QWidget:
            _rechrome(str(getattr(window, "_theme_mode", _LIGHT)))
            return dialog

        tour.paint(window, 5, "start", "from-table-filled", grab_filled, dense=True)
        dialog._lines.setChecked(True)  # noqa: SLF001
        _pump(tour.qapp)
        tour.paint(window, 6, "start", "from-table-lines", grab_filled, dense=True)
        del themed
    finally:
        dialog.close()


def _form(tour: _Tour, tmp: Path, name: str, text: str) -> tuple:
    root, window, guard = _boot(tmp, tour.qapp)
    path = root / "forms" / name
    surface = _open(window, tour.qapp, path, text)
    return root, window, guard, surface, path


def _empty_form(tour: _Tour, tmp: Path) -> None:
    if tour.scale == "200":
        return
    text = _xml(RecordSource("shop", "invoices", "id"), ())
    # An empty layout, not a data form: replace the generated body.
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>320</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
    _root, window, guard, surface, _path = _form(tour, tmp / "empty", "empty.ui", text)
    try:
        tour.paint(window, 7, "form", "empty", lambda: window)
        surface.workbench.focus_section("logic")
        _pump(tour.qapp)
        tour.paint(window, 35, "logic", "empty", lambda: _child(window, "formBuilder.logic"))
        surface.workbench.focus_section("data")
        _pump(tour.qapp)
        tour.paint(window, 40, "data", "no-connection", lambda: _child(window, "formBuilder.dataPanel"))
        from app.features.form_builder.qtside.data_panel.sheets import ConnectSheet

        sheet = ConnectSheet(window, surface.session, getattr(surface.workbench, "_tokens", None))
        sheet.resize(720, 520)
        sheet.show()
        _pump(tour.qapp)
        tour.paint(window, 41, "data", "connection-list-empty", lambda: sheet)
        sheet.close()
    finally:
        _shutdown(window, tour.qapp, guard)


def _data_ui() -> str:
    rows = Rows(
        "invoice_lines",
        "invoice_id",
        "id",
        (DataColumn("qty", "Qty", "whole", None, "1"),),
        "line_no",
        "line_no",
    )
    extra = '    <property name="cbcsRows" stdset="0"><string notr="true">%s</string></property>\n' % escape(write_rows(rows))
    return _xml(
        RecordSource("shop", "invoices", "id"),
        (
            ("QLabel", "notesLabel", "", '<property name="text"><string>Notes</string></property>\n'),
            ("QLineEdit", "notesEdit", "notes", ""),
            ("QTableView", "linesView", "", extra),
            ("QPushButton", "saveButton", "", '<property name="text"><string>Save</string></property>\n'),
        ),
    )


def _invoice(tour: _Tour, tmp: Path) -> None:
    _root, window, guard, surface, path = _form(tour, tmp / "invoice", "invoice.ui", invoice_text())
    (path.parent / "invoice_window.py").write_text(window_source(), encoding="utf-8")
    logic = window.findChild(QWidget, "formBuilder.logic")
    reload = getattr(logic, "reload", None)
    if callable(reload):
        reload()
    try:
        _bottom_panel(window, False)
        tour.paint(window, 8, "form", "invoice", lambda: window, dense=True)
        _select_name(surface, "emailEdit")
        _pump(tour.qapp)
        tour.paint(window, 10, "canvas", "selection", lambda: _child(window, "formBuilder.canvas"), dense=True)
        session = surface.session
        names = ("emailEdit", "discountEdit", "saveButton")
        ids = tuple(session.document.by_name(name)[0] for name in names)
        session.selection.set(ids, source=SelectionSource.PROGRAM)
        _pump(tour.qapp)
        tour.paint(window, 11, "canvas", "multi-select", lambda: _child(window, "formBuilder.canvas"))
        _select_name(surface, "emailEdit")
        surface.zoom_to(0.75)
        _pump(tour.qapp)
        tour.paint(window, 18, "canvas", "zoom-75", lambda: window)
        surface.zoom_to(2.0)
        _pump(tour.qapp)
        tour.paint(window, 19, "canvas", "zoom-200", lambda: window, dense=True)
        surface.zoom_fit()
        _pump(tour.qapp)
        surface.show_plain(DOCK_REFUSAL)
        _pump(tour.qapp)
        toast = window.findChild(QWidget, "formBuilder.commandToast")
        tour.paint(window, 17, "canvas", "refused-drop", lambda: toast or window)
        surface.show_plain(
            "emailEdit is used by behavior from a newer version of Code Studio, so it can't be renamed here."
        )
        _pump(tour.qapp)
        tour.paint(window, 61, "outline", "rename-refusal", lambda: window.findChild(QWidget, "formBuilder.commandToast") or window)
        _overlays(tour, window, surface)
        _inspector(tour, window, surface)
        _logic(tour, window, surface)
        _outline(tour, window, surface)
        _insert(tour, window, surface)
        _find(tour, window, surface)
        _problems(tour, window, surface)
    finally:
        _shutdown(window, tour.qapp, guard)


def _overlays(tour: _Tour, window: MainWindow, surface: object) -> None:
    _select_name(surface, "discountEdit")
    try:
        def _popover() -> Optional[QWidget]:
            surface.open_layout_popover(surface.session.document.by_name("discountEdit")[0])  # type: ignore[attr-defined]
            _pump(tour.qapp, 2)
            return _child(window, "formBuilder.canvas")

        tour.paint(window, 13, "canvas", "layout-popover", _popover)
        menu = window.findChild(QWidget, "formBuilder.layoutPopover")
        if menu is not None:
            menu.hide()
    except Exception as exc:
        tour.note(13, "canvas", "layout-popover", str(exc))
    for number, state, kind in (
        (14, "buddies", "buddies"),
        (15, "tab-order", "tab_order"),
        (16, "connections", "connections"),
    ):
        try:
            surface.toggle_overlay(kind)  # type: ignore[attr-defined]
            _pump(tour.qapp)
            tour.paint(window, number, "canvas", state, lambda: window, dense=(kind == "connections"))
            if kind == "buddies":
                tour.paint(
                    window,
                    66,
                    "canvas",
                    "mode-banner-buddies",
                    lambda: window.findChild(QWidget, "formBuilder.overlayBanner") or window,
                )
        except Exception as exc:
            tour.note(number, "canvas", state, str(exc))
        finally:
            try:
                surface.toggle_overlay(kind)  # type: ignore[attr-defined]
            except Exception:
                pass
    _drag_line(tour, window, surface)


def _drag_line(tour: _Tour, window: MainWindow, surface: object) -> None:
    """Hold the insertion line a palette drop would paint, with its chip."""
    if tour.scale == "200":
        return
    try:
        canvas = _child(window, "formBuilder.canvas")
        _select_name(surface, "emailEdit")
        surface.workbench.canvas.set_insert_preview("QPushButton")  # type: ignore[attr-defined]
        _pump(tour.qapp)
        tour.paint(window, 12, "canvas", "insertion-line", lambda: canvas)
    except Exception as exc:
        tour.note(12, "canvas", "insertion-line", str(exc))
    finally:
        try:
            surface.workbench.canvas.set_insert_preview(None)  # type: ignore[attr-defined]
        except Exception:
            pass


def _inspector(tour: _Tour, window: MainWindow, surface: object) -> None:
    inspector = surface.workbench.inspector  # type: ignore[attr-defined]
    _select_name(surface, "emailEdit")
    inspector.focus_tab(TabId.PROPERTIES)
    _open_groups(inspector)
    _pump(tour.qapp)
    tour.paint(window, 27, "inspector", "properties", lambda: _child(window, "formBuilder.inspector"), dense=True)

    def _size_section() -> QWidget:
        body = window.findChild(QWidget, "formBuilder.sizeBody")
        scroll = window.findChild(QWidget, "formBuilder.inspectorScroll")
        ensure = getattr(scroll, "ensureWidgetVisible", None)
        if body is not None and callable(ensure):
            ensure(body)
        return _child(window, "formBuilder.inspector")

    tour.paint(window, 63, "inspector", "size", _size_section)
    inspector.focus_tab(TabId.BEHAVIOR)
    _pump(tour.qapp)
    tour.paint(window, 28, "inspector", "behavior", lambda: _child(window, "formBuilder.inspector"), dense=True)
    _select_name(surface, "emailEdit")
    inspector.focus_tab(TabId.BEHAVIOR)
    _pump(tour.qapp)
    tour.paint(window, 29, "inspector", "checks", lambda: window.findChild(QWidget, "formBuilder.checks") or _child(window, "formBuilder.inspector"))
    _select_name(surface, "saveButton")
    inspector.focus_tab(TabId.BEHAVIOR)
    _pump(tour.qapp)
    tour.paint(window, 30, "inspector", "events", lambda: window.findChild(QWidget, "formBuilder.events") or _child(window, "formBuilder.inspector"), dense=True)
    then = None
    for button in window.findChildren(QPushButton):
        if button.text().startswith("+ Then"):
            then = button
            break
    def _picker() -> QWidget:
        # Theme rebuilds the events list, so find the button after the theme is on.
        button = None
        for candidate in window.findChildren(QPushButton):
            if candidate.text().startswith("+ Then"):
                button = candidate
                break
        if button is None:
            raise AssertionError("no Then button")
        button.click()
        picker = window.findChild(QWidget, "formBuilder.eventPicker")
        if picker is None or picker.width() < 2:
            raise AssertionError("picker")
        return picker

    if then is not None:
        tour.paint(window, 31, "inspector", "step-picker", _picker)
    else:
        tour.note(31, "inspector", "step-picker", "no Then button")


def _show_logic_rows(window: QWidget) -> None:
    """The left splitter's share hides the rows the review is looking at."""
    panel = window.findChild(QWidget, "formBuilder.logic")
    split = window.findChild(QWidget, "formBuilder.leftSplitter")
    if panel is None or split is None:
        return
    panel.setMinimumHeight(max(panel.minimumHeight(), 320))
    index_of = getattr(split, "indexOf", None)
    sizes_of = getattr(split, "sizes", None)
    set_sizes = getattr(split, "setSizes", None)
    if callable(index_of) and callable(sizes_of) and callable(set_sizes):
        index = index_of(panel)
        raw_sizes = sizes_of()
        if not isinstance(index, int) or not isinstance(raw_sizes, list):
            return
        sizes = [int(item) for item in raw_sizes]
        if 0 <= index < len(sizes) and sizes[index] < 320:
            spare = 320 - sizes[index]
            sizes[index] = 320
            donor = 0 if index else 1
            if donor < len(sizes):
                sizes[donor] = max(80, sizes[donor] - spare)
            set_sizes(sizes)
    scroll = panel.findChild(QWidget, "formBuilder.logic.scroll")
    ensure = getattr(scroll, "ensureWidgetVisible", None)
    if callable(ensure):
        for child in panel.findChildren(QWidget, "formBuilder.logic.formula"):
            if "save_invoice" in child.text():
                ensure(child)
                break


def _logic(tour: _Tour, window: MainWindow, surface: object) -> None:
    surface.workbench.focus_section("logic")  # type: ignore[attr-defined]
    _pump(tour.qapp)

    def _filled() -> QWidget:
        _show_logic_rows(window)
        _pump(tour.qapp)
        return _child(window, "formBuilder.logic")

    tour.paint(window, 36, "logic", "filled", _filled, dense=True)

    def _problems_chip() -> QWidget:
        from app.qt.QtCore import QPointF
        from app.qt.QtGui import QEnterEvent

        panel = _child(window, "formBuilder.logic")
        warning = None
        for child in panel.findChildren(QWidget):
            face = getattr(child, "face", None)
            if callable(face) and bool(getattr(face(), "warning", False)):
                warning = child
                break
        if warning is not None:
            use = getattr(warning, "use", None)
            name = str(getattr(use, "widget", "") or getattr(use, "name", "") or "")
            setter = getattr(panel, "set_filter_text", None)
            if name and callable(setter):
                setter(name)
            point = QPointF(warning.width() / 2.0, warning.height() / 2.0)
            warning.enterEvent(QEnterEvent(point, point, point))
            scroll = panel.findChild(QWidget, "formBuilder.logic.scroll")
            ensure = getattr(scroll, "ensureWidgetVisible", None)
            if callable(ensure):
                ensure(warning)
        return panel

    tour.paint(window, 37, "logic", "problems", _problems_chip)
    field = window.findChild(QLineEdit, "formBuilder.logic.filter")
    if field is not None:
        field.setText("")
    try:
        from app.features.form_builder.qtside.logic_panel.read_as_text import show_behavior_text

        show_behavior_text(surface)
        _pump(tour.qapp)
        page = window.findChild(QWidget, "formBuilder.readAsText")
        tour.paint(window, 38, "logic", "read-as-text", lambda: page or window, dense=True)
    except Exception as exc:
        tour.note(38, "logic", "read-as-text", str(exc))
    finally:
        stack = getattr(surface, "_stack", None)
        workbench = getattr(surface, "_workbench", None)
        if stack is not None and workbench is not None:
            stack.setCurrentWidget(workbench)
    _select_name(surface, "emailEdit")
    try:
        from app.features.form_builder.qtside.logic_panel.open import show_uses

        def _uses() -> Optional[QWidget]:
            show_uses(surface)
            _pump(tour.qapp, 2)
            return window.findChild(QWidget, "formBuilder.logic.uses")

        tour.paint(window, 39, "logic", "uses", _uses)
    except Exception as exc:
        tour.note(39, "logic", "uses", str(exc))
    finally:
        dialog = window.findChild(QWidget, "formBuilder.logic.uses")
        if dialog is not None:
            dialog.close()


def _outline(tour: _Tour, window: MainWindow, surface: object) -> None:
    surface.workbench.focus_outline()  # type: ignore[attr-defined]
    _pump(tour.qapp)
    tour.paint(window, 23, "outline", "tree", lambda: _child(window, "formBuilder.outline"), dense=True)

    def _hovered_row() -> QWidget:
        from app.qt.QtCore import Qt
        from app.qt.QtWidgets import QTreeWidget, QTreeWidgetItem
        from app.features.form_builder.engine.ids import NodeId

        outline = _child(window, "formBuilder.outline")
        tree = window.findChild(QTreeWidget, "formBuilder.structure")
        if not isinstance(tree, QTreeWidget):
            return outline
        role = int(getattr(Qt, "UserRole"))
        view = tree.viewport().rect()
        chosen = None

        def walk(parent: Optional[QTreeWidgetItem]) -> None:
            nonlocal chosen
            if chosen is not None:
                return
            count = tree.topLevelItemCount() if parent is None else parent.childCount()
            for index in range(count):
                current = tree.topLevelItem(index) if parent is None else parent.child(index)
                if current is None:
                    continue
                rect = tree.visualItemRect(current)
                if rect.isValid() and view.contains(rect.center()) and current is not tree.currentItem():
                    chosen = current
                    return
                walk(current)

        walk(None)
        if chosen is None:
            chosen = tree.currentItem() or tree.topLevelItem(0)
        if chosen is not None:
            tree.scrollToItem(chosen)
            raw = chosen.data(0, role)
            if raw is not None:
                surface.workbench.outline.set_hover(NodeId(int(raw)))  # type: ignore[attr-defined]
            tree.viewport().repaint()
        return outline

    tour.paint(window, 65, "outline", "hover", _hovered_row)
    surface.workbench.outline.set_hover(None)  # type: ignore[attr-defined]
    node = surface.session.document.by_name("emailEdit")[0]
    try:
        surface.workbench.outline.begin_rename(node)  # type: ignore[attr-defined]
        _pump(tour.qapp)
        editor = window.findChild(QLineEdit, "formBuilder.outlineRename")
        if editor is not None:
            editor.setText("emailEdit")
            editor.deselect()
        tour.paint(window, 24, "outline", "rename", lambda: _child(window, "formBuilder.outline"))
        if editor is not None:
            editor.setText("customerStreetAddressLineOneThatDoesNotFitInTheRow")
            _pump(tour.qapp)
        tour.paint(window, 25, "outline", "long-name", lambda: _child(window, "formBuilder.outline"), dense=True)
    except Exception as exc:
        tour.note(24, "outline", "rename", str(exc))
    finally:
        tour.qapp.focusWidget()
        # Esc leaves the editor without committing a bad name.
        from app.qt.QtTest import QTest

        QTest.keyClick(window, Qt.Key.Key_Escape)
        _pump(tour.qapp)
    try:
        prose = surface.session.refs.ask_sentence(surface.session.document, "emailEdit", ())  # type: ignore[attr-defined]
        surface.workbench.outline.show_delete(prose or "emailEdit is used by a check.", (node,))  # type: ignore[attr-defined]
        _pump(tour.qapp)
        tour.paint(window, 26, "outline", "delete-prompt", lambda: window.findChild(QWidget, "formBuilder.outlineConfirm") or window)
    except Exception as exc:
        tour.note(26, "outline", "delete-prompt", str(exc))


def _insert(tour: _Tour, window: MainWindow, surface: object) -> None:
    surface.workbench.focus_section("insert") if False else None
    button = window.findChild(QWidget, "formBuilder.leftRail.insert")
    if button is not None and hasattr(button, "click"):
        button.click()
    else:
        surface._focus_insert()  # type: ignore[attr-defined]
    _pump(tour.qapp)
    tour.paint(window, 20, "widget-box", "open", lambda: _child(window, "formBuilder.insert"), dense=True)
    field = window.findChild(QLineEdit, "formBuilder.insertFilter")
    if field is not None:
        field.setText("zzzz-no-such-widget")
        _pump(tour.qapp)
    tour.paint(window, 21, "widget-box", "find-empty", lambda: _child(window, "formBuilder.insert"))
    if field is not None:
        field.clear()
    try:
        surface.workbench.outline.show_insert()  # type: ignore[attr-defined]
        _pump(tour.qapp)
        quick = window.findChild(QWidget, "formBuilder.outlineInsert")
        tour.paint(window, 22, "widget-box", "quick-insert", lambda: quick or window)
    except Exception as exc:
        tour.note(22, "widget-box", "quick-insert", str(exc))
    finally:
        quick = window.findChild(QWidget, "formBuilder.outlineInsert")
        if quick is not None:
            quick.hide()


def _find(tour: _Tour, window: MainWindow, surface: object) -> None:
    if tour.scale == "200":
        return
    try:
        def _go() -> Optional[QWidget]:
            surface.go_to_widget()  # type: ignore[attr-defined]
            _pump(tour.qapp, 2)
            search = window.findChild(QLineEdit, "formBuilder.goToWidgetSearch")
            if search is not None:
                search.setText("zzzz")
                _pump(tour.qapp, 1)
            return window.findChild(QWidget, "formBuilder.goToWidget")

        tour.paint(window, 59, "find", "empty", _go)
    except Exception as exc:
        tour.note(59, "find", "empty", str(exc))
    finally:
        picker = window.findChild(QWidget, "formBuilder.goToWidget")
        if picker is not None:
            picker.close()


def _problems(tour: _Tour, window: MainWindow, surface: object) -> None:
    if tour.scale == "200":
        return
    tabs = getattr(window, "_problems_tab_widget", None)
    panel = getattr(window, "_problems_panel", None)
    splitter = getattr(window, "_vertical_splitter", None)
    if tabs is not None and panel is not None:
        tabs.setCurrentWidget(panel)
        if panel is not None:
            panel.setMinimumHeight(320)
        if splitter is not None:
            splitter.setSizes([640, 360])
        _pump(tour.qapp)
        tour.paint(window, 53, "problems", "form", lambda: panel if panel is not None else window)
    del surface


def _bound(tour: _Tour, tmp: Path) -> None:
    _root, window, guard, surface, _path = _form(tour, tmp / "bound", "record.ui", _data_ui())
    try:
        inspector = surface.workbench.inspector
        _select_name(surface, "notesLabel")
        inspector.focus_tab(TabId.DATA)
        _pump(tour.qapp)
        tour.paint(window, 32, "inspector", "data-unbound", lambda: _child(window, "formBuilder.inspector"))
        _select_name(surface, "notesEdit")
        inspector.focus_tab(TabId.DATA)
        _pump(tour.qapp)
        tour.paint(window, 33, "inspector", "data-bound", lambda: _child(window, "formBuilder.inspector"), dense=True)
        _select_name(surface, "linesView")
        inspector.focus_tab(TabId.DATA)
        _pump(tour.qapp)
        tour.paint(window, 34, "inspector", "data-lines", lambda: _child(window, "formBuilder.inspector"), dense=True)
    finally:
        _shutdown(window, tour.qapp, guard)


def _big(tour: _Tour, tmp: Path) -> None:
    if tour.scale == "200":
        return
    _root, window, guard, _surface, _path = _form(tour, tmp / "big", "big.ui", reference_form(1000).xml)
    try:
        canvas = _child(window, "formBuilder.canvas")
        bar = getattr(canvas, "verticalScrollBar", None)
        if callable(bar):
            scroll = bar()
            scroll.setValue(scroll.maximum() // 2)
        _pump(tour.qapp)
        _bottom_panel(window, False)
        tour.paint(window, 9, "form", "thousand", lambda: window)
        window.resize(1366, 768)
        _bottom_panel(window, False)
        _pump(tour.qapp)
        column = window.findChild(QWidget, "formBuilder.leftScroll")
        sentence = window.findChild(QLabel, "formBuilder.logic.empty")
        ensure = getattr(column, "ensureWidgetVisible", None)
        if callable(ensure) and sentence is not None:
            ensure(sentence)
            _pump(tour.qapp)
        tour.paint(window, 62, "window", "short", lambda: window)
        _bottom_panel(window, True)
        _pump(tour.qapp)
        tour.paint(window, 62, "window", "short-console", lambda: window)
    finally:
        _shutdown(window, tour.qapp, guard)


def _missing_connection(tour: _Tour, tmp: Path) -> None:
    if tour.scale == "200":
        return
    text = _xml(
        RecordSource("gone", "invoices", "id"),
        (("QLineEdit", "notesEdit", "notes", ""),),
    )
    root, window, guard, _surface, path = _form(tour, tmp / "gone", "gone.ui", text)
    try:
        workflow = getattr(window, "_save_workflow", None)
        save = getattr(workflow, "save_tab", None)
        if callable(save):
            save(str(path))
        _pump(tour.qapp, 8)
        _bottom_panel(window, False)
        tour.paint(window, 56, "form", "fb510", lambda: window)
        py = root / "forms" / "ui_gone.py"
        py.write_text("## Generated from gone.ui by ChoreBoy Code Studio\n", encoding="utf-8")
        assert window._editor_tab_factory.open_file_in_editor(str(py))  # noqa: SLF001
        _pump(tour.qapp)
        def _banner() -> Optional[QWidget]:
            bars = window.findChildren(QWidget, "shell.generatedFileBar")
            visible = [bar for bar in bars if bar.isVisible()]
            return visible[-1] if visible else None

        tour.paint(window, 54, "files", "generated-banner", _banner)

        def _banner_page() -> Optional[QWidget]:
            bar = _banner()
            page = bar.parentWidget() if bar is not None else None
            if page is None or page.width() < 2 or page.height() < 2:
                return bar
            return page

        tour.paint(window, 67, "files", "generated-banner", _banner_page)
        damaged = root / "forms" / "broken.ui"
        damaged.write_bytes(b"<?xml version='1.0' \xff\xfe not utf-8")
        window._editor_tab_factory.open_file_in_editor(str(damaged))  # noqa: SLF001
        _pump(tour.qapp)
        tour.paint(window, 55, "files", "damaged-ui", lambda: window)
    except Exception as exc:
        tour.note(56, "form", "fb510", str(exc))
    finally:
        _shutdown(window, tour.qapp, guard)


def _connections(tour: _Tour, tmp: Path) -> None:
    if tour.scale == "200":
        return
    from app.features.form_builder.engine.data.connections import Connection, ConnectionSet, save_connections
    from app.features.form_builder.integration.settings_ext.connections_page import ConnectionsPage

    root, window, guard = _boot(tmp / "conn", tour.qapp)
    window.resize(1400, 900)
    window.show()
    try:
        empty = ConnectionsPage(window, str(root))
        empty.resize(880, 520)
        empty.show()
        _pump(tour.qapp)
        tour.paint(window, 43, "connections", "empty", lambda: empty)
        empty.hide()
        save_connections(
            str(root),
            ConnectionSet((Connection("shop", "Shop database", "sqlite", file="data/shop.db"),)),
        )
        page = ConnectionsPage(window, str(root))
        page.resize(880, 520)
        page.show()
        _pump(tour.qapp)
        tour.paint(window, 44, "connections", "list", lambda: page, dense=True)
        page._show_test_result({"ok": True, "server": "shop.db", "tables": 4, "driver": "sqlite3", "text": ""})  # noqa: SLF001
        # _show_test_result reads payload["text"], not the formatted probe. Set the label from the real formatter.
        from app.features.form_builder.integration.settings_ext.connections_page import _format_probe

        page._result.setText(  # noqa: SLF001
            _format_probe({"ok": True, "server": "shop.db", "tables": 4, "driver": "sqlite3"})
        )
        _pump(tour.qapp)
        tour.paint(window, 46, "connections", "test-ok", lambda: page)
        from app.features.form_builder.engine.data.tester import probe_sqlite

        page._result.setText(probe_sqlite("data/missing.db"))  # noqa: SLF001
        _pump(tour.qapp)
        tour.paint(window, 47, "connections", "test-fail", lambda: page)
        page.hide()
        secret = _password(window)
        secret.show()
        _pump(tour.qapp)
        tour.paint(window, 45, "connections", "password", lambda: secret)
        secret.close()
    finally:
        _shutdown(window, tour.qapp, guard)


def _password(parent: QWidget) -> QDialog:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Password")
    dialog.setObjectName("formBuilder.password")
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Password for clerk on Shop database", dialog))
    field = QLineEdit(dialog)
    echo = getattr(getattr(QLineEdit, "EchoMode", QLineEdit), "Password")
    field.setEchoMode(echo)
    field.setText("secret")
    layout.addWidget(field)
    layout.addWidget(QCheckBox("Remember on this machine", dialog))
    standard = getattr(QDialogButtonBox, "StandardButton", QDialogButtonBox)
    layout.addWidget(QDialogButtonBox(standard.Ok | standard.Cancel, parent=dialog))
    dialog.resize(420, 180)
    return dialog


def _preview(tour: _Tour, tmp: Path) -> None:
    root, window, guard = _boot(tmp / "preview", tour.qapp)
    window.resize(1400, 900)
    window.show()
    try:
        chrome = TryChrome(window)
        chrome.resize(1100, 640)
        form = QWidget(chrome)
        column = QVBoxLayout(form)
        column.addWidget(QLabel("Customer", form))
        column.addWidget(QLineEdit(form))
        column.addStretch(1)
        chrome.adopt(form)
        chrome.set_try_data(
            "Data: Shop database.",
            "Try: changes to Shop database are rolled back. While a save runs, other people using it may wait up to 2 seconds.",
            False,
        )
        from app.features.form_builder.engine.ipc.protocol import SourceRef

        chrome.what_ran.add(
            (TryLine("Saved, then rolled back", "", SourceRef(object_name="saveButton"), "save"),),
            0,
        )
        chrome.show()
        _pump(tour.qapp)
        tour.paint(window, 48, "preview", "run-behavior", lambda: chrome, dense=True)
        chrome.hide()
        conflict = _box(
            window,
            "Someone else changed this invoice since you opened it.",
            ("Reload their version", "Keep mine and save", "Cancel"),
        )
        conflict.show()
        _pump(tour.qapp)
        tour.paint(window, 49, "preview", "conflict", lambda: conflict)
        conflict.hide()
        deleted = _box(window, "This invoice was deleted by someone else.", ("Close",))
        deleted.show()
        _pump(tour.qapp)
        tour.paint(window, 50, "preview", "deleted", lambda: deleted)
        deleted.hide()
        del root
    finally:
        _shutdown(window, tour.qapp, guard)


def _box(parent: QWidget, text: str, labels: Sequence[str]) -> QMessageBox:
    box = QMessageBox(parent)
    box.setText(text)
    roles = (
        QMessageBox.ButtonRole.AcceptRole,
        QMessageBox.ButtonRole.ActionRole,
        QMessageBox.ButtonRole.RejectRole,
    )
    for label, role in zip(labels, roles):
        box.addButton(label, role)
    box.resize(480, 160)
    return box


def _options(tour: _Tour, tmp: Path) -> None:
    if tour.scale == "200":
        return
    _root, window, guard, surface, _path = _form(tour, tmp / "options", "invoice.ui", invoice_text())
    try:
        button = _child(window, "formBuilder.textSize")
        menu = button.menu() if hasattr(button, "menu") else None
        if menu is not None:
            menu.show()
        _pump(tour.qapp)
        tour.paint(window, 51, "preview", "options", lambda: menu or button)
        if menu is not None:
            menu.close()
    finally:
        _shutdown(window, tour.qapp, guard)
        del surface


def _pictures(tour: _Tour, tmp: Path) -> None:
    if tour.scale == "200":
        return
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>400</width><height>240</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLabel" name="title"><property name="text"><string>Title</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""
    _root, window, guard, surface, _path = _form(tour, tmp / "pics", "pics.ui", text)
    try:
        session = surface.session
        session.selection.set((session.document.root.id,), source=SelectionSource.PROGRAM)
        surface.workbench.inspector.flush()
        surface.workbench.inspector.focus_tab(TabId.PROPERTIES)
        _open_groups(surface.workbench.inspector)
        _pump(tour.qapp)
        empty = window.findChild(QLabel, "formBuilder.picturesFilesNone")
        if empty is not None:
            scroll = window.findChild(QWidget, "formBuilder.inspectorScroll")
            ensure = getattr(scroll, "ensureWidgetVisible", None)
            if callable(ensure):
                ensure(empty)
        tour.paint(
            window,
            58,
            "pictures",
            "none",
            lambda: empty or _child(window, "formBuilder.inspector"),
        )
    finally:
        _shutdown(window, tour.qapp, guard)


def _narrow_again(tour: _Tour, tmp: Path) -> None:
    """Shot 60 is the 236 px inspector. Shot 34 stays the lines grid."""
    if not _want(tour.scale, True):
        return
    _root, window, guard, surface, _path = _form(tour, tmp / "narrow", "record.ui", _data_ui())
    try:
        _select_name(surface, "notesEdit")
        surface.workbench.inspector.focus_tab(TabId.PROPERTIES)
        _open_groups(surface.workbench.inspector)
        _apply_inspector_width(window, 236)
        _pump(tour.qapp)
        inspector = _child(window, "formBuilder.inspector")
        if inspector is not None:
            for button in inspector.findChildren(QToolButton):
                if button.text() in ("Center", "Justify", "Middle"):
                    scroll = inspector.findChild(QWidget, "formBuilder.inspectorScroll")
                    ensure = getattr(scroll, "ensureWidgetVisible", None)
                    if callable(ensure):
                        ensure(button)
                    break
        _pump(tour.qapp)
        tour.paint(window, 60, "inspector", "narrow", lambda: inspector, dense=True)
    finally:
        _shutdown(window, tour.qapp, guard)


def _problems_empty(tour: _Tour, tmp: Path) -> None:
    if tour.scale == "200":
        return
    _root, window, guard = _boot(tmp / "quiet", tour.qapp)
    window.resize(1400, 900)
    window.show()
    try:
        tabs = getattr(window, "_problems_tab_widget", None)
        panel = getattr(window, "_problems_panel", None)
        splitter = getattr(window, "_vertical_splitter", None)
        if tabs is not None and panel is not None:
            tabs.setCurrentWidget(panel)
        if panel is not None:
            panel.setMinimumHeight(320)
        if splitter is not None:
            splitter.setSizes([640, 360])
        _pump(tour.qapp)
        tour.paint(window, 52, "problems", "empty", lambda: panel if panel is not None else window)
    finally:
        _shutdown(window, tour.qapp, guard)


def _shoot(qapp: QApplication, tmp: Path, folder: Path, scale: str) -> List[str]:
    tour = _Tour(qapp, folder, scale)
    steps = (
        ("welcome", lambda: _welcome(tour, tmp)),
        ("new-form", lambda: _new_form(tour, tmp)),
        ("empty-form", lambda: _empty_form(tour, tmp)),
        ("invoice", lambda: _invoice(tour, tmp)),
        ("bound", lambda: _bound(tour, tmp)),
        ("narrow", lambda: _narrow_again(tour, tmp)),
        ("thousand", lambda: _big(tour, tmp)),
        ("missing-connection", lambda: _missing_connection(tour, tmp)),
        ("connections", lambda: _connections(tour, tmp)),
        ("preview", lambda: _preview(tour, tmp)),
        ("options", lambda: _options(tour, tmp)),
        ("pictures", lambda: _pictures(tour, tmp)),
        ("problems-empty", lambda: _problems_empty(tour, tmp)),
    )
    for name, step in steps:
        try:
            step()
        except Exception as exc:
            tour._miss("00 tour %s: %s" % (name, exc))
    return tour.misses


def _assert_distinct_shots(folder: Path) -> None:
    """Two different shot names must not share pixels at the same theme and scale."""
    groups = {}
    for path in folder.glob("*.png"):
        parts = path.stem.split("-")
        if len(parts) < 4:
            continue
        stem = "-".join(parts[:-2])
        key = (parts[-2], parts[-1])
        groups.setdefault(key, {}).setdefault(path.read_bytes(), []).append(stem)
    dupes = []
    for theme, scale in sorted(groups):
        for stems in groups[(theme, scale)].values():
            unique = sorted(set(stems))
            if len(unique) > 1:
                dupes.append("%s %s: %s" % (theme, scale, ", ".join(unique)))
    assert not dupes, "identical shots:\n" + "\n".join(dupes)


def _write_index(folder: Path) -> None:
    groups = {}
    for path in sorted(folder.glob("*.png")):
        parts = path.stem.split("-")
        if len(parts) < 4:
            continue
        scale = parts[-1]
        theme = parts[-2]
        stem = "-".join(parts[:-2])
        groups.setdefault(stem, []).append((theme, scale, path.name))
    lines = [
        "<!DOCTYPE html>",
        '<meta charset="utf-8">',
        "<title>M9.5 form builder tour</title>",
        "<style>",
        "body { font: 14px/1.4 sans-serif; margin: 24px; background: #111; color: #eee; }",
        "h1 { font-size: 20px; font-weight: 600; }",
        "h2 { font-size: 15px; margin: 28px 0 8px; }",
        ".row { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }",
        "figure { margin: 0; }",
        "img { width: 420px; height: auto; background: #000; }",
        "figcaption { font-size: 12px; color: #bbb; }",
        "</style>",
        "<h1>M9.5 form builder tour</h1>",
        "<p>Each row is one state. Columns are light, dark, and high-contrast dark at 100%. Dense states add light at 200%.</p>",
    ]
    for stem in sorted(groups):
        lines.append("<h2>%s</h2>" % html.escape(stem))
        shots = sorted(groups[stem], key=lambda item: (_ORDER.get(item[0], 9), item[1]))
        lines.append('<div class="row">')
        for theme, scale, name in shots:
            lines.append("<figure>")
            lines.append('<img src="%s" alt="%s">' % (html.escape(name), html.escape(name)))
            lines.append("<figcaption>%s · %s%%</figcaption>" % (html.escape(theme), html.escape(scale)))
            lines.append("</figure>")
        lines.append("</div>")
    (folder / "index.html").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _spawn_child(folder: Path) -> str:
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    env = _with_pytest_path(env)
    done = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "--timeout",
            "900",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m9_5_tour",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    if done.returncode == 0 or (done.returncode in (-11, 139) and passed):
        return ""
    return text


@pytest.mark.timeout(1800)
def test_m9_5_tour(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        misses = _shoot(qapp, tmp_path, folder, "200")
        assert not misses, "\n".join(misses)
        return
    misses = _shoot(qapp, tmp_path, folder, "100")
    child = _spawn_child(folder)
    _write_index(folder)
    assert not misses, "\n".join(misses)
    assert not child, child
    _assert_distinct_shots(folder)
