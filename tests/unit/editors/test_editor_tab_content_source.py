"""EditorTabState delegates text and dirty state to an attached content source."""

from __future__ import annotations

import pytest

from app.editors.editor_tab import EditorTabState

pytestmark = pytest.mark.unit


class _Source:
    def __init__(self, text: str, *, dirty: bool) -> None:
        self.text = text
        self.dirty = dirty
        self.saved: str | None = None
        self._revision = 1

    def current_text(self) -> str:
        return self.text

    def is_dirty(self) -> bool:
        return self.dirty

    def mark_saved(self, saved_text: str) -> None:
        self.saved = saved_text
        self.dirty = False

    def revision(self) -> int:
        return self._revision

    def subscribe_changed(self, listener: object) -> object:
        del listener
        return lambda: None


def _tab(source: _Source | None = None) -> EditorTabState:
    return EditorTabState(
        file_path="/tmp/form.ui",
        display_name="form.ui",
        original_content="old",
        current_content="stored",
        content_source=source,
    )


def test_current_content_and_dirty_delegate_to_the_source() -> None:
    source = _Source("from-source", dirty=True)
    tab = _tab(source)

    assert tab.current_content == "from-source"
    assert tab.is_dirty is True


def test_update_content_rejects_a_sourced_tab() -> None:
    tab = _tab(_Source("from-source", dirty=True))

    with pytest.raises(ValueError):
        tab.update_content("typed")


def test_mark_saved_passes_the_source_text() -> None:
    source = _Source("serialized", dirty=True)
    tab = _tab(source)

    tab.mark_saved()

    assert source.saved == "serialized"
    assert tab.original_content == "serialized"
    assert tab.is_dirty is False
