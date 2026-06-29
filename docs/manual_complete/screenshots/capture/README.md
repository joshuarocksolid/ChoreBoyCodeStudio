# Screenshot Capture Guide (Complete Edition)

This guide documents the **reproducible recipe** used to capture every screenshot in
the Complete Edition manual. Following it lets a future maintainer re-capture any
image deterministically when the UI changes.

## Why a recipe exists

Screenshots go stale when the UI changes. The maintenance policy requires replacing
affected screenshots in the same change that alters the UI. A scripted, repeatable
capture process makes that practical.

## Environment

Screenshots are captured from the **development runtime**, which runs the real
application through FreeCAD's bundled Python (PySide2), launched under an X server.

> [!NOTE] The development runtime uses conda-packaged FreeCAD + PySide2 (Python 3.9).
> This is visually very close to, but not pixel-identical to, the production ChoreBoy
> appliance. Window chrome (title bar, borders) comes from the host window manager.
> Layout, labels, panels, and behavior are accurate.

### One-time setup (Cursor Cloud / Linux dev box)

```bash
# 1. Miniconda (if not present)
curl -sSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p "$HOME/miniconda3"
export PATH="$HOME/miniconda3/bin:$PATH"
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# 2. FreeCAD 1.0 + PySide2 dev runtime -> ~/opt/freecad/AppRun
FREECAD_DEV_PREFIX="$HOME/opt/freecad" bash scripts/setup_freecad_dev.sh

# 3. Vendored Python deps (tree-sitter, jedi, black, pyflakes, pytest, ...)
[ -L vendor ] && rm vendor
CBCS_ARTIFACTS_DIR="$HOME/cbcs_artifacts" bash scripts/setup_vendor_py39.sh

# 4. Capture tools
sudo apt-get install -y scrot imagemagick x11-utils wmctrl   # xdotool is usually preinstalled
```

### Launch the editor

```bash
export FREECAD_APPRUN="$HOME/opt/freecad/AppRun"
export CBCS_ARTIFACTS_DIR="$HOME/cbcs_artifacts"
export DISPLAY=:1
cd /workspace && ./run_dev.sh        # launches DETACHED; do not pipe stdout (held open by child)
```

## Capture method (chosen): in-process Qt grab (primary)

The **primary, reproducible** method is an in-process capture harness,
`capture_harness.py`, run through AppRun. It builds the real `MainWindow`, loads the
demo project, drives dialogs/panels programmatically, and saves each as a PNG via
`QWidget.grab()`. This needs **no mouse choreography and no window manager**, is
DPI-stable, and produces dozens of deterministic shots in one run.

```bash
# A clean, headless X display avoids any wedged-session issues:
Xvfb :99 -screen 0 1600x1050x24 >/tmp/xvfb.log 2>&1 &
DISPLAY=:99 CBCS_SHOT_OUT=/tmp/caps \
  docs/manual_complete/screenshots/capture/capture_run.sh
# Review /tmp/caps/*.png, then copy the good ones into screenshots/ with shot_list ids.
```

`capture_run.sh` sets `FREECAD_APPRUN`, `CBCS_ARTIFACTS_DIR`, `XAUTHORITY`,
`QT_QPA_PLATFORM=xcb`, and `CBCS_DISABLE_BACKGROUND_RUNTIME=1` (so no REPL/plugin-host
subprocesses spawn), then runs the harness through AppRun. Add new shots by extending
the capture sequence in `capture_harness.py` (call the relevant workflow method, then
`grab(...)`); modal dialogs are captured with `QTimer.singleShot` while their `exec_()`
loop runs.

> [!NOTE] On the standard desktop display (`:1`), a stale X session can wedge new Qt
> clients (QApplication hangs). Capturing on a throwaway `Xvfb` display sidesteps this
> and is fully deterministic because `QWidget.grab()` does not need a compositor.

## Alternative method: live-window capture (fallback)

For ad-hoc shots of the live app (or states the harness cannot reach yet), use
**ImageMagick window capture** (`import -window <id>`). It grabs only the application's
client area — no desktop wallpaper or panel — and is crisp.

```bash
export DISPLAY=:1
WID=$(xdotool search --name "ChoreBoy Code Studio" | head -1)

# Deterministic framing: un-maximize, then fix size + position.
wmctrl -ir "$WID" -b remove,maximized_vert,maximized_horz; sleep 1
xdotool windowsize "$WID" 1500 950
xdotool windowmove "$WID" 30 30
xdotool windowactivate "$WID"; sleep 1

import -window "$WID" docs/manual_complete/screenshots/<name>.png
```

For dialogs/popups, capture the dialog window by its own id (search by dialog title)
or capture the whole app window after the dialog opens.

## Conventions

- **Format:** PNG.
- **Baseline theme:** Light. Theme-specific shots (Dark, High Contrast) are captured
  intentionally and named with a theme suffix (e.g. `_dark`, `_hc_dark`).
- **Window size:** 1500x950 for the main window unless a wider capture is needed.
- **Clean state:** before capturing, switch the bottom panel away from the Python
  Console if the dev-only `freecadcmd` startup banner is visible there (it prints CLI
  usage to stderr on the dev runtime only), or click the console **Clear** button.
- **Naming:** `NN_topic[_variant].png`, zero-padded, matching `shot_list.json` ids.
- **Annotations:** numbered callouts on overview images are added with ImageMagick
  (`convert ... -fill ... -draw ...`) or kept as a separate `_annotated` file so the
  raw capture is preserved.

## Re-capturing after UI changes

1. Relaunch the editor on the current build.
2. Reproduce the exact state described in the shot's `purpose`/`state` note.
3. Re-run the capture command with the same filename (overwrites in place).
4. Run `python3 docs/manual_complete/build_manual.py --check` and rebuild the PDF.
