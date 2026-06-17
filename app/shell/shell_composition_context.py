"""Composition context and timer registry for main-window shell wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from PySide2.QtCore import QTimer

from app.core.models import CapabilityProbeReport
from app.persistence.autosave_store import AutosaveStore
from app.persistence.local_history_store import LocalHistoryStore


@dataclass
class ShellCompositionTimers:
    """All composition-owned QTimers for centralized lifecycle management."""

    project_tree_preview_click: QTimer
    auto_save_to_file: QTimer
    realtime_lint: QTimer
    outline_refresh: QTimer
    run_event: QTimer
    repl_event: QTimer
    external_change_poll: QTimer
    restore_project: QTimer
    auto_start_repl: QTimer
    runtime_probe: QTimer
    startup_probe_refresh: QTimer

    def stop_all(self) -> None:
        self.project_tree_preview_click.stop()
        self.auto_save_to_file.stop()
        self.realtime_lint.stop()
        self.outline_refresh.stop()
        self.run_event.stop()
        self.repl_event.stop()
        self.external_change_poll.stop()
        self.restore_project.stop()
        self.auto_start_repl.stop()
        self.runtime_probe.stop()
        self.startup_probe_refresh.stop()


@dataclass
class ShellCompositionContext:
    """Holds wired shell collaborators during phased main-window composition."""

    window: Any
    startup_report: Optional[CapabilityProbeReport]
    state_root: str | None
    local_history_store: LocalHistoryStore | None = None
    autosave_store: AutosaveStore | None = None
    timers: ShellCompositionTimers | None = None

    @property
    def w(self) -> Any:
        return self.window


__all__ = ["ShellCompositionContext", "ShellCompositionTimers"]
