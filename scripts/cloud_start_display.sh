#!/usr/bin/env bash
# Boot-time display check. Exits 0 when an X server is already up.
# Xvfb is started only when neither $DISPLAY nor :1 answers.
# dockerd is started when docker.io is installed. A daemon that cannot
# run does not fail this script; the pg93 gate reports that itself.
set -euo pipefail

start_dockerd() {
  if ! command -v dockerd >/dev/null 2>&1; then
    echo "dockerd is not installed" >&2
    return 0
  fi
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  sudo -n mkdir -p /var/run /var/lib/docker || true
  sudo -n dockerd --group ubuntu >/tmp/cbcs-dockerd.log 2>&1 &
  local _
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "dockerd did not become ready. See /tmp/cbcs-dockerd.log" >&2
}

start_dockerd

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
