#!/usr/bin/env bash
# One-time migration: move legacy vendor/ to vendor_py311/ under artifacts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$(dirname "$ROOT")/ChoreBoyCodeStudio_artifacts}"
LEGACY="$ARTIFACTS_DIR/vendor"
TARGET="$ARTIFACTS_DIR/vendor_py311"

if [[ ! -e "$LEGACY" ]]; then
  echo "No legacy vendor directory at $LEGACY — nothing to migrate."
  exit 0
fi

if [[ -e "$TARGET" ]]; then
  echo "Target already exists: $TARGET" >&2
  echo "Move or rename it manually before migrating." >&2
  exit 1
fi

echo "Moving $LEGACY -> $TARGET"
mv "$LEGACY" "$TARGET"
echo "Done. Run ./scripts/setup_vendor_py39.sh to create vendor_py39 for local Python 3.9 dev."
