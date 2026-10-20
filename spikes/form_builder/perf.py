"""Status-bar timings. The log is a TSV a reviewer can re-read."""

from __future__ import annotations

import time
from pathlib import Path

LOG = Path(__file__).resolve().parent / "perf.log"


def log_sample(kind: str, milliseconds: float, note: str = "") -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp}\t{kind}\t{milliseconds:.3f}\t{note}\n")
