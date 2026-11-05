#!/bin/sh
# Run on the ChoreBoy guest. Do not set QT_QPA_PLATFORM.
set -eu
HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
if [ -d "$HERE/payload/app" ]; then
  ROOT=$HERE/payload
else
  ROOT=$HERE
fi
cd "$ROOT"
unset QT_QPA_PLATFORM
unset CBCS_QT_API
exec /opt/freecad/AppRun -c "import runpy, sys; sys.path.insert(0, '$ROOT'); runpy.run_path('$ROOT/run_probe.py', run_name='__main__')"
