from __future__ import annotations

import pytest

from app.features.form_builder.integration.form_commands import form_command_set
from app.shell.shortcut_preferences import (
    SHORTCUT_COMMANDS,
    ShortcutCatalog,
    ShortcutCommand,
    ShortcutConflict,
    keep_preview_open_shortcut_id,
)

pytestmark = pytest.mark.unit

_FOCUS_GROUP_1 = "shell.action.view.focusFirstEditorGroup"


def _catalog_with(*extra: ShortcutCommand) -> ShortcutCatalog:
    return ShortcutCatalog.build(SHORTCUT_COMMANDS, (form_command_set() + extra,))


def test_default_tables_have_no_conflicts_including_reserved_rows() -> None:
    catalog = _catalog_with()
    assert catalog.conflicts(catalog.defaults(), include_reserved=True) == ()


def test_every_declared_shadow_is_live_at_defaults() -> None:
    assert _catalog_with().stale_shadows() == ()


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        pytest.param(
            ShortcutCommand("test.row", "Canvas Ctrl+1", "Ctrl+1", "Test", scopes=("canvas",)),
            {
                ShortcutConflict("Ctrl+1", (_FOCUS_GROUP_1, "test.row"), "overlap"),
                ShortcutConflict("Ctrl+1", ("form.layout.horizontal", "test.row"), "overlap"),
            },
            id="canvas-ctrl-1-without-shadow",
        ),
        pytest.param(
            ShortcutCommand("test.row", "Alt+F4 row", "Alt+F4", "Test"),
            {ShortcutConflict("Alt+F4", ("test.row",), "window_manager")},
            id="window-manager-key",
        ),
        pytest.param(
            ShortcutCommand("test.row", "Ctrl+K row", "Ctrl+K", "Test"),
            {
                ShortcutConflict("Ctrl+K", ("shell.action.view.markdownShowSplit", "test.row"), "overlap"),
                ShortcutConflict("Ctrl+K", (keep_preview_open_shortcut_id(), "test.row"), "overlap"),
                ShortcutConflict("Ctrl+K", ("form.preview.twoWidths", "test.row"), "overlap"),
            },
            id="chord-prefix",
        ),
    ],
)
def test_added_row_conflict_is_reported(extra: ShortcutCommand, expected: set[ShortcutConflict]) -> None:
    catalog = _catalog_with(extra)
    assert set(catalog.conflicts(catalog.defaults(), include_reserved=True)) == expected


def test_shadow_on_a_different_key_is_stale() -> None:
    catalog = _catalog_with(
        ShortcutCommand("test.stale", "Stale", "Ctrl+7", "Test", scopes=("canvas",), shadows=(_FOCUS_GROUP_1,))
    )

    assert catalog.stale_shadows() == (("test.stale", _FOCUS_GROUP_1),)
