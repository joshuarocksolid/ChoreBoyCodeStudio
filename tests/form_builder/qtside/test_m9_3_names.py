# pyright: reportAttributeAccessIssue=false
"""Every visible interactive form-builder widget has a name a screen reader can read."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.features.form_builder.qtside.dialogs.from_table import FromTableDialog  # noqa: E402
from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtTest import QTest  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QWidget,
)
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _key, _mods  # noqa: E402
from tests.form_builder.qtside.test_m7_8a_panel import _pump, open_invoice  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(180)]

_CONTAINERS = (QWidget, QFrame, QScrollArea, QSplitter, QStackedWidget, QTabWidget, QGroupBox)


def _spoken(widget: QWidget) -> str:
    named = (widget.accessibleName() or "").strip()
    if named:
        return named
    if widget.isWindow():
        title = str(widget.windowTitle() or "").strip()
        if title:
            return title
    if isinstance(widget, QAbstractButton):
        text = str(widget.text() or "").replace("&", "").strip()
        if text:
            return text
    if isinstance(widget, QGroupBox):
        title = str(widget.title() or "").strip()
        if title:
            return title
    window = widget.window()
    for label in window.findChildren(QLabel):
        buddy = label.buddy()
        if buddy is widget and str(label.text() or "").strip():
            return str(label.text()).replace("&", "").strip()
    return ""


def _focusable(root: QWidget) -> list:
    no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
    widgets = [root]
    widgets.extend(root.findChildren(QWidget))
    found = []
    for widget in widgets:
        if not widget.isVisible():
            continue
        if widget.focusPolicy() == no_focus:
            continue
        found.append(widget)
    return found


def _unnamed(root: QWidget) -> list:
    missing = []
    for widget in _focusable(root):
        if _spoken(widget):
            continue
        if type(widget) in _CONTAINERS:
            continue
        missing.append(widget.objectName() or type(widget).__name__)
    return missing


def test_open_surfaces_name_every_interactive_widget(tmp_path: Path, qapp: QApplication) -> None:
    window, surface, guard = open_invoice(tmp_path, qapp)
    dialog = None
    try:
        missing = _unnamed(surface)
        assert missing == [], missing
        focus = QApplication.focusWidget() or window
        QTest.keyClick(focus, _key("Key_R"), _mods("Control"))  # type: ignore[arg-type]
        _pump(qapp)
        picker = window.findChild(QWidget, "formBuilder.goToWidget")
        assert picker is not None and picker.isVisible()
        search = picker.findChild(QWidget, "formBuilder.goToWidgetSearch")
        assert search is not None
        first = (search.accessibleDescription() or "").strip()
        assert first
        QTest.keyClick(search, _key("Key_Down"))  # type: ignore[arg-type]
        _pump(qapp)
        second = (search.accessibleDescription() or "").strip()
        assert second
        assert second != first
        missing = _unnamed(picker)
        assert missing == [], missing
        QTest.keyClick(search, _key("Key_Escape"))  # type: ignore[arg-type]
        _pump(qapp)
        window.activateWindow()
        surface.focus_primary()  # type: ignore[attr-defined]
        _pump(qapp)
        focus = QApplication.focusWidget() or window
        QTest.keyClick(focus, _key("Key_D"), _mods("Control", "Shift"))  # type: ignore[arg-type]
        _pump(qapp)
        landed = QApplication.focusWidget()
        assert landed is not None and landed.objectName() == "formBuilder.data.connect"
        missing = _unnamed(surface)
        assert missing == [], missing
        dialog = FromTableDialog(
            project_root=str(tmp_path),
            stem="invoice",
            chrome=chrome_for(tokens_from_palette(qapp.palette())),
            date_format="yyyy-MM-dd",
            name_reason=lambda: None,
            parent=window,
        )
        dialog.show()
        _pump(qapp)
        missing = _unnamed(dialog)
        assert missing == [], missing
        assert guard.seen == []
    finally:
        if dialog is not None:
            dialog.close()
        from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

        _close(window, qapp, guard)
