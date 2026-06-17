#!/usr/bin/env python3
"""Run a named pytest shard through the AppRun-backed test wrapper."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

PYTEST_WORKERS_ENV_VAR = "CBCS_PYTEST_WORKERS"
REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_TESTS_PATH = REPO_ROOT / "run_tests.py"
PREFLIGHT_PATH = REPO_ROOT / "testing" / "preflight_test_env.py"
DEFAULT_PYTEST_ARGS = ["-q", "--import-mode=importlib"]
FAST_SHARD_TIMEOUT_SECONDS = 180
FAST_SHARD_SEQUENCE: list[list[str]] = [
    ["tests/unit", "-m", "not slow"],
    [
        "tests/integration",
        "--ignore=tests/integration/performance",
        "-m",
        "not slow",
    ],
]
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
    shard_args: list[str] | None = None,
) -> list[str]:
    resolved_shard_args = TEST_SHARDS[shard_name] if shard_args is None else shard_args
    return [
        python_executable or sys.executable,
        str(RUN_TESTS_PATH),
        *DEFAULT_PYTEST_ARGS,
        *resolved_shard_args,
        *(extra_pytest_args or []),
    ]


def _fast_shard_commands(
    *,
    python_executable: str | None = None,
    extra_pytest_args: list[str] | None = None,
) -> list[list[str]]:
    return [
        build_command(
            "fast",
            python_executable=python_executable,
            extra_pytest_args=extra_pytest_args,
            shard_args=step_args,
        )
        for step_args in FAST_SHARD_SEQUENCE
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
    commands = (
        _fast_shard_commands(extra_pytest_args=pytest_args)
        if parsed.shard == "fast"
        else [command]
    )
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
    deadline = None if shard_timeout is None else time.monotonic() + shard_timeout
    try:
        for step_command in commands:
            step_timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            if deadline is not None and step_timeout == 0.0:
                raise subprocess.TimeoutExpired(step_command, shard_timeout)
            completed = subprocess.run(
                step_command,
                cwd=str(REPO_ROOT),
                env=env,
                check=False,
                timeout=step_timeout,
            )
            if completed.returncode != 0:
                return completed.returncode
    except subprocess.TimeoutExpired:
        print(
            f"ERROR: {parsed.shard} shard exceeded the {FAST_SHARD_TIMEOUT_SECONDS}s watchdog. "
            "Check for hung tests or orphaned AppRun children with "
            "`python3 testing/preflight_test_env.py`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
