"""Dialog-owned settings state grouped by tab for snapshot capture/apply."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from app.shell.settings_models import EditorSettingsSnapshot


@dataclass(frozen=True)
class GeneralTabState:
    """Editable General-tab fields plus intelligence highlighting passthrough."""

    tab_width: int
    font_size: int
    font_family: str
    indent_style: str
    indent_size: int
    detect_indentation_from_file: bool
    format_on_save: bool
    organize_imports_on_save: bool
    trim_trailing_whitespace_on_save: bool
    insert_final_newline_on_save: bool
    enable_preview: bool
    auto_save: bool
    exit_behavior: str
    hover_tooltip_enabled: bool
    auto_reindent_flat_python_paste: bool
    completion_enabled: bool
    completion_auto_trigger: bool
    completion_min_chars: int
    diagnostics_realtime: bool
    quick_fixes_enabled: bool
    quick_fix_require_preview_for_multifile: bool
    cache_enabled: bool
    incremental_indexing: bool
    metrics_logging_enabled: bool
    force_full_reindex_on_open: bool
    theme_mode: str
    ui_font_weight: str
    dark_chrome_palette: str
    auto_open_console_on_run_output: bool
    auto_open_problems_on_run_failure: bool
    highlighting_adaptive_mode: str
    highlighting_reduced_threshold_chars: int
    highlighting_lexical_only_threshold_chars: int

    @classmethod
    def from_snapshot(cls, snapshot: EditorSettingsSnapshot) -> GeneralTabState:
        """Extract General-tab owned fields from an editor settings snapshot."""
        return cls(**{field.name: getattr(snapshot, field.name) for field in fields(cls)})

    def to_snapshot_fields(self) -> dict[str, Any]:
        """Return ``EditorSettingsSnapshot`` keyword arguments for General-tab fields."""
        return asdict(self)
