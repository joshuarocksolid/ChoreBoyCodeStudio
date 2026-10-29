# pyright: reportAttributeAccessIssue=false
"""The page chip names a main window instead of saying it has no layout."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.integration.chrome_text import page_chip_text
from app.features.form_builder.qtside.canvas.core.words import page_chip_label
from tests.form_builder.qtside.support import open_session

pytestmark = pytest.mark.unit


def test_a_main_window_chip_names_the_window_kind() -> None:
    session = open_session(build_template_ui("main_window", "shop_window"))
    assert page_chip_label(session.document, "Form") == "shop_window · Main window"
    assert page_chip_text(session.document, "Form") == ("shop_window", "Main window")

