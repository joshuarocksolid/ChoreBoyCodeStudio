#!/usr/bin/env bash
#
# cloud_setup_screenshot_runtime.sh
# ---------------------------------
# Idempotent bootstrap for the ChoreBoy Code Studio *development runtime* used to
# launch the real application (FreeCAD + PySide2) and capture screenshots for the
# Complete Edition user manual.
#
# This is wired into `.cursor/environment.json` as the cloud-agent `install`
# command so that, after the first run, Cursor snapshots the result and future
# cloud agents boot with the runtime already present (no reinstall). It is also
# safe to run by hand on a fresh Linux dev box.
#
# It is intentionally IDEMPOTENT: every step is guarded by an existence check so
# the script survives snapshot expiry / partial-cache re-runs without redoing
# completed work.
#
# What it provisions:
#   1. System (apt) packages required by Qt's xcb platform plugin and by the
#      screenshot capture tooling (only if missing and apt/sudo are available;
#      in the cloud these normally come from .cursor/Dockerfile).
#   2. Miniconda (if `conda` is not already on PATH).
#   3. A FreeCAD 1.0 + Python 3.9 + PySide2 conda env at ~/opt/freecad with an
#      AppRun wrapper (via scripts/setup_freecad_dev.sh).
#   4. The Python 3.9 vendor bundle (tree-sitter, jedi, black, pyflakes, pytest,
#      ...) under $CBCS_ARTIFACTS_DIR/vendor_py39 (via scripts/setup_vendor_py39.sh).
#
# After this completes, launch the app with:
#   export FREECAD_APPRUN="$HOME/opt/freecad/AppRun"
#   export CBCS_ARTIFACTS_DIR="$HOME/cbcs_artifacts"
#   DISPLAY=:1 ./run_dev.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FREECAD_DEV_PREFIX="${FREECAD_DEV_PREFIX:-$HOME/opt/freecad}"
CBCS_ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-$HOME/cbcs_artifacts}"
MINICONDA_PREFIX="${MINICONDA_PREFIX:-$HOME/miniconda3}"
export FREECAD_DEV_PREFIX CBCS_ARTIFACTS_DIR

log() { printf '\n[cloud-setup] %s\n' "$*"; }

# ---------------------------------------------------------------------------
# 1. System (apt) packages for Qt xcb + screenshot capture.
#    In the cloud these are provided by .cursor/Dockerfile; this block is a
#    self-healing fallback for raw dev boxes / snapshot-fallback boots.
# ---------------------------------------------------------------------------
ensure_apt_deps() {
  local needed=(
    libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-cursor0
    libxkbcommon-x11-0 libegl1
    imagemagick x11-utils wmctrl xdotool scrot
  )
  # Quick check: if the key capture tools already exist, skip apt entirely.
  if command -v import >/dev/null 2>&1 && command -v wmctrl >/dev/null 2>&1 \
     && command -v xdotool >/dev/null 2>&1 && command -v scrot >/dev/null 2>&1; then
    log "apt deps already satisfied; skipping."
    return 0
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    log "apt-get unavailable; assuming system deps are baked into the image."
    return 0
  fi
  local SUDO=""
  if [[ "$(id -u)" -ne 0 ]]; then
    if sudo -n true >/dev/null 2>&1; then
      SUDO="sudo"
    else
      log "No root/sudo; skipping apt step (rely on image-provided deps)."
      return 0
    fi
  fi
  log "Installing apt packages: ${needed[*]}"
  $SUDO apt-get update -y
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends "${needed[@]}"
}

# ---------------------------------------------------------------------------
# 2. Miniconda.
# ---------------------------------------------------------------------------
ensure_conda() {
  if command -v conda >/dev/null 2>&1; then
    log "conda already on PATH ($(command -v conda))."
  elif [[ -x "$MINICONDA_PREFIX/bin/conda" ]]; then
    log "conda found at $MINICONDA_PREFIX/bin/conda."
    export PATH="$MINICONDA_PREFIX/bin:$PATH"
  else
    log "Installing Miniconda to $MINICONDA_PREFIX ..."
    local installer="/tmp/miniconda_installer.sh"
    curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o "$installer"
    bash "$installer" -b -p "$MINICONDA_PREFIX"
    rm -f "$installer"
    export PATH="$MINICONDA_PREFIX/bin:$PATH"
  fi
  # Accept channel Terms of Service (no-op if already accepted / not required).
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------------------
# 3. FreeCAD + PySide2 conda env at ~/opt/freecad.
# ---------------------------------------------------------------------------
ensure_freecad() {
  if [[ -x "$FREECAD_DEV_PREFIX/AppRun" ]] \
     && "$FREECAD_DEV_PREFIX/AppRun" -c "import PySide2, FreeCAD" >/dev/null 2>&1; then
    log "FreeCAD dev runtime already present at $FREECAD_DEV_PREFIX/AppRun."
    return 0
  fi
  log "Provisioning FreeCAD + PySide2 dev runtime via scripts/setup_freecad_dev.sh ..."
  # Make `conda` available to the sub-script's `command -v conda` check.
  export PATH="$MINICONDA_PREFIX/bin:$PATH"
  FREECAD_DEV_PREFIX="$FREECAD_DEV_PREFIX" bash "$ROOT/scripts/setup_freecad_dev.sh"
}

# ---------------------------------------------------------------------------
# 4. Python 3.9 vendor bundle.
# ---------------------------------------------------------------------------
ensure_vendor() {
  local vendor_py39="$CBCS_ARTIFACTS_DIR/vendor_py39"
  if [[ -d "$vendor_py39/tree_sitter" ]] && [[ -d "$vendor_py39/jedi" ]]; then
    log "Vendor bundle already populated at $vendor_py39."
    return 0
  fi
  log "Populating Python 3.9 vendor bundle via scripts/setup_vendor_py39.sh ..."
  # Drop a dangling/foreign repo-root vendor symlink so the launcher can re-link it.
  if [[ -L "$ROOT/vendor" ]]; then
    rm -f "$ROOT/vendor"
  fi
  CBCS_ARTIFACTS_DIR="$CBCS_ARTIFACTS_DIR" bash "$ROOT/scripts/setup_vendor_py39.sh"
}

# ---------------------------------------------------------------------------
# Verification.
# ---------------------------------------------------------------------------
verify() {
  log "Verifying runtime ..."
  "$FREECAD_DEV_PREFIX/AppRun" -c \
    "import sys; print('AppRun Python:', sys.version.split()[0]); import PySide2, FreeCAD; print('PySide2 + FreeCAD import OK')"
  if [[ -d "$CBCS_ARTIFACTS_DIR/vendor_py39/tree_sitter" ]]; then
    log "Vendor bundle present: $CBCS_ARTIFACTS_DIR/vendor_py39"
  fi
  log "Done. Launch with: FREECAD_APPRUN=\"$FREECAD_DEV_PREFIX/AppRun\" CBCS_ARTIFACTS_DIR=\"$CBCS_ARTIFACTS_DIR\" DISPLAY=:1 ./run_dev.sh"
}

main() {
  log "Repo root: $ROOT"
  ensure_apt_deps
  ensure_conda
  ensure_freecad
  ensure_vendor
  verify
}

main "$@"
