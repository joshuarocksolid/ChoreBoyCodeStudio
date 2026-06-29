#!/usr/bin/env bash
# Run the in-process screenshot capture harness through FreeCAD AppRun.
#
# Usage:
#   DISPLAY=:1 docs/manual_complete/screenshots/capture/capture_run.sh
#
# Honors:
#   FREECAD_APPRUN     (default: $HOME/opt/freecad/AppRun)
#   CBCS_ARTIFACTS_DIR (default: $HOME/cbcs_artifacts)
#   CBCS_SHOT_OUT      (default: /tmp/caps)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
export FREECAD_APPRUN="${FREECAD_APPRUN:-$HOME/opt/freecad/AppRun}"
export CBCS_ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$HOME/cbcs_artifacts}"
export CBCS_SHOT_OUT="${CBCS_SHOT_OUT:-/tmp/caps}"
export CBCS_DISABLE_BACKGROUND_RUNTIME=1
export PYTHONUNBUFFERED=1
export DISPLAY="${DISPLAY:-:1}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

# Ensure the repo vendor symlink points at the real py39 bundle (the launcher does
# this too); discovery/runner subprocesses import pytest from here.
if [ ! -d "$ROOT/vendor/pytest" ]; then
  if [ -d "$CBCS_ARTIFACTS_DIR/vendor_py39/pytest" ]; then
    rm -f "$ROOT/vendor"
    ln -s "$CBCS_ARTIFACTS_DIR/vendor_py39" "$ROOT/vendor"
  fi
fi
export PYTHONPATH="$ROOT/vendor${PYTHONPATH:+:$PYTHONPATH}"

# In-app pytest discovery/runner capture stdout from a subprocess. FreeCAD's
# freecadcmd redirects Python stdout, so collection output is lost; route pytest
# through the conda runtime's plain python (non-FreeCAD) so stdout is captured.
PLAIN_PYTHON="$(dirname "$FREECAD_APPRUN")/bin/python"
if [ -x "$PLAIN_PYTHON" ]; then
  export CBCS_PYTEST_EXECUTABLE="${CBCS_PYTEST_EXECUTABLE:-$PLAIN_PYTHON}"
fi

HARNESS="$ROOT/docs/manual_complete/screenshots/capture/capture_harness.py"

exec "$FREECAD_APPRUN" -c "import runpy; runpy.run_path('$HARNESS', run_name='__main__')"
