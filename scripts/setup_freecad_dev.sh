#!/usr/bin/env bash
# Set up a local FreeCAD 1.0 + Python 3.9 environment for dev (matches ChoreBoy).
# Creates a conda env at ~/opt/freecad and an AppRun wrapper so run_dev.sh can use it.
set -e

PREFIX="${FREECAD_DEV_PREFIX:-$HOME/opt/freecad}"
# Cloud pins this to freecad=1.0.0. Local runs keep the unpinned package name.
FREECAD_CONDA_PKG="${FREECAD_CONDA_PKG:-freecad}"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found. Install Miniconda: https://docs.conda.io/en/latest/miniconda.html"
  exit 1
fi

export CONDA_PLUGINS_AUTO_ACCEPT_TOS="${CONDA_PLUGINS_AUTO_ACCEPT_TOS:-yes}"
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true

if [[ -x "$PREFIX/AppRun" ]] && "$PREFIX/AppRun" -c "import PySide2, FreeCAD" >/dev/null 2>&1; then
  echo "FreeCAD dev runtime already present at $PREFIX/AppRun."
  exit 0
fi

echo "Setting up FreeCAD 1.0 + Python 3.9 at: $PREFIX"
if [[ -d "$PREFIX/bin" ]] && [[ -x "$PREFIX/bin/python" ]]; then
  echo "Conda env already exists at $PREFIX. Installing/updating freecad..."
  eval "$(conda shell.bash hook)"
  conda activate "$PREFIX"
  conda install -c conda-forge "$FREECAD_CONDA_PKG" pyside2 -y
else
  echo "Creating conda env with python=3.9, ${FREECAD_CONDA_PKG}, and pyside2..."
  conda create -p "$PREFIX" -c conda-forge python=3.9 "$FREECAD_CONDA_PKG" pyside2 -y
fi

FREECADCMD="$PREFIX/bin/freecadcmd"
if [[ ! -x "$FREECADCMD" ]]; then
  echo "Expected $FREECADCMD not found."
  exit 1
fi

# AppRun must run freecadcmd (FreeCAD's launcher), not raw python. freecadcmd initializes
# FreeCAD's environment (Mod paths, PySide shim). ChoreBoy's AppRun does the same.
APPRUN="$PREFIX/AppRun"
echo "Creating AppRun wrapper at $APPRUN"
printf '%s\n' '#!/usr/bin/env bash' "exec \"$PREFIX/bin/freecadcmd\" \"\$@\"" > "$APPRUN"
chmod +x "$APPRUN"

echo ""
echo "Verifying runtime..."
"$APPRUN" -c "import sys; print('Python:', sys.version); import PySide2; import FreeCAD; print('PySide2 and FreeCAD OK')"
echo ""
echo "Done. To use this runtime when running the app:"
echo "  export FREECAD_APPRUN=\"$APPRUN\""
echo "  ./run_dev.sh"
echo ""
echo "To make it permanent, add to your shell profile:"
echo "  export FREECAD_APPRUN=\"$APPRUN\""
