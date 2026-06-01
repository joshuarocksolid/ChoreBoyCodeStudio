#!/usr/bin/env bash
# Launch ChoreBoy Code Studio via dev_launch_editor.py (AppRun resolution in Python).
#
# Usage: ./run_dev.sh [--dry-run|--probe|--foreground] [extra args]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
exec python3 "$ROOT/dev_launch_editor.py" "$@"
