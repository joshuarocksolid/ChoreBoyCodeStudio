"""EditorTabState delegates text and dirty state to an attached content source."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editors.editor_manager import EditorManager
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


def test_mark_saved_passes_the_written_text_instead_of_rereading() -> None:
    source = _Source("later", dirty=True)
    tab = _tab(source)

    tab.mark_saved(saved_text="written")

    assert source.saved == "written"
    assert tab.original_content == "written"


def test_save_tab_marks_the_text_it_wrote(tmp_path: Path) -> None:
    file_path = tmp_path / "form.ui"
    file_path.write_text("old", encoding="utf-8")
    source = _Source("first", dirty=True)
    calls = {"n": 0}

    def current_text() -> str:
        calls["n"] += 1
        return "first" if calls["n"] == 1 else "second"

    source.current_text = current_text  # type: ignore[method-assign]
    manager = EditorManager()
    tab = manager.open_file(str(file_path)).tab
    tab.content_source = source  # type: ignore[assignment]

    manager.save_tab(tab.file_path)

    assert file_path.read_text(encoding="utf-8") == "first"
    assert source.saved == "first"
