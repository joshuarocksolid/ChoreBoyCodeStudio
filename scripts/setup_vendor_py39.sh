#!/usr/bin/env bash
# Populate ChoreBoyCodeStudio_artifacts/vendor_py39 for local Python 3.9 AppRun dev.
# Matches the shipped ChoreBoy bundle contract (cp39 manylinux tree-sitter core).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$(dirname "$ROOT")/ChoreBoyCodeStudio_artifacts}"
TARGET="$ARTIFACTS_DIR/vendor_py39"

echo "Installing Python 3.9 vendor bundle into: $TARGET"
mkdir -p "$TARGET"

pip3 install \
  pyflakes==3.4.0 tree-sitter==0.23.2 \
  tree-sitter-python==0.23.6 tree-sitter-json==0.24.8 \
  tree-sitter-html==0.23.2 tree-sitter-xml==0.7.0 \
  tree-sitter-css==0.23.2 tree-sitter-bash==0.23.3 \
  tree-sitter-markdown==0.3.2 tree-sitter-yaml==0.7.0 \
  tree-sitter-toml==0.7.0 tree-sitter-javascript==0.23.1 \
  jedi parso isort tomli rope \
  pytest==8.3.4 pluggy iniconfig exceptiongroup \
  --target="$TARGET" \
  --python-version=3.9 \
  --only-binary=:all: \
  --platform=manylinux_2_17_x86_64

pip3 install "black==24.10.0" "click>=8.0,<8.2" --no-binary=black --target="$TARGET" --upgrade --force-reinstall

echo "Overlaying cp39 tree-sitter core binding..."
python3 "$ROOT/scripts/overlay_cp39_tree_sitter_binding.py" --artifacts-dir "$ARTIFACTS_DIR"

echo ""
echo "Done. Verify with:"
echo "  ./run_dev.sh --probe"
