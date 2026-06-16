#!/usr/bin/env bash
# Recreate the local editor-tooling venv under ChoreBoyCodeStudio_artifacts.
# This venv is for IDE/static-analysis tools only; the app runs through AppRun.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$(dirname "$ROOT")/ChoreBoyCodeStudio_artifacts}"
TARGET="$ARTIFACTS_DIR/.venv-editor"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3 and retry." >&2
  exit 1
fi

case "$TARGET" in
  ""|"/")
    echo "Refusing to recreate unsafe venv target: '$TARGET'" >&2
    exit 1
    ;;
esac

echo "Recreating editor tooling venv at: $TARGET"
mkdir -p "$ARTIFACTS_DIR"
rm -rf "$TARGET"
python3 -m venv "$TARGET"

"$TARGET/bin/python" -m pip install --upgrade pip
"$TARGET/bin/python" -m pip install "pyright==1.1.410"

echo ""
echo "Done. Use this venv for pyright/IDE tooling only:"
echo "  source \"$TARGET/bin/activate\""
echo ""
echo "Do not activate it before ./run_dev.sh; the editor runtime uses FreeCAD AppRun."
