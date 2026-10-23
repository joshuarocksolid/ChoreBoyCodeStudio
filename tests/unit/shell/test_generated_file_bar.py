"""Opening a generated module shows the banner and starts read-only."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtWidgets import QPlainTextEdit, QPushButton  # noqa: E402
from app.shell.editor_tab_page import EditorTabPage  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit


def _edit_button(page: EditorTabPage) -> QPushButton:
    for child in page.generated_bar.findChildren(QPushButton):
        if child.objectName() == "shell.generatedFileBar.editAnyway":
            return child
    raise AssertionError("Edit anyway is missing")


def test_edit_anyway_unlocks_only_that_tab(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    editor = QPlainTextEdit()
    page = EditorTabPage(editor, buffer_id="buf")
    page.generated_bar.apply_theme(tokens_from_palette(qapp.palette(), force_mode="light"))
    page.show_generated(str(tmp_path / "ui_invoice.py"), "")
    assert editor.isReadOnly()
    assert "invoice.ui" in page.generated_bar.message()
    assert "invoice_window.py" in page.generated_bar.message()
    out = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    page.resize(960, 72)
    page.show()
    qapp.processEvents()
    assert _edit_button(page).isVisible()
    page.grab().save(str(out / "generated-file-banner.png"))
    page.make_generated_editable()
    assert not editor.isReadOnly()
    assert not _edit_button(page).isVisible()
    page.deleteLater()
