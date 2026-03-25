#!/usr/bin/env python3
"""Run the test suite through the FreeCAD AppRun runtime.

Usage:
    python3 run_tests.py -v
    python3 run_tests.py -v tests/unit/
    python3 run_tests.py -v -k test_project_service
    CBCS_PYTEST_WORKERS=4 python3 run_tests.py -q tests/unit

Pytest args inherit `[tool.pytest.ini_options]` from pyproject.toml. This launcher
also prepends ``--import-mode=importlib`` when the caller did not set
``--import-mode``, so duplicate test module basenames under tests/ collect
correctly even if config discovery differs. When ``CBCS_PYTEST_WORKERS`` is set
to a non-zero value and the caller did not provide explicit xdist worker flags,
the launcher also prepends ``-n <value>``.
"""
from __future__ import annotations

import os
import subprocess
import sys

APPRUN = os.environ.get("CBCS_APPRUN", "/opt/freecad/AppRun")
PYTEST_WORKERS_ENV_VAR = "CBCS_PYTEST_WORKERS"


def _pytest_argv() -> list[str]:
    """Return pytest CLI args, defaulting to importlib mode unless already set."""
    args = list(sys.argv[1:])
    worker_count = _configured_pytest_workers()
    if worker_count is not None and not _has_parallelism_arg(args):
        args = ["-n", worker_count, *args]
    if not _has_import_mode_arg(args):
        args = ["--import-mode=importlib", *args]
    return args


def _configured_pytest_workers() -> str | None:
    raw_value = os.environ.get(PYTEST_WORKERS_ENV_VAR)
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value or value == "0":
        return None
    return value


def _has_import_mode_arg(args: list[str]) -> bool:
    return any(arg == "--import-mode" or arg.startswith("--import-mode=") for arg in args)


def _has_parallelism_arg(args: list[str]) -> bool:
    for arg in args:
        if arg == "-n" or arg == "--numprocesses":
            return True
        if arg.startswith("--numprocesses="):
            return True
        if arg.startswith("-n") and len(arg) > 2:
            return True
    return False


def main() -> int:
    if not os.path.isfile(APPRUN):
        print(
            f"ERROR: FreeCAD AppRun not found at {APPRUN}\n"
            "Set CBCS_APPRUN to override the path.",
            file=sys.stderr,
        )
        return 1

    repo_root = os.path.dirname(os.path.abspath(__file__))
    pytest_args = repr(_pytest_argv())

    payload = (
        "import sys;"
        f"sys.path.insert(0, {repo_root!r});"
        f"sys.exit(__import__('pytest').main({pytest_args}))"
    )

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    result = subprocess.run([APPRUN, "-c", payload], cwd=repo_root, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
