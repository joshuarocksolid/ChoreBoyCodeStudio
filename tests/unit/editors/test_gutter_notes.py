"""The code gutter can mark a line the builder kept as written."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.code_editor_widget import CodeEditorWidget  # noqa: E402

pytestmark = pytest.mark.unit


def test_a_kept_note_widens_the_gutter(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    editor = CodeEditorWidget()
    editor.setPlainText("alpha\nbeta\n")
    before = editor.line_number_area_width()
    editor.set_gutter_notes({2: "Kept as is"})
    assert editor.line_number_area_width() > before
    editor.set_gutter_notes({})
    assert editor.line_number_area_width() == before
    editor.deleteLater()
