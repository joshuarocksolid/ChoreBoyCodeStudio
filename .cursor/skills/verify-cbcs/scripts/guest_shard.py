"""In-process pytest under guest AppRun.

cbapp already launched this file inside confined /opt/freecad/AppRun.
Do not subprocess AppRun again — guest AppArmor allows only /bin/sh.
"""

from __future__ import annotations

import os
import sys
import traceback


def _repo_root() -> str:
    root = os.environ.get("CBCS_PACKAGE_ROOT")
    if root:
        return root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def _pytest_args(shard: str) -> list[str]:
    # Same argv testing/run_test_shard.py builds, then the run_tests.py marker rule.
    args = ["-q", "--import-mode=importlib"]
    if shard == "fast":
        args.extend(
            [
                "tests/unit",
                "tests/integration",
                "--ignore=tests/integration/performance",
                "-m",
                "not slow",
            ]
        )
    elif shard == "unit":
        args.extend(["tests/unit", "-m", "not slow"])
    elif shard == "integration":
        args.extend(["tests/integration", "--ignore=tests/integration/performance"])
    elif shard == "performance":
        args.append("tests/integration/performance")
    elif shard == "runtime_parity":
        args.append("tests/runtime_parity")
    else:
        args.append("tests")
    has_marker = any(arg == "-m" or (arg.startswith("-m") and len(arg) > 2) for arg in args)
    selects_perf = any("tests/integration/performance" in arg for arg in args)
    if not has_marker and not selects_perf:
        args = ["-m", "not performance", *args]
    return args


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")
    os.environ.setdefault("CBCS_SYNC_PROJECT_OPEN", "1")
    root = _repo_root()
    vendor = os.path.join(root, "vendor")
    if root not in sys.path:
        sys.path.insert(0, root)
    if os.path.isdir(vendor) and vendor not in sys.path:
        sys.path.insert(0, vendor)
    os.chdir(root)

    shard = os.environ.get("CBCS_SHARD", "all")
    log_path = os.environ.get("CBCS_SHARD_LOG") or os.path.join(root, "shard.log")
    done_path = os.environ.get("CBCS_SHARD_DONE") or log_path + ".done"
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    log = open(log_path, "w", buffering=1)
    sys.stdout = log
    sys.stderr = log
    rc = 1
    try:
        print("guest_shard shard=" + shard + " root=" + root)
        print("pytest_args " + repr(_pytest_args(shard)))
        import pytest

        rc = int(pytest.main(_pytest_args(shard)))
        print("pytest_exit " + str(rc))
    except Exception:
        traceback.print_exc()
        rc = 2
        print("pytest_exit " + str(rc))
    finally:
        log.flush()
        with open(done_path, "w") as done:
            done.write(str(rc) + "\n")
        log.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
