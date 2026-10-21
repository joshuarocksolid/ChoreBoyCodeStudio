#!/usr/bin/env bash
# Idempotent cloud bootstrap.
# Heavy FreeCAD trees live in the image when .cursor/Dockerfile has run.
# This script still installs them when the image does not have them yet,
# then fills repo-local vendor bundles and the pyright npm package.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/scripts/cloud_runtime_lib.sh"

export CBCS_ARTIFACTS_DIR="${CBCS_ARTIFACTS_DIR:-${HOME}/cbcs_artifacts}"
export FREECAD_DEV_PREFIX="${FREECAD_DEV_PREFIX:-${HOME}/opt/freecad}"
export MINICONDA_PREFIX="${MINICONDA_PREFIX:-${HOME}/miniconda3}"
export CBCS_DOWNLOAD_CACHE="${CBCS_DOWNLOAD_CACHE:-${HOME}/.cache/cbcs}"

SECONDS=0
cloud_load_pins
cloud_log "repo root: ${ROOT}"
cloud_install_apt_packages
cloud_install_appimages
cloud_install_conda_freecad

ensure_vendor() {
  local profile="$1" marker_a="$2" marker_b="$3" script="$4"
  local target="${CBCS_ARTIFACTS_DIR}/vendor_${profile}"
  if [[ -d "${target}/${marker_a}" && -d "${target}/${marker_b}" ]]; then
    cloud_log "vendor_${profile} already present at ${target}"
    return 0
  fi
  if [[ -L "${ROOT}/vendor" ]]; then
    rm -f "${ROOT}/vendor"
  fi
  cloud_log "populating vendor_${profile}"
  CBCS_ARTIFACTS_DIR="$CBCS_ARTIFACTS_DIR" bash "${ROOT}/scripts/${script}"
}

ensure_vendor py39 tree_sitter jedi setup_vendor_py39.sh
ensure_vendor py311 tree_sitter jedi setup_vendor_py311.sh

if [[ -x "${ROOT}/node_modules/.bin/pyright" ]]; then
  cloud_log "pyright already installed"
elif command -v npm >/dev/null 2>&1; then
  cloud_log "installing npm devDependencies (pyright)"
  npm install --prefix "$ROOT" --no-package-lock --no-audit --no-fund
else
  cloud_log "npm missing; skipping pyright install"
fi

cloud_verify_runtimes
cloud_log "download cache bytes: $(du -sb "$CBCS_DOWNLOAD_CACHE" | awk '{print $1}')"
cloud_log "freecad 1.0 tree bytes: $(du -sb "$FREECAD_10_DEST" | awk '{print $1}')"
cloud_log "freecad 1.1 tree bytes: $(du -sb "$FREECAD_11_DEST" | awk '{print $1}')"
if [[ -d "$FREECAD_DEV_PREFIX" ]]; then
  cloud_log "conda prefix bytes: $(du -sb "$FREECAD_DEV_PREFIX" | awk '{print $1}')"
fi
cloud_log "install elapsed ${SECONDS}s"
