#!/bin/sh
# Copy the app source this probe imports. Run on the build machine, then push
# the probe directory. The copy does not need the repository.
set -eu
HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
SRC=${1:-$(git -C "$HERE" rev-parse --show-toplevel)}
VENDOR=${CBCS_PGTEST_VENDOR:-/Users/local/Projects/ChoreBoyCodeStudio_artifacts/vendor_pgtest}
rm -rf "$HERE/payload"
mkdir -p "$HERE/payload"
tar -C "$SRC" \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'tests' \
  -cf - app run_editor.py run_schema_helper.py \
  | tar -C "$HERE/payload" -xf -
mkdir -p "$HERE/payload/tests/form_builder/perf" \
  "$HERE/payload/tests/form_builder/fixtures/m8"
cp "$SRC/tests/form_builder/perf/m8_paths.py" "$HERE/payload/tests/form_builder/perf/m8_paths.py"
cp "$SRC/tests/form_builder/perf/stats.py" "$HERE/payload/tests/form_builder/perf/stats.py"
cp "$SRC/tests/form_builder/fixtures/m8/make_shop.py" "$HERE/payload/tests/form_builder/fixtures/m8/make_shop.py"
touch "$HERE/payload/tests/__init__.py" \
  "$HERE/payload/tests/form_builder/__init__.py" \
  "$HERE/payload/tests/form_builder/perf/__init__.py" \
  "$HERE/payload/tests/form_builder/fixtures/__init__.py" \
  "$HERE/payload/tests/form_builder/fixtures/m8/__init__.py"
cp "$HERE/run_probe.py" "$HERE/payload/run_probe.py"
cp "$HERE/run_on_vm.sh" "$HERE/payload/run_on_vm.sh"
cp "$HERE/pyside6_alias.py" "$HERE/payload/pyside6_alias.py"
cp "$HERE/child_entry.py" "$HERE/payload/run_form_preview.py"
if [ -d "$VENDOR/pg8000" ] && [ -d "$VENDOR/scramp" ]; then
  cp -R "$VENDOR/pg8000" "$VENDOR/scramp" "$VENDOR/asn1crypto" "$HERE/payload/"
  cp -R "$VENDOR/pg8000-1.31.5.dist-info" "$VENDOR/scramp-1.4.17.dist-info" "$VENDOR/asn1crypto-1.5.1.dist-info" "$HERE/payload/"
fi
find "$HERE/payload" -name '__pycache__' -type d -prune -exec rm -rf {} + || true
BYTES=$(du -sk "$HERE/payload" | awk '{print $1}')
echo "payload ${BYTES} KiB"
if [ "$BYTES" -gt 40960 ]; then
  echo "payload is over 40 MiB" >&2
  exit 1
fi
