"""Regression tests for completion popup keyboard navigation at list boundaries."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtCore import QEvent, Qt  # noqa: E402
from PySide2.QtGui import QKeyEvent  # noqa: E402
from PySide2.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from app.editors.completion_popup.completion_controller import (  # noqa: E402
    CompletionController,
)
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402

pytestmark = pytest.mark.unit

_MAX_BOUNDARY_EVENT_FILTER_KEYPRESS_DEPTH = 3


def _item(label: str) -> CompletionItem:
    return CompletionItem(
        label=label,
        insert_text=label,
        kind=CompletionKind.SYMBOL,
        source="test",
    )


def _build_controller(item_count: int = 20) -> tuple[CompletionController, QPlainTextEdit]:
    editor = QPlainTextEdit()
    controller = CompletionController(editor)
    controller.set_widget(editor)
    items = [_item(f"item_{index}") for index in range(item_count)]
    controller.set_items(items, "item")
    controller.popup().show()
    return controller, editor


def _key_event(key: Qt.Key) -> QKeyEvent:
    return QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)


def _navigate_popup_keypresses(controller: CompletionController, key: Qt.Key, count: int) -> None:
    popup = controller.popup()
    for _ in range(count):
        QApplication.sendEvent(popup, _key_event(key))


def _count_event_filter_keypress_depth(controller: CompletionController, key: Qt.Key) -> int:
    depth = 0
    max_depth = 0
    original = CompletionController.eventFilter

    def counting_event_filter(self, watched, event):  # type: ignore[no-untyped-def]
        nonlocal depth, max_depth
        if event.type() == QEvent.KeyPress:
            depth += 1
            max_depth = max(max_depth, depth)
        try:
            return original(self, watched, event)
        finally:
            if event.type() == QEvent.KeyPress:
                depth -= 1

    CompletionController.eventFilter = counting_event_filter  # type: ignore[method-assign]
    try:
        QApplication.sendEvent(controller.popup(), _key_event(key))
    finally:
        CompletionController.eventFilter = original  # type: ignore[method-assign]
    return max_depth


@pytest.mark.parametrize(
    "navigate_key,extra_key,expected_row",
    [
        (Qt.Key_Down, Qt.Key_Down, 19),
        (Qt.Key_Up, Qt.Key_Up, 0),
    ],
)
def test_boundary_navigation_does_not_recurse_via_event_filter(
    qapp,
    navigate_key: Qt.Key,
    extra_key: Qt.Key,
    expected_row: int,
) -> None:
    controller, _editor = _build_controller(item_count=20)
    list_view = controller.popup().list_view()

    if navigate_key == Qt.Key_Down:
        _navigate_popup_keypresses(controller, Qt.Key_Down, 19)
    else:
        list_view.setCurrentIndex(controller.model().index(5, 0))
        _navigate_popup_keypresses(controller, Qt.Key_Up, 5)

    assert list_view.currentIndex().row() == expected_row

    depth = _count_event_filter_keypress_depth(controller, extra_key)

    assert depth <= _MAX_BOUNDARY_EVENT_FILTER_KEYPRESS_DEPTH
    assert list_view.currentIndex().row() == expected_row


@pytest.mark.parametrize("key", [Qt.Key_Down, Qt.Key_Up, Qt.Key_Escape, Qt.Key_Return])
def test_dispatch_popup_key_parity_between_host_and_event_filter(qapp, key: Qt.Key) -> None:
    controller, _editor = _build_controller(item_count=5)
    list_view = controller.popup().list_view()
    if key == Qt.Key_Down:
        _navigate_popup_keypresses(controller, Qt.Key_Down, 4)
    elif key == Qt.Key_Up:
        list_view.setCurrentIndex(controller.model().index(3, 0))

    host_event = _key_event(key)
    assert controller.handle_navigation_event(host_event) is True

    visible_after_host = controller.is_visible()
    row_after_host = list_view.currentIndex().row()

    controller, _editor = _build_controller(item_count=5)
    list_view = controller.popup().list_view()
    if key == Qt.Key_Down:
        _navigate_popup_keypresses(controller, Qt.Key_Down, 4)
    elif key == Qt.Key_Up:
        list_view.setCurrentIndex(controller.model().index(3, 0))

    filter_depth = _count_event_filter_keypress_depth(controller, key)

    assert filter_depth <= _MAX_BOUNDARY_EVENT_FILTER_KEYPRESS_DEPTH
    assert controller.is_visible() is visible_after_host
    assert list_view.currentIndex().row() == row_after_host
