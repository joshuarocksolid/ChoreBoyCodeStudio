"""A runner stand-in that starts a child in its own process group, like a user
program doing ``subprocess.Popen(["/opt/freecad/AppRun", ...])``.

Both processes print a line to stdout (and the parent also to stderr), then
append to a heartbeat file. If their pipe breaks, the print raises and the
heartbeat stops, so a growing heartbeat proves the process is alive *and* can
still write output.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

_CHILD = (
    "import sys, time\n"
    "while True:\n"
    "    print('child-tick', flush=True)\n"
    "    with open(sys.argv[1], 'a') as beat:\n"
    "        beat.write('x')\n"
    "    time.sleep(0.05)\n"
)

_PARENT = (
    "import os, subprocess, sys, time\n"
    "beats = sys.argv[1]\n"
    "subprocess.Popen([sys.executable, '-c', CHILD, os.path.join(beats, 'child')])\n"
    "while True:\n"
    "    print('parent-tick', flush=True)\n"
    "    print('parent-err', file=sys.stderr, flush=True)\n"
    "    with open(os.path.join(beats, 'parent'), 'a') as beat:\n"
    "        beat.write('x')\n"
    "    time.sleep(0.05)\n"
)


def heartbeat_command(beat_dir: Path) -> list[str]:
    program = "CHILD = %r\n%s" % (_CHILD, _PARENT)
    return [sys.executable, "-c", program, str(beat_dir)]


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def wait_for_beats(beat_dir: Path, timeout_seconds: float = 10.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _size(beat_dir / "parent") > 0 and _size(beat_dir / "child") > 0:
            return True
        time.sleep(0.05)
    return False


def is_beating(path: Path, window_seconds: float = 0.8) -> bool:
    before = _size(path)
    time.sleep(window_seconds)
    return _size(path) > before >= 0


def kill_group(process_group_id: int | None) -> None:
    if process_group_id is None:
        return
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except OSError:
        pass
