#!/usr/bin/env python3
"""Preflight checks before running pytest shards through AppRun."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPRUN = os.environ.get("CBCS_APPRUN", "/opt/freecad/AppRun")


def _iter_proc_cmdlines() -> list[tuple[int, str]]:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    entries: list[tuple[int, str]] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", "replace")
        entries.append((int(entry.name), cmdline))
    return entries


def _is_stale_test_process(cmdline: str) -> bool:
    if "preflight_test_env.py" in cmdline:
        return False
    if "extglob -c snap=" in cmdline or "dump_bash_state" in cmdline:
        return False
    if "ChoreBoyCodeStudio/run_plugin_host.py" in cmdline:
        return True
    if "ChoreBoyCodeStudio/run_runner.py" in cmdline:
        return True
    if "pytest.main" in cmdline and "ChoreBoyCodeStudio" in cmdline:
        return True
    if " run_tests.py " in cmdline or cmdline.rstrip().endswith("run_tests.py"):
        return True
    return False


def find_stale_test_processes() -> list[tuple[int, str]]:
    current_pid = os.getpid()
    stale: list[tuple[int, str]] = []
    for pid, cmdline in _iter_proc_cmdlines():
        if pid == current_pid:
            continue
        if not _is_stale_test_process(cmdline):
            continue
        stale.append((pid, cmdline))
    return stale


def pytest_timeout_available() -> bool:
    app_run_path = Path(APPRUN)
    if not app_run_path.is_file():
        print(f"ERROR: FreeCAD AppRun not found at {APPRUN}", file=sys.stderr)
        return False
    payload = "import pytest_timeout; print('ok')"
    completed = subprocess.run(
        [str(app_run_path), "-c", payload],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def main() -> int:
    stale = find_stale_test_processes()
    if stale:
        print("Stale test/runtime processes detected. Clean up before running shards:", file=sys.stderr)
        for pid, cmdline in stale:
            print(f"  PID {pid}: {cmdline}", file=sys.stderr)
        print(
            "\nSuggested cleanup:\n"
            "  pkill -f 'ChoreBoyCodeStudio/(run_tests|run_plugin_host|run_runner)'\n"
            "  rm -rf /tmp/pytest-of-$USER",
            file=sys.stderr,
        )
        return 1

    if not pytest_timeout_available():
        print(
            "pytest-timeout is not importable in AppRun. Install it into site-packages or vendor:\n"
            "  pip3 install pytest-timeout --target=/opt/freecad/usr/lib/python3.11/site-packages/\n"
            "  # or re-run scripts/setup_vendor_py311.sh / setup_vendor_py39.sh",
            file=sys.stderr,
        )
        return 1

    print("Preflight OK: no stale test processes; pytest-timeout available in AppRun.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
