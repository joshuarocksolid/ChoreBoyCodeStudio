#!/bin/sh
# Copy the editor and the packaging tree this probe imports. Run on the host,
# then submit the probe directory. The copy does not need the repository.
set -eu
HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
SRC=${1:-$(git -C "$HERE" rev-parse --show-toplevel)}
rm -rf "$HERE/payload"
mkdir -p "$HERE/payload"
tar -C "$SRC" \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude 'tests' \
    -cf - app packaging run_editor.py run_form_preview.py \
    | tar -C "$HERE/payload" -xf -
cp "$HERE/run_probe.py" "$HERE/drive.py" "$HERE/apps.py" "$HERE/use_app.py" \
    "$HERE/run_on_vm.sh" "$HERE/payload/"
find "$HERE/payload" -name '__pycache__' -type d -prune -exec rm -rf {} + || true
find "$HERE/payload" -name '*.pyc' -delete || true
BYTES=$(du -sk "$HERE/payload" | awk '{print $1}')
echo "payload ${BYTES} KiB"
if [ "$BYTES" -gt 40960 ]; then
  echo "payload is over 40 MiB" >&2
  exit 1
fi
