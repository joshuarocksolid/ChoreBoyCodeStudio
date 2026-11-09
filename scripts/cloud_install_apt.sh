#!/usr/bin/env bash
# Qt xcb, AppImage extract tools, and screenshot tools for the cloud image.
set -euo pipefail

if [[ -f "$(dirname "$0")/cloud_runtime_lib.sh" ]]; then
  # shellcheck disable=SC1091
  source "$(dirname "$0")/cloud_runtime_lib.sh"
else
  # shellcheck disable=SC1091
  source /opt/cbcs/cloud_runtime_lib.sh
fi

cloud_install_apt_packages
