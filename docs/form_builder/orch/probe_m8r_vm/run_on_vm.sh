#!/bin/sh
# Run on the ChoreBoy guest. Do not set QT_QPA_PLATFORM.
set -eu
cd /mnt/cbprobe/incoming/m8r/payload
unset QT_QPA_PLATFORM
unset CBCS_QT_API
exec /opt/freecad/AppRun -c "import runpy, sys; sys.path.insert(0, '/mnt/cbprobe/incoming/m8r/payload'); runpy.run_path('/mnt/cbprobe/incoming/m8r/payload/run_probe.py', run_name='__main__')"
