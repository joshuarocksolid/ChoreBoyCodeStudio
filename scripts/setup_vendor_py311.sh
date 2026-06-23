#!/usr/bin/env bash
# Populate ChoreBoyCodeStudio_artifacts/vendor_py311 for Cloud / Python 3.11 AppRun dev.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$(dirname "$ROOT")/ChoreBoyCodeStudio_artifacts}"
TARGET="$ARTIFACTS_DIR/vendor_py311"

echo "Installing Python 3.11 vendor bundle into: $TARGET"
mkdir -p "$TARGET"

pip3 install pyflakes==3.4.0 tree-sitter==0.23.2 \
  tree-sitter-python==0.23.6 tree-sitter-json==0.24.8 \
  tree-sitter-html==0.23.2 tree-sitter-xml==0.7.0 \
  tree-sitter-css==0.23.2 tree-sitter-bash==0.23.3 \
  tree-sitter-markdown==0.3.2 tree-sitter-yaml==0.7.0 \
  tree-sitter-toml==0.7.0 tree-sitter-javascript==0.23.1 \
  tree-sitter-sql==0.3.9 \
  jedi parso "black==24.10.0" isort tomli rope typing_extensions \
  pytest==8.3.4 pytest-timeout==2.3.1 pluggy iniconfig exceptiongroup \
  --target="$TARGET" --python-version=3.11 --only-binary=:all: \
  --platform=manylinux_2_17_x86_64

echo ""
echo "Done. Verify with:"
echo "  CBCS_APPRUN=/opt/freecad/AppRun ./run_dev.sh --probe"
