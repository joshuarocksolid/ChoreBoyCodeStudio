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

HARNESS="$ROOT/docs/manual_complete/screenshots/capture/capture_harness.py"

exec "$FREECAD_APPRUN" -c "import runpy; runpy.run_path('$HARNESS', run_name='__main__')"
