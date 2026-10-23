"""Run realize seeds in a child process so a crash names its seed.

Usage: python -m tests.form_builder.qtside.tools.realize_sequence --steps 30 --seeds 0,1,2

Run it under the allocator scribble env (``MallocScribble=1
MallocPreScribble=1`` on macOS, ``MALLOC_PERTURB_`` on Linux) so a
use-after-free crashes instead of reading stale memory. Each ``SEED`` line on
stderr carries ``PYTHONHASHSEED``; a crash replays with the same value.
"""

from __future__ import annotations

import argparse
import faulthandler
import os
import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    faulthandler.enable()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--seeds", required=True, help="Comma-separated seed numbers")
    args = parser.parse_args(argv)
    seeds = [int(piece) for piece in args.seeds.split(",") if piece]
    from tests.form_builder.qtside.test_realize import run_realize_seeds

    run_realize_seeds(seeds, args.steps, hash_seed=os.environ.get("PYTHONHASHSEED", "random"))
    print("OK seeds=%d steps=%d" % (len(seeds), args.steps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
