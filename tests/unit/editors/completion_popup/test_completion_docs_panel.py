"""The docs pane shows signatures, the first paragraph and the owner, nothing internal."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.completion_popup.completion_docs_panel import CompletionDocsPanel  # noqa: E402
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402

pytestmark = pytest.mark.unit

INTERNAL_STRINGS = (
    "possible_descriptor_or_getattr",
    "possible descriptor",
    "runtime_introspection",
    "Runtime introspection",
    "runtime_inspection",
    "approximate",
    "semantic",
    "tier_header",
)


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.mark.parametrize(
    "item",
    [
        CompletionItem(
            label="setGeometry",
            insert_text="setGeometry",
            kind=CompletionKind.METHOD,
            detail="QWidget method",
            signature="setGeometry(self, arg__1: PySide2.QtCore.QRect)\nsetGeometry(self, x: int, y: int, w: int, h: int)",
            source="runtime_introspection",
            engine="runtime_introspection",
            confidence="runtime_inspection",
            side_effect_risk="possible_descriptor_or_getattr",
        ),
        CompletionItem(
            label="join",
            insert_text="join",
            kind=CompletionKind.FUNCTION,
            detail="function • semantic • approximate",
            documentation="join(a, *p)\n\nJoin two or more pathname components.\n\nSecond paragraph.",
            source="semantic",
            side_effect_risk="inspection_only",
        ),
    ],
)
def test_docs_pane_never_shows_internal_strings(item: CompletionItem) -> None:
    panel = CompletionDocsPanel()
    panel.set_item(item)
    panel.set_resolving(True)

    shown = panel.visible_text()

    assert item.label in shown
    for internal in INTERNAL_STRINGS:
        assert internal not in shown
    assert "Second paragraph" not in shown
    assert "arg__1" not in shown and "self" not in shown
