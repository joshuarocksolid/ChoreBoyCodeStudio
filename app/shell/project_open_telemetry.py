"""Structured timing telemetry for project open phases."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time


@dataclass
class ProjectOpenTelemetry:
    """Accumulates per-phase timings for one project-open attempt."""

    project_root: str = ""
    started_at: float = field(default_factory=time.perf_counter)
    enumerate_ms: float = 0.0
    tree_ms: float = 0.0
    session_restore_ms: float = 0.0
    entry_count: int = 0

    def mark_enumerate(self, *, entry_count: int) -> None:
        self.entry_count = entry_count

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started_at) * 1000.0

    def log(self, logger: logging.Logger) -> None:
        logger.info(
            "Project open telemetry: root=%s files=%s total_ms=%.2f "
            "enumerate_ms=%.2f tree_ms=%.2f session_restore_ms=%.2f",
            self.project_root,
            self.entry_count,
            self.elapsed_ms(),
            self.enumerate_ms,
            self.tree_ms,
            self.session_restore_ms,
        )
