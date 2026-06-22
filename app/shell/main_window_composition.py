"""Service and workflow wiring for the main editor window shell."""

from __future__ import annotations

from typing import Optional

from app.core.models import CapabilityProbeReport
from app.shell.main_window_composition_phases import (
    connect_composition_timers,
    create_composition_timers,
    install_editor_project_wiring,
    install_editors,
    install_intelligence,
    install_layout_foundation,
    install_persistence,
    install_run_debug,
    install_theme_and_finalize,
    start_composition_timers,
)
from app.shell.shell_composition_context import MainWindowCompositionSurface, ShellCompositionContext


def install_main_window_composition(
    window: MainWindowCompositionSurface,
    *,
    startup_report: Optional[CapabilityProbeReport],
    state_root: str | None,
) -> None:
    """Attach services, workflows, and timers to ``window`` in init order."""
    ctx = ShellCompositionContext(
        window=window,
        startup_report=startup_report,
        state_root=state_root,
    )
    # Phased install: layout → persistence → editors → run/debug → intelligence → theme.
    # Run/debug precedes intelligence because bootstrap_intelligence_runtime needs repl_manager.
    install_layout_foundation(ctx)
    install_persistence(ctx)
    create_composition_timers(ctx)
    install_editors(ctx)
    install_run_debug(ctx)
    install_intelligence(ctx)
    install_editor_project_wiring(ctx)
    connect_composition_timers(ctx)
    install_theme_and_finalize(ctx)
    start_composition_timers(ctx)
