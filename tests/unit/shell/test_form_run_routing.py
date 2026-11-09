"""F5 on a form tab uses the surface hook. Debug and Run Project do not."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.shell.project_tree_context_menu import form_adopt_callback
from tests.unit.shell.test_run_command_routing import _build_run_launch_workflow

pytestmark = pytest.mark.unit


def _form_host(workflow_host: Any, calls: list[str]) -> None:
    surface = SimpleNamespace(run_active_file=lambda workflow: calls.append("hook") or True)
    workflow_host.editor_manager = lambda: SimpleNamespace(
        active_tab=lambda: SimpleNamespace(file_path="/tmp/invoice.ui", is_dirty=False, current_content="")
    )
    workflow_host.tab_content_registry = lambda: SimpleNamespace(
        surface_for_path=lambda path: surface if str(path).endswith(".ui") else None
    )


def test_run_action_on_a_form_uses_the_surface_hook() -> None:
    workflow, host = _build_run_launch_workflow()
    calls: list[str] = []
    _form_host(host, calls)

    def fail_start(**_kwargs: object) -> bool:
        raise AssertionError("F5 started the active-file session")

    workflow.start_session = fail_start  # type: ignore[method-assign]
    assert workflow.handle_run_action() is True
    assert calls == ["hook"]


def test_debug_action_does_not_use_the_form_hook() -> None:
    workflow, host = _build_run_launch_workflow()
    calls: list[str] = []
    _form_host(host, calls)
    assert workflow.handle_debug_action() is False
    assert calls == []


def test_run_project_action_does_not_use_the_form_hook() -> None:
    workflow, host = _build_run_launch_workflow()
    calls: list[str] = []
    _form_host(host, calls)
    assert workflow.handle_run_project_action() is False
    assert calls == []


def test_adopt_callback_is_only_for_a_ui_file() -> None:
    seen: list[str] = []

    def adopt(path: str) -> None:
        seen.append(path)

    window = SimpleNamespace(_form_builder_adopt_form=adopt)
    assert form_adopt_callback(window, "/tmp/invoice.ui", False) is adopt
    assert form_adopt_callback(window, "/tmp/main.py", False) is None
    assert form_adopt_callback(window, "/tmp/forms", True) is None
    assert form_adopt_callback(SimpleNamespace(), "/tmp/invoice.ui", False) is None
    form_adopt_callback(window, "/tmp/invoice.ui", False)("/tmp/invoice.ui")
    assert seen == ["/tmp/invoice.ui"]
