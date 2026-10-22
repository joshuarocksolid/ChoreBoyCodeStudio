#!/usr/bin/env bash
# Populate ChoreBoyCodeStudio_artifacts/vendor_py39 for local Python 3.9 AppRun dev.
# Matches the shipped ChoreBoy bundle contract (cp39 manylinux tree-sitter core).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$(dirname "$ROOT")/ChoreBoyCodeStudio_artifacts}"
TARGET="$ARTIFACTS_DIR/vendor_py39"

echo "Installing Python 3.9 vendor bundle into: $TARGET"
mkdir -p "$TARGET"

TREE_SITTER_PINS=()
while IFS= read -r requirement; do
  TREE_SITTER_PINS+=("$requirement")
done < <(PYTHONPATH="$ROOT" python3 -c 'from app.packaging.tree_sitter_cp39 import iter_pip_requirements
print("\n".join(iter_pip_requirements()))')

pip3 install \
  pyflakes==3.4.0 \
  "${TREE_SITTER_PINS[@]}" \
  jedi parso isort tomli rope typing_extensions \
  pytest==8.3.4 pytest-timeout==2.3.1 pluggy iniconfig exceptiongroup \
  --target="$TARGET" \
  --python-version=3.9 \
  --only-binary=:all: \
  --platform=manylinux_2_17_x86_64

pip3 install "black==24.10.0" "click>=8.0,<8.2" --no-binary=black --target="$TARGET" --upgrade --force-reinstall

echo "Overlaying Linux tree-sitter core and grammar bindings..."
python3 "$ROOT/scripts/overlay_cp39_tree_sitter_binding.py" --artifacts-dir "$ARTIFACTS_DIR"

echo ""
echo "Done. Verify with:"
echo "  ./run_dev.sh --probe"
