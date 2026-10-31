# pyright: reportAttributeAccessIssue=false
"""M7.0s picker rows, the step-picker pixels, and a badge kind from a new file."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.core import constants  # noqa: E402
from app.features.form_builder.engine.ids import IdAllocator  # noqa: E402
from app.features.form_builder.engine.ui4.defaults import QtClassTable  # noqa: E402
from app.features.form_builder.engine.ui4.reader import read_ui  # noqa: E402
from app.features.form_builder.integration.chrome import chrome_for  # noqa: E402
from app.features.form_builder.qtside.canvas.layers import logic_badges  # noqa: E402
from app.features.form_builder.qtside.canvas.layers.badge_kinds import load_kinds  # noqa: E402
from app.features.form_builder.qtside.canvas.layers import badge_kinds  # noqa: E402
from app.features.form_builder.qtside.pickers.flow import PickContext, PickerSource, _step_page  # noqa: E402
from app.features.form_builder.qtside.pickers.groups_ext import load_groups  # noqa: E402
from app.features.form_builder.qtside.pickers import groups_ext  # noqa: E402
from app.features.form_builder.qtside.pickers.popover import EventPicker  # noqa: E402
from dataclasses import fields  # noqa: E402

from app.features.form_builder.qtside.theme.overlay import OVERLAY_HIGH_CONTRAST, OverlayPalette  # noqa: E402
from app.qt.QtGui import QImage  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402
from tests.form_builder.m5_0s_support import forget_package, make_package  # noqa: E402
from tests.form_builder.qtside.test_m6_1c_connections import _world, connection, form  # noqa: E402
from tests.form_builder.engine.commands._support import open_log  # noqa: E402

pytestmark = pytest.mark.unit

_M7 = Path(__file__).resolve().parents[1] / "fixtures" / "m7"
_SALE = Path(__file__).resolve().parents[1] / "fixtures" / "m6" / "forms" / "sale.ui"
_ROWS = (
    "DO THIS",
    "Close this form",
    "Accept (OK)",
    "Cancel",
    "Clear a field\u2026",
    "Move focus to\u2026",
    "FIELDS",
    "Check all fields",
    "Set a field",
    "Clear fields",
    "Move focus to",
    "SHOW",
    "Show or hide",
    "Enable or disable",
    "Show a message",
    "Ask yes or no",
    "Switch tab or page",
    "WINDOWS",
    "Open another form",
    "Close this form",
    "YOUR CODE",
    "Call a new method\u2026",
    "forms/sale_window.py",
    "Call show_total()",
    "FLOW",
    "Stop here if\u2026",
    "EVERYTHING ELSE",
    "A widget's own action\u2026",
)

_PROBE_GROUP = {
    "probe": """
        from app.features.form_builder.qtside.pickers.flow import Item
        from app.features.form_builder.qtside.pickers.groups_ext import PickerGroup

        def rows(ctx):
            return [Item("header", "", "PROBE", header=True), Item("probe", "", "Probe row")]

        def register(registry):
            registry.add(PickerGroup("probe", 5, "PROBE", rows))
    """,
}

_PROBE_BADGE = {
    "probe": """
        from app.features.form_builder.qtside.canvas.layers.badge_kinds import BadgeKind

        def applies(node, facts):
            return getattr(facts, "sender", "") == "clearButton"

        def sentence(node, facts):
            return "Probe badge"

        def register(registry):
            registry.add(BadgeKind("probe", 0, "P", applies, sentence))
    """,
}


def _sale_context() -> PickContext:
    text = _SALE.read_text(encoding="utf-8")
    doc = read_ui(text, allocator=IdAllocator()).document
    return PickContext(
        doc,
        QtClassTable.shared(),
        PickerSource("clearButton", "clicked"),
        "",
        ("show_total",),
        "forms/sale_window.py",
        "SaleWindow",
        False,
    )


def _argb(image: QImage) -> Tuple[int, int, bytes]:
    if not isinstance(image, QImage):
        image = image.toImage()
    converted = image.convertToFormat(QImage.Format_ARGB32)
    return converted.width(), converted.height(), bytes(converted.constBits())


def test_step_page_rows_match_the_pre_change_list() -> None:
    page = _step_page(_sale_context(), "clicked", False, -1, "")
    assert tuple(item.text for item in page.rows) == _ROWS


def test_step_picker_pixels_match_the_light_snapshot(qapp: QApplication) -> None:
    del qapp
    app = QApplication.instance()
    assert app is not None
    tokens = tokens_from_palette(app.palette(), force_mode=constants.UI_THEME_MODE_LIGHT)
    chrome = chrome_for(tokens)
    host = QWidget()
    host.resize(400, 300)
    host.show()
    picker = EventPicker(host, chrome, lambda gesture: None)
    picker.open_at(host, _sale_context())
    app.processEvents()
    picker.adjustSize()
    app.processEvents()
    grabbed = picker.grab()
    stored = QImage(str(_M7 / "step_picker_light.png"))
    assert _argb(grabbed) == _argb(stored)


def test_a_dummy_group_from_a_new_file_appears_on_the_step_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = make_package(tmp_path, monkeypatch, "m70s_group_probe", _PROBE_GROUP)
    try:
        registry = load_groups(groups_ext, package)
        monkeypatch.setattr(groups_ext, "default_registry", lambda: registry)
        page = _step_page(_sale_context(), "clicked", False, -1, "")
        texts = tuple(item.text for item in page.rows)
        assert "Probe row" in texts
        assert texts.index("Probe row") < texts.index("DO THIS")
        assert texts[-2:] == _ROWS[-2:]
    finally:
        forget_package("m70s_group_probe")


def test_a_dummy_badge_kind_that_sorts_first_wins_the_glyph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = make_package(tmp_path, monkeypatch, "m70s_badge_probe", _PROBE_BADGE)
    try:
        registry = load_kinds(badge_kinds, package)
        monkeypatch.setattr(badge_kinds, "default_registry", lambda: registry)
        log = open_log(form(connection("clearButton", "clicked()", "nameEdit", "clear()")))
        current = log.document.by_name("clearButton")[0]
        static, inputs = _world(log, current)
        logic_badges.forget_badge_memo()
        output = logic_badges.build(static, inputs, None)
        marks = [item.data for item in output.items if isinstance(item.data, tuple) and item.data[0] == "badge"]
        clear = [item for item in marks if item[1] == "clearButton"]
        assert len(clear) == 1
        tip, glyph, count = clear[0][2], clear[0][3], clear[0][4]
        assert glyph == "P"
        assert count == 2
        assert tip.startswith("Probe badge ")
        assert "When clicked" in tip
    finally:
        forget_package("m70s_badge_probe")


def test_feeds_token_is_a_color() -> None:
    default = next(item for item in fields(OverlayPalette) if item.name == "feeds")
    assert default.default == "#6B7280FF"
    assert OVERLAY_HIGH_CONTRAST.feeds == "#000000FF"
