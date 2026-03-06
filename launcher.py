"""Legacy launcher compatibility artifact.

This module intentionally remains a no-op placeholder so packaging/type-check
entrypoint references stay stable while `run_editor.py` and `run_runner.py`
own the real launch flow.
"""

APP_RUN_PATH = "/opt/freecad/AppRun"
EDITOR_BOOT = "run_editor.py"
RUNNER_BOOT = "run_runner.py"


def main() -> int:
    """Return success for compatibility-only launcher shim."""
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
