"""Debug panel ↔ workflow integration contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.debug_control_workflow import DebugControlWorkflow  # noqa: E402
from app.shell.debug_panel import DebugPanelWidget  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def test_panel_clear_all_breakpoints_uses_single_workflow_path() -> None:
    """Panel Clear All and menu Remove All share one workflow entry point."""
    panel = DebugPanelWidget()
    store_calls: list[str] = []

    class FakeStore:
        def clear_all(self) -> None:
            store_calls.append("clear_all")

        def all_specs(self):
            return []

    window = SimpleNamespace(
        _editor_widgets_by_path={},
        _debug_panel=panel,
        _debug_session=SimpleNamespace(state=SimpleNamespace(breakpoints=[])),
        _run_service=SimpleNamespace(is_debug_mode=False, supervisor=SimpleNamespace(is_running=lambda: False)),
        _run_event_workflow=SimpleNamespace(refresh_run_action_states=lambda: None),
    )
    workflow = DebugControlWorkflow(window)
    workflow._store = FakeStore()  # type: ignore[assignment]
    panel.clear_all_breakpoints_requested.connect(workflow.clear_all_breakpoints)

    panel._handle_clear_all_breakpoints()

    assert store_calls == ["clear_all"]
