#!/usr/bin/env python3
"""Run the test suite through the FreeCAD AppRun runtime.

Usage:
    python3 run_tests.py -v
    python3 run_tests.py -v tests/unit/
    python3 run_tests.py -v -k test_project_service
"""
from __future__ import annotations

import os
import subprocess
import sys

APPRUN = os.environ.get("CBCS_APPRUN", "/opt/freecad/AppRun")


def main() -> int:
    if not os.path.isfile(APPRUN):
        print(
            f"ERROR: FreeCAD AppRun not found at {APPRUN}\n"
            "Set CBCS_APPRUN to override the path.",
            file=sys.stderr,
        )
        return 1

    repo_root = os.path.dirname(os.path.abspath(__file__))
    pytest_args = repr(sys.argv[1:])

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
