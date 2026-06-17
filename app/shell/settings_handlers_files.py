"""Files and local history tab handlers for SettingsDialog."""

from __future__ import annotations

from app.project.file_excludes import DEFAULT_EXCLUDE_PATTERNS
from app.shell.settings_models import EditorSettingsSnapshot, SETTINGS_SCOPE_GLOBAL, SETTINGS_SCOPE_PROJECT


class SettingsFilesHandlersMixin:
    """Mixin for settings file excludes and local history handlers."""

    def _file_exclude_patterns_snapshot(self) -> list[str]:
        patterns: list[str] = []
        for i in range(self._file_excludes_list.count()):
            item = self._file_excludes_list.item(i)
            if item is not None:
                text = item.text().strip()
                if text:
                    patterns.append(text)
        return patterns

    def _handle_add_file_exclude(self) -> None:
        text = self._file_exclude_input.text().strip()
        if not text:
            return
        for part in text.split(","):
            pattern = part.strip()
            if not pattern:
                continue
            existing = [
                self._file_excludes_list.item(i).text()
                for i in range(self._file_excludes_list.count())
                if self._file_excludes_list.item(i) is not None
            ]
            if pattern not in existing:
                self._file_excludes_list.addItem(pattern)
        self._file_exclude_input.clear()

    def _handle_remove_file_exclude(self) -> None:
        selected = self._file_excludes_list.currentRow()
        if selected >= 0:
            self._file_excludes_list.takeItem(selected)

    def _handle_reset_file_excludes(self) -> None:
        self._file_excludes_list.clear()
        baseline_patterns = DEFAULT_EXCLUDE_PATTERNS
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            baseline_patterns = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL].file_exclude_patterns
        for pattern in baseline_patterns:
            self._file_excludes_list.addItem(pattern)

    def _local_history_exclude_patterns_snapshot(self) -> list[str]:
        patterns: list[str] = []
        for i in range(self._local_history_excludes_list.count()):
            item = self._local_history_excludes_list.item(i)
            if item is None:
                continue
            text = item.text().strip()
            if text:
                patterns.append(text)
        return patterns

    def _handle_add_local_history_exclude(self) -> None:
        text = self._local_history_exclude_input.text().strip()
        if not text:
            return
        existing = {
            self._local_history_excludes_list.item(i).text()
            for i in range(self._local_history_excludes_list.count())
            if self._local_history_excludes_list.item(i) is not None
        }
        for part in text.split(","):
            pattern = part.strip()
            if pattern and pattern not in existing:
                self._local_history_excludes_list.addItem(pattern)
                existing.add(pattern)
        self._local_history_exclude_input.clear()

    def _handle_remove_local_history_exclude(self) -> None:
        selected = self._local_history_excludes_list.currentRow()
        if selected >= 0:
            self._local_history_excludes_list.takeItem(selected)

    def _handle_reset_local_history_settings(self) -> None:
        baseline = EditorSettingsSnapshot()
        if self._active_scope == SETTINGS_SCOPE_PROJECT:
            baseline = self._scope_snapshots[SETTINGS_SCOPE_GLOBAL]
        self._local_history_max_checkpoints_input.setValue(baseline.local_history_max_checkpoints_per_file)
        self._local_history_retention_days_input.setValue(baseline.local_history_retention_days)
        self._local_history_max_tracked_file_kb_input.setValue(
            max(1, int((baseline.local_history_max_tracked_file_bytes + 1023) / 1024))
        )
        self._local_history_excludes_list.clear()
        for pattern in baseline.local_history_exclude_patterns:
            self._local_history_excludes_list.addItem(pattern)
