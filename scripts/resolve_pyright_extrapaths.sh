#!/usr/bin/env bash
# Emit FreeCAD site-packages for pyright extraPaths (py39 dev preferred, else Cloud py311).
set -euo pipefail
PY39="${HOME}/opt/freecad/lib/python3.9/site-packages"
PY311="/opt/freecad/usr/lib/python3.11/site-packages"
if [[ -d "${PY39}/PySide2" ]]; then
  printf '%s\n' "${PY39}"
elif [[ -d "${PY311}/PySide2" ]]; then
  printf '%s\n' "${PY311}"
else
  echo "resolve_pyright_extrapaths: no PySide2 site-packages found" >&2
  exit 1
fi
