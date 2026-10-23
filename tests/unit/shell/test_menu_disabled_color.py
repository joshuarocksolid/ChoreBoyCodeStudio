"""Disabled shell menu rows use muted text in every theme."""

from __future__ import annotations

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.shell.style_sheet_sections_chrome import shell_section_main_window_menus  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_MODES = ("light", "dark", "high_contrast_light", "high_contrast_dark")


def _block(sheet: str, header: str) -> str:
    start = sheet.index(header)
    return sheet[start : sheet.index("}", start)]


def test_disabled_menu_rows_use_muted_text(qapp) -> None:  # type: ignore[no-untyped-def]
    for mode in _MODES:
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        sheet = shell_section_main_window_menus(tokens)
        assert tokens.text_muted != tokens.text_primary
        assert tokens.text_muted in _block(sheet, "QMenu::item:disabled")
        assert tokens.text_primary in _block(sheet, "QMenu::item:selected")
        assert "color:" not in _block(sheet, "QMenu::item {")
