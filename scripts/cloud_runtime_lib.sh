# Shared helpers for the cloud FreeCAD 1.0 / 1.1 bootstrap.
# Sourced by the install script and by the image bake. Not executed directly.

cloud_log() {
  printf '\n[cloud-setup] %s\n' "$*"
}

cloud_as_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo -n "$@"
  fi
}

cloud_home() {
  if [[ "$(id -u)" -eq 0 ]]; then
    printf '%s\n' /home/ubuntu
  else
    printf '%s\n' "$HOME"
  fi
}

cloud_owner() {
  if [[ "$(id -u)" -eq 0 ]]; then
    printf '%s\n' ubuntu:ubuntu
  else
    printf '%s\n' "$(id -u):$(id -g)"
  fi
}

cloud_load_pins() {
  if [[ -n "${CBCS_RUNTIME_PINS:-}" ]]; then
    # shellcheck disable=SC1090
    source "$CBCS_RUNTIME_PINS"
    return 0
  fi
  local pins
  pins="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cloud_runtime_pins.env"
  # shellcheck disable=SC1090
  source "$pins"
}

cloud_download() {
  local url="$1" dest="$2" sha="$3"
  mkdir -p "$(dirname "$dest")"
  if [[ -f "$dest" ]] && echo "${sha}  ${dest}" | sha256sum -c - >/dev/null 2>&1; then
    cloud_log "cache hit $(basename "$dest")"
    return 0
  fi
  rm -f "$dest"
  cloud_log "downloading $(basename "$dest")"
  curl -fL --retry 5 --retry-delay 2 -o "${dest}.partial" "$url"
  mv "${dest}.partial" "$dest"
  echo "${sha}  ${dest}" | sha256sum -c -
}

cloud_extract_appimage() {
  local dest="$1" url="$2" sha="$3" version="$4" filename="$5"
  local stamp="${dest}/cbcs-cloud-stamp"
  local want="${version} ${sha}"
  if [[ -x "${dest}/AppRun" && -f "$stamp" && "$(cat "$stamp")" == "$want" ]]; then
    cloud_log "pinned FreeCAD ${version} already at ${dest}"
    return 0
  fi
  local cache="${CBCS_DOWNLOAD_CACHE:-$(cloud_home)/.cache/cbcs}"
  local image="${cache}/${filename}"
  cloud_download "$url" "$image" "$sha"
  chmod +x "$image"
  local work
  work="$(mktemp -d)"
  if ! (cd "$work" && "$image" --appimage-extract); then
    cloud_log "AppImage --appimage-extract failed; unsquashfs fallback"
    local offset
    offset="$(od -An -t u4 -j 8 -N 4 "$image" | tr -d ' ')"
    unsquashfs -d "${work}/squashfs-root" -o "$offset" "$image"
  fi
  if [[ ! -x "${work}/squashfs-root/AppRun" ]]; then
    echo "extract produced no AppRun for ${filename}" >&2
    rm -rf "$work"
    return 1
  fi
  cloud_as_root rm -rf "$dest"
  cloud_as_root mkdir -p "$(dirname "$dest")"
  cloud_as_root mv "${work}/squashfs-root" "$dest"
  cloud_as_root chown -R "$(cloud_owner)" "$dest"
  printf '%s\n' "$want" | cloud_as_root tee "$stamp" >/dev/null
  rm -rf "$work"
  local bytes
  bytes="$(du -sb "$image" | awk '{print $1}')"
  cloud_log "installed FreeCAD ${version} at ${dest} (download ${bytes} bytes)"
}

cloud_install_apt_packages() {
  local needed=(
    ca-certificates curl git sudo bzip2 xz-utils file squashfs-tools
    python3 python3-pip
    libgl1 libglib2.0-0 libgomp1 libxrender1 libsm6 libxi6
    libxkbcommon0 libxkbcommon-x11-0 libegl1 libopengl0
    libfontconfig1 libfreetype6 libx11-6 libxext6 libdbus-1-3 libnss3
    libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-cursor0
    libxcb-xfixes0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libxtst6
    libasound2t64
    imagemagick x11-utils wmctrl xdotool scrot xvfb
  )
  if command -v import >/dev/null 2>&1 \
    && command -v wmctrl >/dev/null 2>&1 \
    && command -v xdotool >/dev/null 2>&1 \
    && command -v scrot >/dev/null 2>&1 \
    && command -v unsquashfs >/dev/null 2>&1 \
    && command -v Xvfb >/dev/null 2>&1 \
    && dpkg -s libxcb-xinerama0 >/dev/null 2>&1; then
    cloud_log "apt packages already present"
    return 0
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    cloud_log "apt-get unavailable; assuming the image already has Qt libraries"
    return 0
  fi
  cloud_log "installing apt packages"
  cloud_as_root apt-get update -y
  cloud_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${needed[@]}"
}

cloud_install_node() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    cloud_log "node already present ($(node -v))"
    return 0
  fi
  local cache="${CBCS_DOWNLOAD_CACHE:-$(cloud_home)/.cache/cbcs}"
  local archive="${cache}/${NODE_FILENAME}"
  cloud_download "$NODE_URL" "$archive" "$NODE_SHA256"
  cloud_as_root tar -xJf "$archive" -C /usr/local --strip-components=1
  cloud_log "installed node $(node -v)"
}

cloud_install_miniconda() {
  local home prefix
  home="$(cloud_home)"
  prefix="${MINICONDA_PREFIX:-${home}/miniconda3}"
  if [[ -x "${prefix}/bin/conda" ]]; then
    cloud_log "conda present at ${prefix}"
    return 0
  fi
  local cache="${CBCS_DOWNLOAD_CACHE:-${home}/.cache/cbcs}"
  local installer="${cache}/${MINICONDA_FILENAME}"
  cloud_download "$MINICONDA_URL" "$installer" "$MINICONDA_SHA256"
  cloud_as_root mkdir -p "$home"
  cloud_as_root chown "$(cloud_owner)" "$home"
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u ubuntu -H bash "$installer" -b -p "$prefix"
  else
    bash "$installer" -b -p "$prefix"
  fi
  cloud_log "installed Miniconda at ${prefix}"
}

cloud_run_as_runtime_user() {
  local home prefix
  home="$(cloud_home)"
  prefix="${MINICONDA_PREFIX:-${home}/miniconda3}"
  if [[ "$(id -u)" -eq 0 ]]; then
    sudo -u ubuntu -H env \
      HOME="$home" \
      PATH="${prefix}/bin:${PATH}" \
      FREECAD_DEV_PREFIX="${FREECAD_DEV_PREFIX:-${home}/opt/freecad}" \
      FREECAD_CONDA_PKG="${FREECAD_CONDA_PKG:-freecad=1.0.0}" \
      CONDA_PLUGINS_AUTO_ACCEPT_TOS=yes \
      "$@"
  else
    PATH="${prefix}/bin:${PATH}" \
      FREECAD_DEV_PREFIX="${FREECAD_DEV_PREFIX:-${home}/opt/freecad}" \
      FREECAD_CONDA_PKG="${FREECAD_CONDA_PKG:-freecad=1.0.0}" \
      CONDA_PLUGINS_AUTO_ACCEPT_TOS=yes \
      "$@"
  fi
}

cloud_install_conda_freecad() {
  local home prefix script
  home="$(cloud_home)"
  prefix="${FREECAD_DEV_PREFIX:-${home}/opt/freecad}"
  if [[ -x "${prefix}/AppRun" ]] \
    && cloud_run_as_runtime_user "${prefix}/AppRun" -c "import PySide2, FreeCAD" >/dev/null 2>&1; then
    cloud_log "conda FreeCAD already present at ${prefix}/AppRun"
    return 0
  fi
  cloud_install_miniconda
  script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup_freecad_dev.sh"
  cloud_log "provisioning conda FreeCAD at ${prefix}"
  cloud_run_as_runtime_user bash "$script"
}

cloud_pin_pyside2_default() {
  local dest="$1"
  local apprun="${dest}/AppRun"
  if [[ -f "${dest}/AppRun.real" ]]; then
    return 0
  fi
  if ! "${apprun}" -c "import PySide6" >/dev/null 2>&1; then
    cloud_log "FreeCAD 1.0 AppRun imports PySide2 without a PySide6 default"
    return 0
  fi
  if ! "${apprun}" -c "import PySide2" >/dev/null 2>&1; then
    echo "FreeCAD 1.0 at ${dest} cannot import PySide2" >&2
    return 1
  fi
  cloud_log "FreeCAD 1.0 has both bindings; defaulting AppRun to CBCS_QT_API=pyside2"
  cloud_as_root mv "$apprun" "${dest}/AppRun.real"
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp" <<'EOF'
#!/bin/bash
# cbcs-pyside2-default: the 1.0 prefix ships both Qt bindings.
# An explicit CBCS_QT_API still wins.
if [[ -z "${CBCS_QT_API:-}" ]]; then
  export CBCS_QT_API=pyside2
fi
exec "$(dirname "$0")/AppRun.real" "$@"
EOF
  cloud_as_root cp "$tmp" "$apprun"
  cloud_as_root chmod 755 "$apprun"
  rm -f "$tmp"
}

cloud_write_named_file() {
  local path="$1" file="$2"
  cloud_as_root cp "$file" "$path"
  cloud_as_root chmod 755 "$path"
}

cloud_write_fb_python() {
  local dest="$1"
  local tmp
  tmp="$(mktemp)"
  # AppRun's `sys.executable` is the freecad binary, and it inherits the caller's
  # library path. The form-builder smoke needs a real interpreter whose
  # QT_QPA_PLATFORM the caller still controls.
  cat >"$tmp" <<EOF
#!/bin/bash
set -euo pipefail
export PYTHONHOME=${dest}/usr
export SSL_CERT_FILE=${dest}/usr/ssl/cacert.pem
export FONTCONFIG_FILE="\${FONTCONFIG_FILE:-/etc/fonts/fonts.conf}"
export FONTCONFIG_PATH="\${FONTCONFIG_PATH:-/etc/fonts}"
exec ${dest}/usr/bin/python "\$@"
EOF
  cloud_write_named_file /usr/local/bin/cbcs-fb-python "$tmp"
  rm -f "$tmp"
}

cloud_resolve_qt_tool() {
  local dest="$1" name="$2"
  local candidate
  for candidate in \
    "${dest}/usr/lib/qt6/${name}" \
    "${dest}/usr/lib/qt6/libexec/${name}" \
    "${dest}/usr/bin/${name}"
  do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

cloud_publish_qt_tool() {
  local binary="$1" wrapper="$2" lib_root="$3"
  local tmp
  tmp="$(mktemp)"
  if "$binary" -v >/dev/null 2>&1; then
    cat >"$tmp" <<EOF
#!/bin/bash
set -euo pipefail
exec $(printf '%q' "$binary") "\$@"
EOF
  else
    cat >"$tmp" <<EOF
#!/bin/bash
set -euo pipefail
export LD_LIBRARY_PATH="${lib_root}/usr/lib:${lib_root}/usr/lib/x86_64-linux-gnu\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
exec $(printf '%q' "$binary") "\$@"
EOF
  fi
  cloud_write_named_file "$wrapper" "$tmp"
  rm -f "$tmp"
  printf '%s\n' "$wrapper"
}

cloud_resolve_py39() {
  # ~/opt/freecad/AppRun on this image execs freecadcmd, which rejects --json.
  # The conda prefix's python is 3.9 and imports PySide6, so the py39 lane
  # can run pytest and the signal-table probe.
  local prefix python
  prefix="${FREECAD_DEV_PREFIX:-$(cloud_home)/opt/freecad}"
  python="${prefix}/bin/python"
  if [[ -x "$python" ]] && "$python" -c 'import PySide6' >/dev/null 2>&1; then
    printf '%s\n' "$python"
    return 0
  fi
  return 1
}

cloud_write_env_files() {
  local py311="$1" uic="$2" rcc="$3"
  local home artifacts tmp py39
  home="$(cloud_home)"
  artifacts="${CBCS_ARTIFACTS_DIR:-${home}/cbcs_artifacts}"
  py39=""
  if py39="$(cloud_resolve_py39)"; then
    cloud_log "Python 3.9 with PySide6: ${py39}"
  else
    cloud_log "no Python 3.9 with PySide6; CBCS_FB_PY39 left empty and the py39 lane skips"
  fi
  tmp="$(mktemp)"
  cat >"$tmp" <<EOF
FREECAD_APPRUN=${FREECAD_10_DEST}/AppRun
CBCS_FB_APPRUN_11=${FREECAD_11_DEST}/AppRun
CBCS_FB_PY311=${py311}
CBCS_FB_PY39=${py39}
CBCS_FB_UIC=${uic}
CBCS_FB_RCC=${rcc}
CBCS_ARTIFACTS_DIR=${artifacts}
EOF
  cloud_as_root cp "$tmp" /etc/cbcs-cloud.env
  cloud_as_root chmod 644 /etc/cbcs-cloud.env
  cat >"$tmp" <<'EOF'
# Login shells. Non-login agent shells should: set -a; . /etc/cbcs-cloud.env; set +a
if [[ -f /etc/cbcs-cloud.env ]]; then
  set -a
  # shellcheck disable=SC1091
  . /etc/cbcs-cloud.env
  set +a
fi
export DISPLAY="${DISPLAY:-:1}"
EOF
  cloud_as_root cp "$tmp" /etc/profile.d/cbcs-cloud.sh
  cloud_as_root chmod 644 /etc/profile.d/cbcs-cloud.sh
  rm -f "$tmp"
  cloud_as_root ln -sfn "${FREECAD_10_DEST}/AppRun" /usr/local/bin/cbcs-freecad
  cloud_as_root ln -sfn "${FREECAD_11_DEST}/AppRun" /usr/local/bin/cbcs-freecad-1.1
}

cloud_publish_freecad_11_tools() {
  local dest="$1"
  cloud_write_fb_python "$dest"
  local uic rcc
  uic="$(cloud_resolve_qt_tool "$dest" uic)"
  rcc="$(cloud_resolve_qt_tool "$dest" rcc)"
  uic="$(cloud_publish_qt_tool "$uic" /usr/local/bin/cbcs-fb-uic "$dest")"
  rcc="$(cloud_publish_qt_tool "$rcc" /usr/local/bin/cbcs-fb-rcc "$dest")"
  cloud_write_env_files /usr/local/bin/cbcs-fb-python "$uic" "$rcc"
}

cloud_verify_runtimes() {
  local home prefix
  home="$(cloud_home)"
  prefix="${FREECAD_DEV_PREFIX:-${home}/opt/freecad}"
  # FreeCAD treats a long -c string as a filesystem path and fails with
  # "File name too long". Keep each probe to one short statement.
  cloud_log "FreeCAD 1.0 AppRun"
  "${FREECAD_10_DEST}/AppRun" -c 'import sys,PySide2,FreeCAD; print(sys.version.split()[0], PySide2.__version__, FreeCAD.Version()[:3])'
  cloud_log "FreeCAD 1.1 AppRun"
  "${FREECAD_11_DEST}/AppRun" -c 'import sys,PySide6,FreeCAD; print(sys.version.split()[0], PySide6.__version__, FreeCAD.Version()[:3])'
  "${FREECAD_11_DEST}/AppRun" -c 'from PySide6 import QtUiTools, QtDesigner; print("qt6-modules-ok")'
  cloud_log "FreeCAD 1.1 python wrapper"
  /usr/local/bin/cbcs-fb-python -c 'from PySide6 import QtUiTools, QtDesigner; print("wrapper-ok")'
  cloud_log "Qt6 uic and rcc"
  # shellcheck disable=SC1091
  set -a
  # shellcheck disable=SC1091
  . /etc/cbcs-cloud.env
  set +a
  "$CBCS_FB_UIC" -v
  "$CBCS_FB_RCC" -v
  if [[ -x "${prefix}/AppRun" ]]; then
    cloud_log "conda FreeCAD 1.0 (Python 3.9)"
    "${prefix}/AppRun" -c 'import sys, PySide2, FreeCAD; print("python", sys.version.split()[0]); print("PySide2", PySide2.__version__); print("FreeCAD", FreeCAD.Version())'
  fi
}

cloud_install_appimages() {
  cloud_extract_appimage \
    "$FREECAD_10_DEST" "$FREECAD_10_URL" "$FREECAD_10_SHA256" \
    "$FREECAD_10_VERSION" "$FREECAD_10_FILENAME"
  cloud_pin_pyside2_default "$FREECAD_10_DEST"
  cloud_extract_appimage \
    "$FREECAD_11_DEST" "$FREECAD_11_URL" "$FREECAD_11_SHA256" \
    "$FREECAD_11_VERSION" "$FREECAD_11_FILENAME"
  cloud_publish_freecad_11_tools "$FREECAD_11_DEST"
}
