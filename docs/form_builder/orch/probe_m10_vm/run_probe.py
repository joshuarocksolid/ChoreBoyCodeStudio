"""M10.1b. Build three apps in the live editor, package them, install them, run them.

Python 3.9. Do not set QT_QPA_PLATFORM. The guest has a display.
AppArmor makes os.getloadavg() raise. Pass a scratch directory as argv[1]
only when that directory may be deleted.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
# runpy.run_path on the guest does not put this directory on sys.path.
# app/ lives in the nested payload directory the build script copies.
PAYLOAD = HERE / "payload" if (HERE / "payload" / "app").is_dir() else HERE
for _path in (str(PAYLOAD), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _prepare_work() -> Path:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).resolve()
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
        return path
    path = Path("/tmp/m10_cbcs_work")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _boot(work: Path):
    os.environ.pop("QT_QPA_PLATFORM", None)
    os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    if str(PAYLOAD) not in sys.path:
        sys.path.insert(0, str(PAYLOAD))
    os.chdir(str(PAYLOAD))
    from app.qt.QtWidgets import QApplication
    from app.shell.main_window import MainWindow

    qapp = QApplication.instance() or QApplication(sys.argv)
    state = work / "state"
    state.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    window = MainWindow(state_root=str(state))
    window.resize(1400, 900)
    window.show()
    window.raise_()
    window.activateWindow()
    for _ in range(20):
        qapp.processEvents()
    ready_ms = int((time.perf_counter() - started) * 1000)
    return qapp, window, ready_ms


def _launch_use(install_dir: Path, module: str, class_name: str, shots: Path, mode: str) -> str:
    shots.mkdir(parents=True, exist_ok=True)
    script = Path("/tmp/m10_use.py")
    script.write_text((PAYLOAD / "use_app.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    env["M10_APP"] = str(install_dir / "app_files")
    env["M10_MODULE"] = module
    env["M10_CLASS"] = class_name
    env["M10_SHOTS"] = str(shots)
    env["M10_MODE"] = mode
    code = "import runpy; runpy.run_path('/tmp/m10_use.py')"
    started = time.perf_counter()
    proc = subprocess.run(
        ["/opt/freecad/AppRun", "-c", code],
        env=env,
        timeout=180,
        capture_output=True,
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    note = "rc=%s ms=%s" % (proc.returncode, elapsed)
    if proc.returncode != 0:
        note += " err=" + proc.stderr.decode("utf-8", "replace")[-400:]
    return note


def _launcher_shot(drive, app: str, install_dir: Path) -> None:
    desktops = list(install_dir.glob("*.desktop"))
    if not desktops:
        drive.step(app, "launcher", "Look for the installed desktop file.", "none", False)
        return
    text = desktops[0].read_text(encoding="utf-8")
    command = ""
    for line in text.splitlines():
        if line.startswith("Exec="):
            command = line.split("=", 1)[1].strip()
            break
    import shlex

    argv = shlex.split(command)
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    started = time.perf_counter()
    proc = subprocess.Popen(argv, env=env, cwd=str(install_dir))
    time.sleep(4)
    drive.timings["%s_installed_start_ms" % app] = int((time.perf_counter() - started) * 1000)
    drive.step(app, "launcher", "Start the installed .desktop Exec.", "pid %s screen %s" % (proc.pid, drive.shot()), proc.poll() is None)
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    from drive import Drive, loadavg

    results = HERE / "results"
    if results.exists():
        shutil.rmtree(results)
    results.mkdir(parents=True)
    work = _prepare_work()
    load, load_error = loadavg()
    facts = {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "loadavg": load,
        "loadavg_error": load_error,
        "work": str(work),
    }
    try:
        qapp, window, ready_ms = _boot(work)
    except Exception:
        facts["boot_error"] = traceback.format_exc()
        (results / "facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
        print(facts["boot_error"], file=sys.stderr)
        return 1
    from apps import customer, package_and_install, products, shop

    drive = Drive(window, qapp, results)
    drive.timings["editor_ready_ms"] = ready_ms
    label = drive.find("shell.startupStatusLabel")
    saw = label.text() if label is not None and hasattr(label, "text") else drive.shot()
    drive.step("editor", "ready", "Start Code Studio.", "ready in %s ms; status %s" % (ready_ms, saw), True)
    roots = {}
    installs = {}
    try:
        roots["customer"] = customer(drive, work)
        if roots["customer"] is not None:
            installs["customer"] = package_and_install(drive, "customer", roots["customer"], work / "export" / "customer")
        roots["products"] = products(drive, work)
        if roots["products"] is not None:
            installs["products"] = package_and_install(drive, "products", roots["products"], work / "export" / "products")
        roots["shop"] = shop(drive, work)
        if roots["shop"] is not None:
            installs["shop"] = package_and_install(drive, "shop", roots["shop"], work / "export" / "shop")
        uses = {
            "customer": ("forms.customer_card_window", "CustomerCardWindow", "record"),
            "products": ("forms.products_list_window", "ProductsListWindow", "list"),
            "shop": ("forms.shop_desk_window", "ShopDeskWindow", "desk"),
        }
        for app, install_dir in installs.items():
            if install_dir is None:
                continue
            _launcher_shot(drive, app, install_dir)
            module, class_name, mode = uses[app]
            note = _launch_use(install_dir, module, class_name, results / app / "installed", mode)
            drive.step(app, "use-installed", "Use the installed app_files window.", note, "rc=0" in note)
    except Exception:
        facts["run_error"] = traceback.format_exc()
        print(facts["run_error"], file=sys.stderr)
        drive.step("editor", "crash", "The probe hit an exception.", facts["run_error"][-500:], False)
    facts["timings"] = drive.timings
    facts["failures"] = drive.failures
    (results / "facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    (results / "timings.json").write_text(json.dumps(drive.timings, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(facts, indent=2), flush=True)
    window.close()
    return 1 if drive.failures or facts.get("run_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
