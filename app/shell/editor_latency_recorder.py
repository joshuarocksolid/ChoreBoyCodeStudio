"""Shell-owned editor operation latency recording."""

from __future__ import annotations

from collections.abc import Callable

from app.bootstrap.logging_setup import get_subsystem_logger
from app.core.metrics import RollingLatencyTracker
from app.editors.code_editor_widget import CodeEditorWidget

LANGUAGE_ATTACH_WARNING_MS = 80.0
THEME_APPLY_WARNING_MS = 90.0
OVERLAY_REFRESH_WARNING_MS = 24.0


class EditorLatencyRecorder:
    """Records editor paint-path latencies at the shell/session boundary."""

    def __init__(self) -> None:
        self._logger = get_subsystem_logger("shell.editor_latency")
        self._logging_enabled = False
        self._language_attach_latency = RollingLatencyTracker(
            "editor_language_attach_ms",
            window_size=120,
            snapshot_interval=30,
        )
        self._theme_apply_latency = RollingLatencyTracker(
            "editor_theme_apply_ms",
            window_size=120,
            snapshot_interval=30,
        )
        self._overlay_refresh_latency = RollingLatencyTracker(
            "editor_overlay_refresh_ms",
            window_size=180,
            snapshot_interval=75,
        )

    def set_logging_enabled(self, enabled: bool) -> None:
        self._logging_enabled = enabled

    def attach_to_editor(self, editor_widget: CodeEditorWidget) -> None:
        editor_widget.set_operation_latency_sink(self._record_operation_latency)

    def _record_operation_latency(
        self,
        metric_name: str,
        elapsed_ms: float,
        file_path: str | None = None,
    ) -> None:
        tracker = {
            "editor_language_attach_ms": self._language_attach_latency,
            "editor_theme_apply_ms": self._theme_apply_latency,
            "editor_overlay_refresh_ms": self._overlay_refresh_latency,
        }.get(metric_name)
        if tracker is None:
            return
        snapshot = tracker.record(elapsed_ms)
        if not self._logging_enabled:
            return
        file_label = file_path or "<unsaved>"
        warning_threshold_ms = {
            "editor_language_attach_ms": LANGUAGE_ATTACH_WARNING_MS,
            "editor_theme_apply_ms": THEME_APPLY_WARNING_MS,
            "editor_overlay_refresh_ms": OVERLAY_REFRESH_WARNING_MS,
        }[metric_name]
        if elapsed_ms > warning_threshold_ms:
            self._logger.warning(
                "Editor latency warning: file=%s metric=%s elapsed_ms=%.2f",
                file_label,
                metric_name,
                elapsed_ms,
            )
            return
        if snapshot is not None:
            self._logger.info(
                "Editor latency telemetry: file=%s metric=%s count=%s p50_ms=%.2f p95_ms=%.2f max_ms=%.2f",
                file_label,
                snapshot.metric_name,
                snapshot.count,
                snapshot.p50_ms,
                snapshot.p95_ms,
                snapshot.max_ms,
            )


def attach_editor_latency_recorder(
    editor_widget: CodeEditorWidget,
    *,
    recorder: EditorLatencyRecorder,
    logging_enabled: bool,
) -> None:
    """Wire one editor widget to the shared shell latency recorder."""
    recorder.set_logging_enabled(logging_enabled)
    recorder.attach_to_editor(editor_widget)
