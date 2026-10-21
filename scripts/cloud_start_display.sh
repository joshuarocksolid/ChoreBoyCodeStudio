#!/usr/bin/env bash
# Boot-time display check. Exits 0 when an X server is already up.
# Xvfb is started only when neither $DISPLAY nor :1 answers.
set -euo pipefail

display="${DISPLAY:-:1}"
if xdpyinfo -display "$display" >/dev/null 2>&1; then
  exit 0
fi
if [[ "$display" != ":1" ]] && xdpyinfo -display :1 >/dev/null 2>&1; then
  exit 0
fi

Xvfb :1 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset >/tmp/cbcs-xvfb.log 2>&1 &
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if xdpyinfo -display :1 >/dev/null 2>&1; then
    exit 0
  fi
  sleep 0.2
done
echo "Xvfb :1 did not become ready. See /tmp/cbcs-xvfb.log" >&2
exit 1
