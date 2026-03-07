"""Unit tests for ProjectTreeWidget deleteRequested signal on Delete/Backspace."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtTest import QTest  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from app.project.project_tree_widget import ProjectTreeWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp():  # type: ignore[no-untyped-def]
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def tree_widget():  # type: ignore[no-untyped-def]
    widget = ProjectTreeWidget()
    return widget


def test_delete_key_emits_delete_requested(tree_widget: ProjectTreeWidget) -> None:
    received: list[bool] = []
    tree_widget.deleteRequested.connect(lambda: received.append(True))
    QTest.keyPress(tree_widget, Qt.Key_Delete)
    assert received == [True]


def test_backspace_key_emits_delete_requested(tree_widget: ProjectTreeWidget) -> None:
    received: list[bool] = []
    tree_widget.deleteRequested.connect(lambda: received.append(True))
    QTest.keyPress(tree_widget, Qt.Key_Backspace)
    assert received == [True]


def test_other_key_does_not_emit_delete_requested(tree_widget: ProjectTreeWidget) -> None:
    received: list[bool] = []
    tree_widget.deleteRequested.connect(lambda: received.append(True))
    QTest.keyPress(tree_widget, Qt.Key_A)
    assert received == []
