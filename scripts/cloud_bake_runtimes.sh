#!/usr/bin/env bash
# Image bake: apt is a separate layer. This script installs the two FreeCAD
# trees, the Python 3.9 conda prefix, and /etc/cbcs-cloud.env.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${HERE}/cloud_runtime_lib.sh"
cloud_load_pins

export CBCS_DOWNLOAD_CACHE="${CBCS_DOWNLOAD_CACHE:-/var/cache/cbcs}"
mkdir -p "$CBCS_DOWNLOAD_CACHE"

cloud_install_appimages
cloud_install_conda_freecad
cloud_verify_runtimes
rm -rf "$CBCS_DOWNLOAD_CACHE"
