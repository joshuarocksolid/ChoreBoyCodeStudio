# pyright: reportAttributeAccessIssue=false
"""Form toolbar labels stay readable in dark and high-contrast dark."""

from __future__ import annotations

import pytest

from app.core.constants import UI_THEME_MODE_HIGH_CONTRAST_DARK
from app.features.form_builder.integration.workbench import FormToolbar
from app.qt.QtGui import QColor, QPalette
from app.qt.QtWidgets import QWidget
from app.shell.theme_tokens import tokens_from_palette

pytestmark = [pytest.mark.usefixtures("qapp"), pytest.mark.unit]


@pytest.mark.parametrize("mode", ["dark", UI_THEME_MODE_HIGH_CONTRAST_DARK])
def test_toolbar_labels_take_their_ink_from_the_theme(mode: str, qapp) -> None:  # type: ignore[no-untyped-def]
    tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
    parent = QWidget()
    bar = FormToolbar(
        parent,
        on_design=lambda: None,
        on_xml=lambda _checked: None,
        on_undo=lambda: None,
        on_redo=lambda: None,
    )
    bar.apply_theme(tokens)
    ink = bar.tab_order.palette().color(QPalette.ColorRole.ButtonText).name().lower()
    quiet = bar.text_size.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name().lower()
    assert ink == QColor(tokens.text_primary).name().lower()
    assert quiet == QColor(tokens.text_muted).name().lower()
    assert tokens.text_primary in bar.styleSheet()
    assert tokens.text_muted in bar.styleSheet()
    parent.deleteLater()
