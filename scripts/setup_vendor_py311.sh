#!/usr/bin/env bash
# Populate ChoreBoyCodeStudio_artifacts/vendor_py311 for Cloud / Python 3.11 AppRun dev.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$(dirname "$ROOT")/ChoreBoyCodeStudio_artifacts}"
TARGET="$ARTIFACTS_DIR/vendor_py311"

echo "Installing Python 3.11 vendor bundle into: $TARGET"
mkdir -p "$TARGET"

TREE_SITTER_PINS=()
while IFS= read -r requirement; do
  TREE_SITTER_PINS+=("$requirement")
done < <(PYTHONPATH="$ROOT" python3 -c 'from app.packaging.tree_sitter_cp39 import iter_pip_requirements
print("\n".join(iter_pip_requirements()))')

pip3 install pyflakes==3.4.0 \
  "${TREE_SITTER_PINS[@]}" \
  jedi parso "black==24.10.0" isort tomli rope typing_extensions \
  pytest==8.3.4 pytest-timeout==2.3.1 pluggy iniconfig exceptiongroup \
  --target="$TARGET" --python-version=3.11 --only-binary=:all: \
  --platform=manylinux_2_17_x86_64

echo ""
echo "Done. Verify with:"
echo "  CBCS_APPRUN=/opt/freecad/AppRun ./run_dev.sh --probe"
