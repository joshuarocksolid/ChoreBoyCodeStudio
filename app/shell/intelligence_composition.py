"""Intelligence runtime bootstrap extracted from main window composition."""

from __future__ import annotations

from typing import Any

from app.intelligence.semantic_session import SemanticSession
from app.intelligence.runtime_introspection import RuntimeIntrospectionCoordinator
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.editor_intelligence_controller import EditorIntelligenceController


def bootstrap_intelligence_runtime(window: Any, *, symbol_cache_db_path: str) -> None:
    """Wire semantic session, controller, background tasks, and runtime introspection."""
    window._symbol_cache_db_path = symbol_cache_db_path
    window._symbol_index_generation = 0
    window._runtime_introspection_coordinator = RuntimeIntrospectionCoordinator(
        runner_port=window._repl_manager,
    )
    window._semantic_session = SemanticSession(
        dispatch_to_main_thread=window._dispatch_to_main_thread,
        cache_db_path=window._symbol_cache_db_path,
        state_root=window._state_root,
    )
    window._background_tasks = GeneralTaskScheduler(
        dispatch_to_main_thread=window._dispatch_to_main_thread,
    )
    window._intelligence_controller = EditorIntelligenceController(
        semantic_session=window._semantic_session,
        runtime_coordinator=window._runtime_introspection_coordinator,
        background_tasks=window._background_tasks,
    )
