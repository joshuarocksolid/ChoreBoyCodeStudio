"""Bootstrap the standalone installer from a Path-keyed desktop launcher."""

from __future__ import annotations

import json
import os
import runpy
import sys
import time
import traceback


PACKAGE_ROOT_ENV = "CBCS_PACKAGE_ROOT"
DIAGNOSTIC_FILENAME = "launch_diagnostic.json"


def _resolve_package_root() -> tuple[str, str]:
    env_root = os.environ.get(PACKAGE_ROOT_ENV, "").strip()
    if env_root:
        return os.path.abspath(env_root), "env"

    # Production launchers set CBCS_PACKAGE_ROOT from the .desktop Path= cwd.
    # The file-location fallback keeps direct developer/runtime tests diagnosable.
    source_root = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(source_root, os.pardir)), "bootstrap_file"


def _write_diagnostic(package_root: str, stage: str, source: str, error: str = "") -> None:
    payload = {
        "stage": stage,
        "error": error,
        "package_root": package_root,
        "root_source": source,
        "cwd": os.getcwd(),
        "argv": sys.argv,
        "env": {
            PACKAGE_ROOT_ENV: os.environ.get(PACKAGE_ROOT_ENV, ""),
            "DESKTOP_STARTUP_ID": os.environ.get("DESKTOP_STARTUP_ID", ""),
            "PWD": os.environ.get("PWD", ""),
        },
        "timestamp": time.time(),
    }
    diagnostic_path = os.path.join(package_root, DIAGNOSTIC_FILENAME)
    try:
        with open(diagnostic_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError:
        # Diagnostics must never be the reason the installer fails to open.
        return


def main() -> None:
    package_root, root_source = _resolve_package_root()
    _write_diagnostic(package_root, "bootstrap_entered", root_source)
    try:
        installer_entry = os.path.abspath(os.path.join(package_root, "installer", "install.py"))
        if not os.path.isdir(package_root):
            raise RuntimeError(f"Invalid package root: {package_root}")
        if os.path.commonpath([package_root, installer_entry]) != package_root:
            raise RuntimeError(f"Invalid installer entry: {installer_entry}")
        if not os.path.isfile(installer_entry):
            raise RuntimeError(f"Installer entry missing: {installer_entry}")
        installer_dir = os.path.dirname(installer_entry)
        if installer_dir not in sys.path:
            sys.path.insert(0, installer_dir)
        os.chdir(installer_dir)
        runpy.run_path(installer_entry, run_name="__main__")
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}\n{traceback.format_exc()}"
        _write_diagnostic(package_root, "bootstrap_error", root_source, error=error)
        raise


if __name__ == "__main__":
    main()
