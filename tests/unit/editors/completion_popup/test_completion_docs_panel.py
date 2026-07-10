"""Unit tests for completion popup documentation panel."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication  # noqa: E402

from app.core.completion_tier import TIER_HEADER_SIDE_EFFECT  # noqa: E402
from app.editors.completion_popup.completion_docs_panel import CompletionDocsPanel  # noqa: E402
from app.intelligence.completion_models import CompletionItem, CompletionKind  # noqa: E402
from app.shell.theme_tokens import ShellThemeTokens  # noqa: E402

pytestmark = pytest.mark.unit

_TOKENS = ShellThemeTokens(
    window_bg="#1F2428",
    panel_bg="#262C33",
    editor_bg="#1B1F23",
    text_primary="#E9ECEF",
    text_muted="#ADB5BD",
    border="#3C434A",
    accent="#5B8CFF",
    gutter_bg="#1F2428",
    gutter_text="#6C757D",
    line_highlight="#252B33",
    popup_bg="#262C33",
    popup_border="#3C434A",
    is_dark=True,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


@pytest.fixture()
def panel(qapp) -> CompletionDocsPanel:  # type: ignore[no-untyped-def]
    widget = CompletionDocsPanel()
    widget.apply_theme(_TOKENS)
    widget.show()
    return widget


def _item(
    label: str,
    *,
    source: str = "static_api_index",
    documentation: str = "",
    signature: str = "",
    detail: str = "",
) -> CompletionItem:
    return CompletionItem(
        label=label,
        insert_text=label,
        kind=CompletionKind.FUNCTION,
        detail=detail,
        documentation=documentation,
        signature=signature,
        source=source,
        engine="api_index",
        confidence="static",
    )


def test_set_item_renders_documentation_and_human_provenance(panel: CompletionDocsPanel) -> None:
    panel.set_item(
        _item(
            "getcwd",
            documentation="Return the current working directory.",
            signature="getcwd()",
            detail="os stdlib member",
        )
    )

    assert panel._name_label.text() == "getcwd"
    assert panel._signature_label.text() == "getcwd()"
    assert "Return the current working directory." in panel._doc_body.toPlainText()
    assert panel._provenance_label.text() == "Indexed API"


def test_set_item_shows_detail_when_documentation_missing(panel: CompletionDocsPanel) -> None:
    panel.set_item(_item("abc", detail="os stdlib member"))

    assert panel._detail_label.isVisible() or "os stdlib member" in panel._doc_body.toPlainText()


def test_set_resolving_shows_loading_text(panel: CompletionDocsPanel) -> None:
    panel.set_item(_item("sparse", detail="os stdlib member"))
    panel.set_resolving(True)

    assert "Loading documentation" in panel._doc_body.toPlainText()


def test_set_item_clears_stuck_resolving_state(panel: CompletionDocsPanel) -> None:
    """Selecting a non-resolvable item must not keep the prior loading banner."""

    panel.set_item(
        _item(
            "resolvable",
            source="semantic",
            detail="waiting for docs",
        )
    )
    panel.set_resolving(True)
    assert "Loading documentation" in panel._doc_body.toPlainText()

    panel.set_item(_item("plain", detail="already complete"))

    body = panel._doc_body.toPlainText()
    assert "Loading documentation" not in body
    assert "already complete" in body or panel._detail_label.text() == "already complete"


def test_tier_header_selection_keeps_previous_item(panel: CompletionDocsPanel) -> None:
    panel.set_item(_item("getcwd", documentation="Docs stay visible."))
    header = CompletionItem(
        label="Indexed suggestions",
        insert_text="",
        kind=CompletionKind.TEXT,
        source="tier_header",
        confidence="unsupported",
        side_effect_risk=TIER_HEADER_SIDE_EFFECT,
    )

    panel.set_item(header)

    assert panel._name_label.text() == "getcwd"
    assert "Docs stay visible." in panel._doc_body.toPlainText()


def test_set_item_none_hides_content(panel: CompletionDocsPanel) -> None:
    panel.set_item(_item("getcwd", documentation="Docs"))
    panel.set_item(None)

    assert not panel._name_label.isVisible()
