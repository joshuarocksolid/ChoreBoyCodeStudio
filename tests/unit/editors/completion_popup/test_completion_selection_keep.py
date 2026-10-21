"""A later completion source must not move the highlight on an open list."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QApplication  # noqa: E402

from app.editors.completion_popup.completion_controller import CompletionController  # noqa: E402
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402

pytestmark = pytest.mark.unit


def _items() -> list[CompletionItem]:
    return [
        CompletionItem(label="alpha", insert_text="alpha", kind=CompletionKind.METHOD),
        CompletionItem(label="beta", insert_text="beta", kind=CompletionKind.METHOD),
    ]


def test_update_keeps_the_highlight_when_the_user_has_not_moved() -> None:
    if QApplication.instance() is None:
        QApplication([])
    controller = CompletionController()
    controller._set_base(_items(), key=("expr", 0, ""), root="")
    assert controller._refilter("", event="open") is True
    opened = controller.current_item()
    assert opened is not None and opened.label == "alpha"
    controller._popup.show()
    controller._popup.list_view().select_row(1)
    controller._user_moved_selection = False
    assert controller._refilter("", event="update") is True
    current = controller.current_item()
    assert current is not None
    assert current.label == "beta"
    controller._popup.hide()


def test_filter_still_jumps_to_the_best_match() -> None:
    if QApplication.instance() is None:
        QApplication([])
    controller = CompletionController()
    controller._set_base(_items(), key=("expr", 0, ""), root="")
    assert controller._refilter("", event="open") is True
    controller._popup.show()
    controller._popup.list_view().select_row(1)
    controller._user_moved_selection = False
    assert controller._refilter("", event="filter") is True
    current = controller.current_item()
    assert current is not None
    assert current.label == "alpha"
    controller._popup.hide()
