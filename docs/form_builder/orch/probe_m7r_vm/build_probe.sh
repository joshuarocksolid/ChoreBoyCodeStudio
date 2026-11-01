#!/bin/sh
# Copy the app source this probe imports. Run on the build machine, then submit
# the probe directory. The copy does not need the repository.
set -eu
HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
SRC=${1:-$(git -C "$HERE" rev-parse --show-toplevel)}
rm -rf "$HERE/payload"
mkdir -p "$HERE/payload"
# BSD and GNU tar both honor these excludes.
tar -C "$SRC" \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'tests' \
  -cf - app run_editor.py \
  | tar -C "$HERE/payload" -xf -
# The preview child is this probe's entry. It is the file AppRun launches.
# It is not the product script.
cp "$HERE/child_entry.py" "$HERE/payload/run_form_preview.py"
# The speed form is built in the probe. Try mode reads the invoice fixture.
# The tar above excludes tests, so the fixture is copied beside the payload.
rm -rf "$HERE/fixture"
mkdir -p "$HERE/fixture"
cp -R "$SRC/tests/form_builder/fixtures/m7/." "$HERE/fixture/"
find "$HERE/payload" -name '__pycache__' -type d -prune -exec rm -rf {} + || true
BYTES=$(du -sk "$HERE/payload" | awk '{print $1}')
echo "payload ${BYTES} KiB"
if [ "$BYTES" -gt 40960 ]; then
  echo "payload is over 40 MiB" >&2
  exit 1
fi
