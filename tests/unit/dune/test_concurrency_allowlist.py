from __future__ import annotations

from pathlib import Path

import pytest

from tools.dune.check import run
from tools.dune.concurrency import find_concurrency_violations

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_source(repo_root: Path, relative_path: str, source: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _write_manifest(repo_root: Path, owner_path: str) -> None:
    (repo_root / "dune.yaml").write_text(
        "owners:\n"
        "  shell:\n"
        f"    - {owner_path}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        "app/intelligence/semantic_worker.py",
        "app/run/process_supervisor.py",
        "app/debug/debug_transport.py",
        "app/project/project_open_worker.py",
        "app/editors/search_panel.py",
        "app/shell/search_sidebar_widget.py",
        "app/runner/repl_control.py",
        "run_plugin_host.py",
    ],
)
def test_existing_protocol_worker_is_allowed(relative_path: str) -> None:
    assert find_concurrency_violations(REPO_ROOT, [relative_path]) == []


@pytest.mark.parametrize(
    "relative_path",
    [
        "app/shell/python_style_workflow.py",
        "app/shell/save_workflow.py",
        "app/shell/plugin_dialog_workflow.py",
        "app/shell/lint_workflow.py",
    ],
)
def test_existing_blocking_call_allowance_is_green(
    relative_path: str,
) -> None:
    assert find_concurrency_violations(REPO_ROOT, [relative_path]) == []


def test_planted_status_bar_thread_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative_path = "app/shell/status_bar.py"
    _write_manifest(tmp_path, relative_path)
    _write_source(
        tmp_path,
        relative_path,
        "import threading\n"
        "from PySide2.QtWidgets import QLabel\n"
        "\n"
        "class ShellStatusBarController(QLabel):\n"
        "    def refresh(self):\n"
        "        worker = threading.Thread(target=lambda: self.setText('ready'))\n"
        "        worker.start()\n",
    )

    exit_code = run(tmp_path, [relative_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "concurrency: app/shell/status_bar.py:6: "
        "Thread is not an approved worker; "
        "use GeneralTaskScheduler for shell work\n"
    )


def test_planted_thread_in_real_status_bar_factory_fails(tmp_path: Path) -> None:
    relative_path = "app/shell/status_bar.py"
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    import_line = "    from PySide2.QtWidgets import QLabel, QStatusBar\n"
    assert import_line in source
    planted_source = source.replace(
        import_line,
        import_line
        + "    import threading\n\n"
        + "    threading.Thread(target=lambda: None).start()\n",
        1,
    )
    _write_source(tmp_path, relative_path, planted_source)

    violations = find_concurrency_violations(tmp_path, [relative_path])

    assert any(
        violation.endswith(
            "Thread is not an approved worker; "
            "use GeneralTaskScheduler for shell work"
        )
        for violation in violations
    )


def test_planted_gui_thread_invoke_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative_path = "app/shell/plugin_widget.py"
    _write_manifest(tmp_path, relative_path)
    _write_source(
        tmp_path,
        relative_path,
        "from PySide2.QtWidgets import QWidget\n"
        "\n"
        "class PluginWidget(QWidget):\n"
        "    def invoke(self):\n"
        "        return self._runtime_manager.invoke_command('plugin.demo', {})\n",
    )

    exit_code = run(tmp_path, [relative_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "concurrency: app/shell/plugin_widget.py:5: "
        "GUI-thread invoke_command call must run through GeneralTaskScheduler\n"
    )


def test_scheduler_wrapped_invoke_is_allowed(tmp_path: Path) -> None:
    relative_path = "app/shell/plugin_widget.py"
    _write_source(
        tmp_path,
        relative_path,
        "class PluginWidget:\n"
        "    def invoke(self, scheduler, runtime_manager):\n"
        "        def task(_cancel_event):\n"
        "            return runtime_manager.invoke_command('plugin.demo', {})\n"
        "        scheduler.run(key='plugin', task=task)\n",
    )

    assert find_concurrency_violations(tmp_path, [relative_path]) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from PySide2.QtCore import QThread\nQThread()\n",
            "app.shell and app.editors must not create QThread",
        ),
        (
            "import time\ntime.sleep(0.1)\n",
            "app.shell and app.editors must not call time.sleep",
        ),
    ],
)
def test_disallowed_ui_blocking_primitive_fails(
    tmp_path: Path,
    source: str,
    expected: str,
) -> None:
    relative_path = "app/editors/new_widget.py"
    _write_source(tmp_path, relative_path, source)

    violations = find_concurrency_violations(tmp_path, [relative_path])

    assert len(violations) == 1
    assert violations[0].startswith(
        "concurrency: app/editors/new_widget.py:2: "
    )
    assert violations[0].endswith(expected)
