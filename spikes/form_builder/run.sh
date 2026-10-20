#!/bin/sh
ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
PY="/Applications/FreeCAD.app/Contents/Resources/bin/python"
cd "$ROOT"
exec "$PY" -m spikes.form_builder "$@"
