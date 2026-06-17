#!/usr/bin/env python3
"""Run a named pytest shard through the AppRun-backed test wrapper."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

PYTEST_WORKERS_ENV_VAR = "CBCS_PYTEST_WORKERS"
REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_TESTS_PATH = REPO_ROOT / "run_tests.py"
PREFLIGHT_PATH = REPO_ROOT / "testing" / "preflight_test_env.py"
DEFAULT_PYTEST_ARGS = ["-q", "--import-mode=importlib"]
FAST_SHARD_TIMEOUT_SECONDS = 180
TEST_SHARDS = {
    "fast": [
        "tests/unit",
        "tests/integration",
        "--ignore=tests/integration/performance",
        "-m",
        "not slow",
    ],
    "unit": ["tests/unit", "-m", "not slow"],
    "integration": ["tests/integration", "--ignore=tests/integration/performance"],
    "performance": ["tests/integration/performance"],
    "runtime_parity": ["tests/runtime_parity"],
    "all": ["tests"],
}


def build_command(
    shard_name: str,
    *,
    python_executable: str | None = None,
    extra_pytest_args: list[str] | None = None,
) -> list[str]:
    shard_args = TEST_SHARDS[shard_name]
    return [
        python_executable or sys.executable,
        str(RUN_TESTS_PATH),
        *DEFAULT_PYTEST_ARGS,
        *shard_args,
        *(extra_pytest_args or []),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workers",
        help="Optional CBCS_PYTEST_WORKERS override for experiments.",
    )
    parser.add_argument("shard", choices=sorted(TEST_SHARDS))
    parsed, pytest_args = parser.parse_known_args(argv)

    pytest_args = list(pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]

    command = build_command(parsed.shard, extra_pytest_args=pytest_args)
    env = os.environ.copy()
    if parsed.workers:
        env[PYTEST_WORKERS_ENV_VAR] = parsed.workers

    preflight = subprocess.run(
        [sys.executable, str(PREFLIGHT_PATH)],
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
    )
    if preflight.returncode != 0:
        return preflight.returncode

    shard_timeout = FAST_SHARD_TIMEOUT_SECONDS if parsed.shard == "fast" else None
    try:
        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            check=False,
            timeout=shard_timeout,
        )
    except subprocess.TimeoutExpired:
        print(
            f"ERROR: {parsed.shard} shard exceeded the {FAST_SHARD_TIMEOUT_SECONDS}s watchdog. "
            "Check for hung tests or orphaned AppRun children with "
            "`python3 testing/preflight_test_env.py`.",
            file=sys.stderr,
        )
        return 1
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
