"""Unit tests for lint runtime-probe policy in LintWorkflow."""

from __future__ import annotations

import threading
from types import SimpleNamespace
import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.intelligence.diagnostics_service import CodeDiagnostic  # noqa: E402
from tests.support.shell_host_stubs import lint_workflow_stub  # noqa: E402

pytestmark = pytest.mark.unit


def test_render_lint_manual_trigger_uses_static_import_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, host = lint_workflow_stub()
    captured: list[bool] = []

    def _fake_analyze(_broker, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return (SimpleNamespace(title="lint"), [])

    monkeypatch.setattr("app.shell.lint_workflow.analyze_python_with_workflow", _fake_analyze)

    workflow.render_diagnostics_for_file("/tmp/main.py", trigger="manual")
    background_call = host.background_tasks().calls[0]
    background_call["task"](threading.Event())

    assert captured == [False]


def test_render_lint_save_trigger_disables_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, host = lint_workflow_stub()
    captured: list[bool] = []

    def _fake_analyze(_broker, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return (SimpleNamespace(title="lint"), [])

    monkeypatch.setattr("app.shell.lint_workflow.analyze_python_with_workflow", _fake_analyze)

    workflow.render_diagnostics_for_file("/tmp/main.py", trigger="save")
    background_call = host.background_tasks().calls[0]
    background_call["task"](threading.Event())

    assert captured == [False]


def test_lint_all_open_files_disables_runtime_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    workflow, host = lint_workflow_stub()
    host._editor_widgets_by_path = {
        "/tmp/a.py": SimpleNamespace(toPlainText=lambda: "import x\n"),
        "/tmp/b.py": SimpleNamespace(toPlainText=lambda: "import y\n"),
    }
    captured: list[bool] = []

    def _fake_analyze(_broker, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(bool(kwargs.get("allow_runtime_import_probe")))
        return (SimpleNamespace(title="lint"), [])

    monkeypatch.setattr("app.shell.lint_workflow.analyze_python_with_workflow", _fake_analyze)

    workflow.lint_all_open_files()
    assert len(host.background_tasks().calls) == 2
    for background_call in host.background_tasks().calls:
        background_call["task"](threading.Event())

    assert captured == [False, False]


def test_render_lint_drops_stale_results_for_changed_buffer() -> None:
    workflow, host = lint_workflow_stub()
    editor_widget = SimpleNamespace(toPlainText=lambda: "print('a')\n")
    host._editor_widgets_by_path = {"/tmp/main.py": editor_widget}
    applied: list[tuple[str, list[CodeDiagnostic]]] = []
    revisions = {"current": 1}
    host._editor_tab_workflow = SimpleNamespace(
        buffer_revision=lambda _path: revisions["current"],
    )
    host._problems_controller = SimpleNamespace(
        apply_lint_diagnostics_result=lambda file_path, diagnostics: applied.append((file_path, diagnostics)),
        render_merged_problems_panel=lambda: None,
        update_status_bar_diagnostics=lambda *_args, **_kwargs: None,
    )

    workflow.render_diagnostics_for_file("/tmp/main.py", trigger="save")
    background_call = host.background_tasks().calls[0]

    revisions["current"] = 2
    background_call["on_success"](["diagnostic"])

    assert applied == []
