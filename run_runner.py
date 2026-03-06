"""Runner process bootstrap entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.core import constants
from app.runner.runner_main import run_from_manifest_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse runner CLI options."""
    parser = argparse.ArgumentParser(description="ChoreBoy Code Studio runner entrypoint")
    parser.add_argument("--manifest", required=True, help="Absolute path to run manifest JSON file")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute runner manifest and return standardized exit code."""
    args = parse_args(argv)
    exit_code = run_from_manifest_path(args.manifest)
    if exit_code is None:
        return constants.RUN_EXIT_BOOTSTRAP_ERROR
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
