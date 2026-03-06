"""Unit tests for File -> New Window launch behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


def test_build_new_window_command_uses_apprun_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    monkeypatch.setattr("app.shell.main_window.resolve_runtime_executable", lambda _runtime: "/opt/freecad/AppRun")
    repo_root = Path("/tmp/repo")
    editor_boot = repo_root / "run_editor.py"

    command = MainWindow._build_new_window_command(window, repo_root=repo_root, editor_boot=editor_boot)

    assert command[0] == "/opt/freecad/AppRun"
    assert command[1] == "-c"
    assert "runpy.run_path" in command[2]
    assert str(editor_boot) in command[2]


def test_build_new_window_command_falls_back_to_python_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow.__new__(MainWindow)
    monkeypatch.setattr("app.shell.main_window.resolve_runtime_executable", lambda _runtime: "/usr/bin/python3")
    repo_root = Path("/tmp/repo")
    editor_boot = repo_root / "run_editor.py"

    command = MainWindow._build_new_window_command(window, repo_root=repo_root, editor_boot=editor_boot)

    assert command == ["/usr/bin/python3", str(editor_boot)]


def test_handle_new_window_action_launches_detached_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    editor_boot = repo_root / "run_editor.py"
    editor_boot.write_text("print('boot')\n", encoding="utf-8")

    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    window_any._resolve_repo_root_for_launch = lambda: repo_root
    window_any._build_new_window_command = lambda **_kwargs: ["python3", str(editor_boot)]

    popen_calls: list[tuple[list[str], dict[str, object]]] = []

    def _fake_popen(command: list[str], **kwargs: object):  # type: ignore[no-untyped-def]
        popen_calls.append((command, kwargs))
        return object()

    monkeypatch.setattr("app.shell.main_window.subprocess.Popen", _fake_popen)

    MainWindow._handle_new_window_action(window)

    assert len(popen_calls) == 1
    command, kwargs = popen_calls[0]
    assert command == ["python3", str(editor_boot)]
    assert kwargs["cwd"] == str(repo_root)
    assert kwargs["start_new_session"] is True
