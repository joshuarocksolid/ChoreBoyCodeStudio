#!/usr/bin/env python3
"""Print the form-builder speed table.

Run it with FreeCAD 1.1's Python. The script adds the repo root to ``sys.path``
and imports only the application package plus this harness. It does not import
pytest or the repo's vendor tree.

``--profile mac`` enforces the absolute CPU budgets.
``--profile choreboy`` records those numbers and enforces the overhead ratios
when Realizer exists.
``--profile capped`` pins this process to one CPU with ``taskset`` and then
runs the choreboy profile. Without ``taskset``, and when the process is not
already limited to one CPU, the table is a skip and the process exits 0.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Optional, Sequence

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.form_builder.perf.harness import (  # noqa: E402
    FULL_SIZES,
    SECTION_12_POINTS,
    Row,
    SpeedReport,
    format_table,
    run_speed,
    write_json,
)
from tests.form_builder.perf.stats import CPU_TOLERANCE, wall_policy  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=("mac", "choreboy", "capped"))
    parser.add_argument("--json", type=Path, help="Write the same rows as JSON.")
    parser.add_argument("--samples", type=int, default=15)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1505)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.profile == "capped":
        reason = _pin_or_continue()
        if reason is not None:
            report = _skipped(reason)
            sys.stdout.write(format_table(report))
            if args.json is not None:
                write_json(report, args.json)
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
    report = run_speed(
        profile=args.profile,
        samples=args.samples,
        warmup=args.warmup,
        sizes=FULL_SIZES,
        seed=args.seed,
    )
    sys.stdout.write(format_table(report))
    if args.json is not None:
        write_json(report, args.json)
    # Shiboken's destructor segfaults if Python wrappers outlive Qt.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if report.ok else 1)


def _pin_or_continue() -> Optional[str]:
    """Re-exec under ``taskset -c`` when this process can use more than one CPU."""
    if os.environ.get("CBCS_FB_SPEED_PINNED") == "1":
        return None
    try:
        cpus = os.sched_getaffinity(0)
    except (AttributeError, OSError):
        return "capped profile skipped: this OS does not expose CPU affinity"
    if len(cpus) <= 1:
        return None
    taskset = shutil.which("taskset")
    if taskset is None:
        return (
            "capped profile skipped: taskset is not installed and the process "
            "is not already limited to one CPU"
        )
    core = str(min(cpus))
    os.environ["CBCS_FB_SPEED_PINNED"] = "1"
    try:
        os.execvp(taskset, [taskset, "-c", core, sys.executable, *sys.argv])
    except OSError as exc:
        return "capped profile skipped: taskset failed (%s)" % exc
    return None


def _skipped(reason: str) -> SpeedReport:
    load = _load()
    _enforced, wall = wall_policy(load, load)
    rows = tuple(
        Row(point, None, None, None, None, "-", "skip", reason) for point in SECTION_12_POINTS
    )
    return SpeedReport(
        profile="capped",
        interpreter=sys.version.split()[0],
        qt_version="unavailable",
        load_start=load,
        load_end=load,
        wall=wall,
        samples=0,
        warmup=0,
        cpu_tolerance=CPU_TOLERANCE,
        cpus=1,
        rows=rows,
    )


def _load() -> tuple:
    try:
        return os.getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)


if __name__ == "__main__":
    raise SystemExit(main())
