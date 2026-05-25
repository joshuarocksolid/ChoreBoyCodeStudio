"""Unit tests for settings dialog tab state helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.shell.settings_dialog import SettingsDialog
from app.shell.settings_dialog_state import GeneralTabState
from app.shell.settings_models import EditorSettingsSnapshot

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_general_tab_state_roundtrips_snapshot_fields() -> None:
    snapshot = EditorSettingsSnapshot(
        tab_width=6,
        font_size=15,
        font_family="Courier New",
        indent_style="tabs",
        indent_size=3,
        detect_indentation_from_file=True,
        format_on_save=True,
        organize_imports_on_save=False,
        trim_trailing_whitespace_on_save=True,
        insert_final_newline_on_save=False,
        enable_preview=False,
        auto_save=True,
        exit_behavior="keep_unsaved",
        hover_tooltip_enabled=False,
        auto_reindent_flat_python_paste=True,
        completion_enabled=False,
        completion_auto_trigger=True,
        completion_min_chars=4,
        diagnostics_realtime=False,
        quick_fixes_enabled=True,
        quick_fix_require_preview_for_multifile=False,
        cache_enabled=False,
        incremental_indexing=True,
        metrics_logging_enabled=False,
        force_full_reindex_on_open=True,
        theme_mode="dark",
        ui_font_weight="medium",
        auto_open_console_on_run_output=True,
        auto_open_problems_on_run_failure=False,
        highlighting_adaptive_mode="reduced",
        highlighting_reduced_threshold_chars=12000,
        highlighting_lexical_only_threshold_chars=24000,
    )

    state = GeneralTabState.from_snapshot(snapshot)
    roundtripped = EditorSettingsSnapshot(**state.to_snapshot_fields())

    for field_name in GeneralTabState.__dataclass_fields__:
        assert getattr(roundtripped, field_name) == getattr(snapshot, field_name)


def test_settings_dialog_snapshot_preserves_highlighting_passthrough_fields() -> None:
    snapshot = EditorSettingsSnapshot(
        tab_width=4,
        highlighting_adaptive_mode="reduced",
        highlighting_reduced_threshold_chars=12000,
        highlighting_lexical_only_threshold_chars=24000,
    )
    dialog = SettingsDialog(snapshot)
    dialog._tab_width_input.setValue(8)

    captured = dialog.snapshot()
    assert captured.tab_width == 8
    assert captured.highlighting_adaptive_mode == "reduced"
    assert captured.highlighting_reduced_threshold_chars == 12000
    assert captured.highlighting_lexical_only_threshold_chars == 24000
