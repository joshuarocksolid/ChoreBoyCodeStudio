# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""KEY-001 over the command table and the lanes' keys_ext rows together."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator

import pytest

from app.features.form_builder.integration import keys_ext
from app.shell.shortcut_preferences import SHORTCUT_COMMANDS
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = [pytest.mark.unit]

_PACKAGE = "m5_keys_probe"

_GOOD = """
    def register(registry):
        registry.key("probe.focusActions", "Focus actions", "Alt+5", ("form_tab",))
        registry.key("probe.copyLook", "Copy look", "Ctrl+Alt+K", ("canvas",))
"""

_BAD = """
    def register(registry):
        registry.key("probe.zoomTwin", "Zoom twin", "Ctrl+9", ("form_tab",))
        registry.key("probe.findTwin", "Find twin", "Ctrl+F", ("form_tab",))
        registry.key("probe.wm", "Window manager", "Alt+F4", ("form_tab",))
        registry.key("probe.inert", "Inert", "Ctrl+H", ("canvas",))
        registry.key("form.action.insert", "Insert again", "Ctrl+Alt+J", ("canvas",))
"""


def _shell_map() -> Dict[str, str]:
    return {command.action_id: command.default_shortcut for command in SHORTCUT_COMMANDS}


@pytest.fixture()
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    yield make_package(tmp_path, monkeypatch, _PACKAGE, {"a_good": _GOOD, "b_bad": _BAD})
    forget_package(_PACKAGE)


def test_every_keys_ext_module_in_the_product_keeps_the_table_free_of_collisions() -> None:
    assert keys_ext.collisions(_shell_map()) == ()


def test_a_module_dropped_into_the_package_is_listed_and_its_collisions_are_named(package) -> None:  # type: ignore[no-untyped-def]
    registry = keys_ext.load_keys(package)
    assert [command.command_id for command in keys_ext.extra_commands(registry)][:2] == [
        "probe.focusActions",
        "probe.copyLook",
    ]
    problems = keys_ext.collisions(_shell_map(), registry)
    text = "\n".join(problems)
    assert "form.action.zoomToFit and probe.zoomTwin both use Ctrl+9" in text
    assert "probe.findTwin collides with shell.action.edit.find on Ctrl+F" in text
    assert "probe.wm uses forbidden key Alt+F4" in text
    assert "probe.inert uses Ctrl+H" in text
    assert "form.action.insert is already a row" in text
    assert "probe.focusActions" not in text and "probe.copyLook" not in text


def test_lane_rows_join_the_settings_list_once_per_key(package) -> None:  # type: ignore[no-untyped-def]
    registry = keys_ext.load_keys(package)
    ids = [row[0] for row in keys_ext.extra_shortcut_rows(registry)]
    assert "probe.focusActions" in ids and "probe.copyLook" in ids
    assert "probe.zoomTwin" not in ids  # Ctrl+9 is already listed by the table
    assert all(command.command_id in {c.command_id for c in keys_ext.all_commands(registry)} for command in keys_ext.extra_commands(registry))
