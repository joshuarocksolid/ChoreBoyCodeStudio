"""In-process screenshot capture harness for the Complete Edition manual.

Run through FreeCAD AppRun with a real X display, e.g.::

    FREECAD_APPRUN="$HOME/opt/freecad/AppRun" CBCS_ARTIFACTS_DIR="$HOME/cbcs_artifacts" \
    DISPLAY=:1 ./run_dev.sh   # (not this script; see below)

This script is launched by ``capture_run.sh`` through AppRun. It builds the real
MainWindow, loads the bundled example project, then drives dialogs/panels
programmatically and saves deterministic PNGs via ``QWidget.grab()``. This is the
reproducible, no-mouse capture method (QWidget.grab is DPI-stable and needs no
external tool), and replaces ad-hoc xdotool choreography.

Output PNGs are written to the directory given by ``CBCS_SHOT_OUT`` (default
``/tmp/caps``). A human curates and renames the good ones into ``screenshots/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = "/workspace"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
_VENDOR = os.path.join(REPO_ROOT, "vendor")
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
os.chdir(REPO_ROOT)

# Prevent the harness from spawning REPL / plugin-host subprocesses.
os.environ.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")

OUT_DIR = Path(os.environ.get("CBCS_SHOT_OUT", "/tmp/caps"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
EXAMPLE_PROJECT = os.environ.get("CBCS_DEMO_PROJECT", "/workspace/example_projects/crud_showcase")

from PySide2.QtCore import QTimer  # noqa: E402
from PySide2.QtWidgets import QApplication, QTabWidget  # noqa: E402

from app.bootstrap.capability_probe import run_startup_capability_probe  # noqa: E402
from app.shell.main_window import MainWindow  # noqa: E402


_LOG_FILE = OUT_DIR / "capture_progress.log"


def log(msg: str) -> None:
    line = f"[capture] {msg}"
    print(line, flush=True)
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
    except Exception:
        pass


def settle(app: QApplication, ms: int = 400) -> None:
    from PySide2.QtCore import QElapsedTimer

    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def grab(widget, name: str) -> None:
    path = OUT_DIR / name
    pix = widget.grab()
    pix.save(str(path))
    log(f"saved {path} ({pix.width()}x{pix.height()})")


def capture_modal_tabs(app, trigger, base_name: str, settle_ms: int = 900) -> None:
    """Open a modal dialog, grab each of its tabs, then close it."""

    def do_grab() -> None:
        dlg = app.activeModalWidget() or app.activeWindow()
        if dlg is None:
            log(f"{base_name}: no modal dialog found")
            return
        tabs = dlg.findChild(QTabWidget)
        if tabs is not None and tabs.count() > 0:
            for i in range(tabs.count()):
                tabs.setCurrentIndex(i)
                settle(app, 250)
                label = tabs.tabText(i).strip().lower().replace(" ", "_").replace("&", "")
                grab(dlg, f"{base_name}_{i:02d}_{label}.png")
        else:
            grab(dlg, f"{base_name}.png")
        dlg.close()

    QTimer.singleShot(settle_ms, do_grab)
    trigger()  # blocks in exec_(); the singleShot fires inside the modal loop


def capture_modal(app, trigger, name: str, settle_ms: int = 900) -> None:
    def do_grab() -> None:
        dlg = app.activeModalWidget() or app.activeWindow()
        if dlg is None:
            log(f"{name}: no modal dialog found")
            return
        grab(dlg, name)
        dlg.close()

    QTimer.singleShot(settle_ms, do_grab)
    trigger()


def main() -> int:
    log("main() starting")
    app = QApplication.instance() or QApplication(sys.argv)
    log("QApplication ready")
    report = run_startup_capability_probe()
    log(f"startup probe: {report.available_count}/{report.total_count} checks")
    log("building MainWindow")
    win = MainWindow(startup_report=report)
    log("MainWindow built")
    win.resize(1500, 950)
    win.show()
    log("window shown")
    settle(app, 800)

    # Load the bundled example project for realistic content.
    opened = False
    try:
        opened = bool(win._file_project_commands_workflow.open_project_by_path(EXAMPLE_PROJECT))
    except Exception as exc:  # pragma: no cover - diagnostic path
        log(f"open_project_by_path raised: {exc!r}")
    log(f"project opened={opened} ({EXAMPLE_PROJECT})")
    settle(app, 1500)

    grab(win, "win_project_loaded.png")

    # Open main.py so the editor shows real code and the Outline populates.
    try:
        main_py = os.path.join(EXAMPLE_PROJECT, "main.py")
        if win._editor_tab_factory.open_file_in_editor(main_py, preview=False):
            settle(app, 1200)
            grab(win, "win_editor_code.png")
        else:
            log("open main.py returned False")
    except Exception as exc:
        log(f"open main.py failed: {exc!r}")

    # Markdown preview of README.md.
    try:
        readme = os.path.join(EXAMPLE_PROJECT, "README.md")
        if win._editor_tab_factory.open_file_in_editor(readme, preview=False):
            settle(app, 600)
            win._editor_tab_workflow.handle_markdown_show_split_action()
            settle(app, 1000)
            grab(win, "win_markdown_split.png")
    except Exception as exc:
        log(f"markdown preview failed: {exc!r}")

    # Settings dialog: every tab.
    try:
        capture_modal_tabs(app, win._file_project_commands_workflow.handle_open_settings_action, "settings")
    except Exception as exc:
        log(f"settings capture failed: {exc!r}")
    settle(app, 400)

    # Test Explorer panel (requires a loaded project). Use _on_button_clicked so the
    # view_changed signal fires and the side panel actually switches.
    try:
        if win._activity_bar is not None:
            win._activity_bar._on_button_clicked("test_explorer")
        win._test_runner_workflow.refresh_discovery()
        settle(app, 2500)
        grab(win, "win_test_explorer.png")
        if win._activity_bar is not None:
            win._activity_bar._on_button_clicked("explorer")
        settle(app, 400)
    except Exception as exc:
        log(f"test explorer capture failed: {exc!r}")

    # New Project from Template (template picker dialog).
    try:
        capture_modal(
            app,
            win._file_project_commands_workflow.handle_new_project_from_template_action,
            "template_picker.png",
        )
    except Exception as exc:
        log(f"template picker capture failed: {exc!r}")
    settle(app, 400)

    # Plugin Manager dialog.
    try:
        capture_modal(app, win._plugin_dialog_workflow.handle_open_plugin_manager_action, "plugin_manager.png")
    except Exception as exc:
        log(f"plugin manager capture failed: {exc!r}")
    settle(app, 400)

    # Dark theme variant of the main window.
    try:
        from app.core import constants

        win._shell_preferences_runtime.handle_set_theme(constants.UI_THEME_MODE_DARK)
        settle(app, 1200)
        grab(win, "win_dark.png")
        win._shell_preferences_runtime.handle_set_theme(constants.UI_THEME_MODE_LIGHT)
        settle(app, 800)
    except Exception as exc:
        log(f"theme capture failed: {exc!r}")

    # Optional: a project that has tests, for the Test Explorer + results shots.
    tests_project = os.environ.get("CBCS_TESTS_PROJECT")
    if tests_project and os.path.isdir(tests_project):
        try:
            if win._file_project_commands_workflow.open_project_by_path(tests_project):
                settle(app, 1500)
                if win._activity_bar is not None:
                    win._activity_bar._on_button_clicked("test_explorer")
                win._test_runner_workflow.refresh_discovery()
                settle(app, 2500)
                grab(win, "win_test_explorer.png")
                # Run the tests and wait for outcomes, then capture results + Run Log.
                win._test_runner_workflow.run_all_tests()
                settle(app, 8000)
                grab(win, "win_test_results.png")
            else:
                log("open tests project returned False")
        except Exception as exc:
            log(f"tests capture failed: {exc!r}")

    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
