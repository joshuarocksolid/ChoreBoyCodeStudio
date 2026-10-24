# pyright: reportAttributeAccessIssue=false
"""One toast for delete, cut, wrap, unwrap, morph, and remove layout."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import QEvent, QPointF, Qt, QTimer  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtGui import QEnterEvent  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QWidget
from app.features.form_builder.engine.commands.catalog import DeleteNodes, SetProperty
from app.features.form_builder.engine.ui4.values import StringValue
from tests.unit.features.form_builder.test_workbench import _FORM, _open

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.mark.parametrize(
    ("label", "shows"),
    [
        ("Delete", True),
        ("Cut", True),
        ("Wrap", True),
        ("Unwrap", True),
        ("Change layout", True),
        ("Change widget", True),
        ("Break layout", True),
        ("Remove layout", True),
        ("Edit", False),
        ("Move", False),
        ("Rename", False),
    ],
)
def test_a_toast_appears_only_for_the_regret_commands(tmp_path: Path, label: str, shows: bool) -> None:
    parent, surface = _surface(tmp_path, label)
    try:
        _commit(surface, label)
        toast = _toast(surface)
        assert toast.isVisible() is shows
        if shows:
            assert label in _body(toast)
            assert toast.maximumWidth() == 480
            assert toast.width() <= 480
            assert not toast.isWindow()
            undo = toast.findChild(QPushButton, "formBuilder.toastUndo")
            assert undo is not None and undo.text() == "Undo"
            assert undo.focusPolicy() == _no_focus()
            timer = toast.findChild(QTimer, "formBuilder.toastTimer")
            assert timer is not None
            assert timer.interval() == 8000
    finally:
        _close(parent, surface)


def test_undo_on_the_toast_restores_the_deleted_widget(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent, surface = _surface(tmp_path, "undo")
    try:
        held = surface.findChild(QWidget, "formBuilder.design")
        assert held is not None
        held.setFocus()
        _flush()
        _delete_button(surface)
        assert _page_button(surface) is None
        toast = _toast(surface)
        assert toast.isVisible()
        assert qapp.focusWidget() is held
        undo = toast.findChild(QPushButton, "formBuilder.toastUndo")
        assert undo is not None
        QTest.mouseClick(undo, _left())
        _flush()
        assert _page_button(surface) is not None
        assert not toast.isVisible()
        assert qapp.focusWidget() is not undo
    finally:
        _close(parent, surface)


def test_a_later_command_dismisses_the_toast_and_its_undo_does_nothing(tmp_path: Path) -> None:
    parent, surface = _surface(tmp_path, "later")
    try:
        _delete_button(surface)
        toast = _toast(surface)
        undo = toast.findChild(QPushButton, "formBuilder.toastUndo")
        assert undo is not None
        _commit(surface, "Edit", "Form")
        assert not toast.isVisible()
        assert _page_button(surface) is None
        undo.click()
        _flush()
        assert _page_button(surface) is None
    finally:
        _close(parent, surface)


def test_hover_pauses_the_toast(tmp_path: Path) -> None:
    parent, surface = _surface(tmp_path, "hover")
    try:
        _commit(surface, "Wrap")
        toast = _toast(surface)
        timer = toast.findChild(QTimer, "formBuilder.toastTimer")
        assert timer is not None and timer.isActive()
        local = QPointF(4, 4)
        QApplication.sendEvent(toast, QEnterEvent(local, local, local))
        assert not timer.isActive()
        QApplication.sendEvent(toast, QEvent(_event("Leave")))
        assert timer.isActive()
    finally:
        _close(parent, surface)


def _surface(tmp_path: Path, name: str) -> tuple:
    parent = QWidget()
    parent.resize(900, 640)
    surface = _open(parent, _FORM, tmp_path / ("%s.ui" % name))
    surface.resize(900, 640)
    parent.show()
    surface.show()
    _flush()
    return parent, surface


def _commit(surface: QWidget, label: str, name: str = "okButton") -> None:
    session = surface._session  # type: ignore[attr-defined]  # noqa: SLF001
    node = session.document.by_name(name)[0]
    with session.log.transaction(label):
        session.log.execute(SetProperty(node, "toolTip", StringValue(label)))
    _flush()


def _page_button(surface: QWidget) -> object:
    page = surface.page_widget()  # type: ignore[attr-defined]
    assert page is not None
    return page.findChild(QWidget, "okButton")


def _delete_button(surface: QWidget) -> None:
    session = surface._session  # type: ignore[attr-defined]  # noqa: SLF001
    button = session.document.by_name("okButton")[0]
    session.log.execute(DeleteNodes((button,)))
    _flush()


def _toast(surface: QWidget) -> QFrame:
    found = surface.findChild(QFrame, "formBuilder.commandToast")
    assert isinstance(found, QFrame)
    return found


def _body(toast: QFrame) -> str:
    label = toast.findChild(QLabel, "formBuilder.toastText")
    assert label is not None
    return label.text()


def _close(parent: QWidget, surface: QWidget) -> None:
    surface.release()  # type: ignore[attr-defined]
    parent.deleteLater()
    _flush()


def _flush() -> None:
    app = QApplication.instance()
    assert app is not None
    for _ in range(6):
        app.processEvents()


def _left() -> Qt.MouseButton:
    return getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")


def _no_focus() -> Qt.FocusPolicy:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")


def _event(name: str) -> QEvent.Type:
    return getattr(getattr(QEvent, "Type", QEvent), name)
