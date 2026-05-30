#!/usr/bin/env bash
# Launch ChoreBoy Code Studio using FreeCAD AppRun runtime.
# Matches ChoreBoy production environment: Python 3.9, PySide2 from FreeCAD.
#
# Usage: ./run_dev.sh [--dry-run|--probe]
#   --dry-run  Print resolved launch command and exit without launching.
#   --probe    Run the tree-sitter runtime probe through AppRun and exit.
#
# AppRun resolution order:
#   1. CBCS_APPRUN (project override)
#   2. FREECAD_APPRUN (cross-project override)
#   3. ~/opt/freecad/AppRun (created by scripts/setup_freecad_dev.sh)
#   4. /opt/freecad/AppRun
#
# Local dev: run scripts/setup_freecad_dev.sh or set CBCS_APPRUN / FREECAD_APPRUN.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOCAL_APPRUN="$HOME/opt/freecad/AppRun"
SYSTEM_APPRUN="/opt/freecad/AppRun"

if [[ -n "${CBCS_APPRUN:-}" ]]; then
  APPRUN="$CBCS_APPRUN"
elif [[ -n "${FREECAD_APPRUN:-}" ]]; then
  APPRUN="$FREECAD_APPRUN"
elif [[ -x "$LOCAL_APPRUN" ]]; then
  APPRUN="$LOCAL_APPRUN"
else
  APPRUN="$SYSTEM_APPRUN"
fi

if [[ ! -x "$APPRUN" ]]; then
  echo "FreeCAD AppRun not found: $APPRUN" >&2
  echo "Set CBCS_APPRUN or FREECAD_APPRUN, or run ./scripts/setup_freecad_dev.sh" >&2
  exit 1
fi

export CBCS_APPRUN="$APPRUN"
echo "Using FreeCAD AppRun: $APPRUN"

cd "$ROOT"

if [[ "${1:-}" == "--probe" ]]; then
  exec python3 "$ROOT/dev_launch_editor.py" --probe --apprun "$APPRUN" "${@:2}"
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  exec python3 "$ROOT/dev_launch_editor.py" --dry-run --apprun "$APPRUN" "${@:2}"
fi

exec python3 "$ROOT/dev_launch_editor.py" --foreground --apprun "$APPRUN" "$@"
