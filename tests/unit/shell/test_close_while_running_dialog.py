"""Close-while-running prompt: what it names and which choice Enter picks."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.shell.close_while_running_dialog import (  # noqa: E402
    CloseRunChoice,
    CloseWhileRunningDialog,
    RunningProgramSummary,
    find_opened_windows,
)

pytestmark = pytest.mark.unit


def _fake_process(proc: Path, pid: int, pgid: int, argv: list[str], comm: str = "x") -> None:
    entry = proc / str(pid)
    entry.mkdir()
    (entry / "stat").write_text(f"{pid} ({comm}) S 1 {pgid} {pgid} 0 -1", encoding="utf-8")
    (entry / "cmdline").write_text("\0".join(argv) + "\0", encoding="utf-8")


def test_find_opened_windows_names_freecad_children_of_the_run_group(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    runner = 500
    _fake_process(proc, runner, runner, ["/opt/freecad/AppRun", "-c", "runner payload"])
    _fake_process(proc, 501, runner, ["/opt/freecad/usr/bin/freecad", "/home/u/Unnamed.FCStd"], comm="freecad")
    _fake_process(proc, 502, runner, ["/bin/sh", "-c", "sleep 100"])
    _fake_process(proc, 503, runner, ["/opt/freecad/AppRun", "-c", "print(1)"])
    _fake_process(proc, 600, 600, ["/opt/freecad/usr/bin/freecad"], comm="freecad")
    _fake_process(proc, 504, runner, ["/bin/bash", "/opt/freecad/AppRun"])

    assert find_opened_windows(runner, proc_root=str(proc)) == ("FreeCAD (Unnamed.FCStd)", "FreeCAD")


def test_find_opened_windows_is_empty_without_proc(tmp_path: Path) -> None:
    assert find_opened_windows(1, proc_root=str(tmp_path / "missing")) == ()


def test_enter_keeps_the_program_running(qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = CloseWhileRunningDialog(
        None,
        RunningProgramSummary(name="main.py  (ShopTracker)", running_for="Running for 12 minutes", started_with="started with Run Project"),
    )
    assert dialog.keep_button is not None
    assert dialog.keep_button.isDefault() is True
    dialog.keep_button.click()
    assert dialog.choice == CloseRunChoice.KEEP


def test_debug_runs_offer_stop_but_not_keep(qapp) -> None:  # type: ignore[no-untyped-def]
    dialog = CloseWhileRunningDialog(
        None,
        RunningProgramSummary(
            name="main.py",
            running_for="Running for 1 minute",
            started_with="started with Debug",
            can_keep_running=False,
        ),
    )
    assert dialog.keep_button is None
    dialog.reject()
    assert dialog.choice == CloseRunChoice.CANCEL
    dialog.stop_button.click()
    assert dialog.choice == CloseRunChoice.STOP
