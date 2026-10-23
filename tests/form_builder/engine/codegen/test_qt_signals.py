"""The committed signal table matches the running Qt (dump-vs-runtime)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen import qt_signals

_TOOL = Path(__file__).resolve().parents[4] / "tools" / "form_builder" / "dump_qt_signals.py"


def _live() -> dict:
    """The table read by the dump tool in a fresh interpreter.

    A long test session leaves PySide wrappers for deleted meta-objects, so the
    live walk does not run in this process.
    """
    if "freecadcmd" in os.path.basename(sys.executable):
        # Cloud conda AppRun: sys.executable is freecadcmd, which rejects --json.
        pytest.skip("sys.executable is %s, not a Python that runs scripts" % sys.executable)
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [sys.executable, str(_TOOL), "--json"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


def test_signal_table_matches_running_qt() -> None:
    payload = _live()
    if payload["qt_version"] != qt_signals.QT_VERSION:
        pytest.skip(
            "running Qt %s; the committed table is Qt %s"
            % (payload["qt_version"], qt_signals.QT_VERSION)
        )
    live = {name: (body[0], tuple(body[1])) for name, body in payload["classes"].items()}
    problems = []
    for name in sorted(set(live) | set(qt_signals._TABLE)):
        if name not in qt_signals._TABLE:
            problems.append("%s is missing from the table" % name)
        elif name not in live:
            problems.append("%s is not a class in the running Qt" % name)
        elif qt_signals._TABLE[name] != live[name]:
            have_parent, have = qt_signals._TABLE[name]
            want_parent, want = live[name]
            if have_parent != want_parent:
                problems.append("%s has super %s, Qt says %s" % (name, have_parent, want_parent))
            for signal in sorted(set(want) - set(have)):
                problems.append("%s.%s is missing" % (name, signal))
            for signal in sorted(set(have) - set(want)):
                problems.append("%s.%s is not a signal in the running Qt" % (name, signal))
    assert not problems, "\n".join(problems[:40])
