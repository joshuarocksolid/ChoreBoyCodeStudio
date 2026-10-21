#!/usr/bin/env bash
# Node is required for npx pyright. Skip when node and npm are already on PATH.
set -euo pipefail

if [[ -f "$(dirname "$0")/cloud_runtime_lib.sh" ]]; then
  # shellcheck disable=SC1091
  source "$(dirname "$0")/cloud_runtime_lib.sh"
else
  # shellcheck disable=SC1091
  source /opt/cbcs/cloud_runtime_lib.sh
fi

cloud_load_pins
cloud_install_node
