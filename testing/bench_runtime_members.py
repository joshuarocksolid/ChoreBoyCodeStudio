"""Benchmark runtime member listing and resolution in process under AppRun.

Usage:
    CBCS_APPRUN=$HOME/opt/freecad/AppRun python3 testing/bench_runtime_members.py \
        --target PySide2.QtWidgets.QPushButton --member setText

Exits 1 when the listing does not hold every non-dunder ``dir()`` name.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Callable, Optional, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
_IN_APPRUN_ENV = "CBCS_BENCH_RUNTIME_MEMBERS_CHILD"


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="PySide2.QtWidgets.QPushButton")
    parser.add_argument("--member", default="setText")
    parser.add_argument("--repeat", type=int, default=50)
    return parser.parse_args(argv)


def _timings_ms(action: Callable[[], object], repeat: int) -> list[float]:
    samples: list[float] = []
    for _ in range(max(1, repeat)):
        started = time.perf_counter()
        action()
        samples.append((time.perf_counter() - started) * 1000.0)
    return samples


def _median_p95(samples: list[float]) -> str:
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return f"median {statistics.median(ordered):.3f} ms, p95 {p95:.3f} ms"


def _run_in_process(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(_REPO_ROOT))
    vendor = _REPO_ROOT / "vendor"
    if vendor.is_dir():
        sys.path.insert(0, str(vendor))

    from app.intelligence.runtime_members import RuntimeMemberListing, RuntimeMemberRef, RuntimeUnavailable
    from app.runner.repl_introspection import ReplIntrospectionService, resolve_whitelisted_target
    from app.runner.repl_protocol import listing_to_wire

    service = ReplIntrospectionService()
    listing = service.list_members(args.target)
    if isinstance(listing, RuntimeUnavailable):
        print(f"list_members unavailable for {args.target}: {listing.reason}")
        return 1
    assert isinstance(listing, RuntimeMemberListing)

    listed_names = {member.name for member in (*listing.public, *listing.private)}
    dir_names = {name for name in dir(resolve_whitelisted_target(args.target)) if not name.startswith("__")}
    print(f"target: {args.target}")
    print(f"listed names: {len(listed_names)} ({len(listing.public)} public, {len(listing.private)} private)")
    print(f"dir() non-dunder names: {len(dir_names)}")

    list_samples = _timings_ms(lambda: service.list_members(args.target), args.repeat)
    print(f"list_members x{len(list_samples)}: {_median_p95(list_samples)}")
    print(f"wire JSON size: {len(json.dumps(listing_to_wire(listing), separators=(',', ':')))} bytes")

    ref = RuntimeMemberRef(target_path=args.target, name=args.member)
    resolve_samples = _timings_ms(lambda: service.resolve_member(ref), args.repeat)
    print(f"resolve_member {args.member} x{len(resolve_samples)}: {_median_p95(resolve_samples)}")
    print(f"resolved: {service.resolve_member(ref)}")

    if listed_names != dir_names:
        print(f"MISMATCH missing={sorted(dir_names - listed_names)} extra={sorted(listed_names - dir_names)}")
        return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    if os.environ.get(_IN_APPRUN_ENV) == "1":
        return _run_in_process(args)
    apprun = os.environ.get("CBCS_APPRUN") or str(Path.home() / "opt" / "freecad" / "AppRun")
    if not Path(apprun).is_file():
        print(f"AppRun not found at {apprun}. Set CBCS_APPRUN.")
        return 1
    forwarded = list(argv) if argv is not None else sys.argv[1:]
    env = dict(os.environ, **{_IN_APPRUN_ENV: "1", "QT_QPA_PLATFORM": "offscreen"})
    return subprocess.call([apprun, str(Path(__file__).resolve()), *forwarded], cwd=str(_REPO_ROOT), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
