#!/bin/sh
# Copy the app and the speed harness this probe imports. Run on the Mac, then
# submit the probe directory. The copy does not need the repository.
set -eu
HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
SRC=${1:-$(git -C "$HERE" rev-parse --show-toplevel)}
rm -rf "$HERE/payload"
mkdir -p "$HERE/payload"
tar -C "$SRC" \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'tests' \
  -cf - app run_editor.py run_form_preview.py \
  | tar -C "$HERE/payload" -xf -
mkdir -p "$HERE/payload/tests/form_builder" \
  "$HERE/payload/tests/support" \
  "$HERE/payload/tests/unit/features"
cp -R "$SRC/testing" "$HERE/payload/testing"
cp -R "$SRC/tests/form_builder/perf" "$HERE/payload/tests/form_builder/perf"
cp -R "$SRC/tests/form_builder/qtside" "$HERE/payload/tests/form_builder/qtside"
cp -R "$SRC/tests/form_builder/engine" "$HERE/payload/tests/form_builder/engine"
cp -R "$SRC/tests/form_builder/inspector" "$HERE/payload/tests/form_builder/inspector"
cp -R "$SRC/tests/support/form_builder" "$HERE/payload/tests/support/form_builder"
cp -R "$SRC/tests/unit/features/form_builder" "$HERE/payload/tests/unit/features/form_builder"
touch "$HERE/payload/tests/__init__.py" \
  "$HERE/payload/tests/form_builder/__init__.py" \
  "$HERE/payload/tests/support/__init__.py" \
  "$HERE/payload/tests/unit/__init__.py" \
  "$HERE/payload/tests/unit/features/__init__.py"
cp "$HERE/run_probe.py" "$HERE/payload/run_probe.py"
cp "$HERE/profile_surface.py" "$HERE/payload/profile_surface.py"
cp "$HERE/events_probe.py" "$HERE/payload/events_probe.py"
cp "$HERE/run_on_vm.sh" "$HERE/payload/run_on_vm.sh"
cp "$HERE/qt_alias.py" "$HERE/payload/qt_alias.py"
find "$HERE/payload" -name '__pycache__' -type d -prune -exec rm -rf {} + || true
find "$HERE/payload" -name '*.pyc' -delete || true
BYTES=$(du -sk "$HERE/payload" | awk '{print $1}')
echo "payload ${BYTES} KiB"
if [ "$BYTES" -gt 40960 ]; then
  echo "payload is over 40 MiB" >&2
  exit 1
fi
