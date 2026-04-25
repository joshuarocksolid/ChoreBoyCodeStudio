"""Facade around editor startup capability refresh hooks."""

from __future__ import annotations

from typing import Callable

import run_editor

from app.core.models import CapabilityProbeReport


class StartupCapabilityFacade:
    """Keeps shell code decoupled from the repo-root `run_editor` module."""

    def set_refresh_callback(self, callback: Callable[[CapabilityProbeReport], None] | None) -> None:
        run_editor.set_startup_report_refresh_callback(callback)

    def refresh_report(self) -> CapabilityProbeReport:
        return run_editor.refresh_startup_capability_report()
