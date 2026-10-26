"""import app.features must not pull the Qt binding that is not selected."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.run.runtime_launch import build_runpy_bootstrap_payload

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]

_CHILD = r"""
import os
import sys

api = sys.argv[1]
os.environ["CBCS_QT_API"] = api
roots = ("PySide2", "PySide6", "shiboken2", "shiboken6")
attempted = []

class _Recorder:
    def find_spec(self, fullname, path, target=None):
        root = fullname.split(".", 1)[0]
        if root in roots:
            attempted.append(fullname)
        return None

recorder = _Recorder()
sys.meta_path.insert(0, recorder)
probe_name = roots[0] + ".QtCore"
if recorder.find_spec(probe_name, None) is not None:
    raise SystemExit("finder returned a spec for " + probe_name)
if attempted != [probe_name]:
    raise SystemExit("finder did not record " + probe_name)
attempted.clear()

import app.features
from app.features.spec import FEATURE_SPECS, feature_is_enabled

for spec in FEATURE_SPECS:
    feature_is_enabled(spec)

leaked = sorted(name for name in sys.modules if name.split(".", 1)[0] in roots)
if leaked:
    raise SystemExit("leaked " + ",".join(leaked))
if attempted:
    raise SystemExit("attempted " + ",".join(attempted))
"""

_MAIN_WINDOW_CHILD = r"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

result_path = Path(sys.argv[1])

def finish(text):
    result_path.write_text(text, encoding="utf-8")
    print(text, flush=True)

if importlib.util.find_spec("PySide2") is None:
    finish("SKIP")
    raise SystemExit(0)

os.environ["CBCS_QT_API"] = "pyside2"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
roots = ("PySide6", "shiboken6")
attempted = []

class _Recorder:
    def find_spec(self, fullname, path, target=None):
        root = fullname.split(".", 1)[0]
        if root in roots:
            attempted.append(fullname)
        return None

sys.meta_path.insert(0, _Recorder())

from app.qt.QtWidgets import QApplication
from app.shell.main_window import MainWindow

if QApplication.instance() is None:
    QApplication([])
window = MainWindow(state_root=tempfile.mkdtemp())
window.close()

leaked = sorted(name for name in sys.modules if name.split(".", 1)[0] in roots)
if leaked:
    finish("leaked " + ",".join(leaked))
    raise SystemExit(1)
if attempted:
    finish("attempted " + ",".join(attempted))
    raise SystemExit(1)
finish("OK")
"""


def _child_env(qt_api: str) -> dict[str, str]:
    env = os.environ.copy()
    env["CBCS_QT_API"] = qt_api
    entries = [str(_REPO_ROOT), str(_REPO_ROOT / "vendor")]
    if env.get("PYTHONPATH"):
        entries.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env.pop("PYTEST_CURRENT_TEST", None)
    return env


def _run_child(script: Path, *args: str, qt_api: str) -> subprocess.CompletedProcess[str]:
    # AppRun's executable is FreeCAD. A script path opens as a document and
    # hangs. A short ``-c`` payload runpy's the child instead.
    payload = build_runpy_bootstrap_payload(
        script_path=str(script),
        path_entries=(str(_REPO_ROOT), str(_REPO_ROOT / "vendor")),
        argv=[str(script), *args],
    )
    return subprocess.run(
        [sys.executable, "-c", payload],
        cwd=_REPO_ROOT,
        env=_child_env(qt_api),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("qt_api", ["pyside2", "pyside6"])
def test_import_app_features_imports_no_qt_binding(qt_api: str, tmp_path: Path) -> None:
    script = tmp_path / "import_isolation.py"
    script.write_text(_CHILD, encoding="utf-8")
    completed = _run_child(script, qt_api, qt_api=qt_api)

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_pyside2_main_window_does_not_import_pyside6(tmp_path: Path) -> None:
    script = tmp_path / "main_window_isolation.py"
    result_path = tmp_path / "result.txt"
    script.write_text(_MAIN_WINDOW_CHILD, encoding="utf-8")
    completed = _run_child(script, str(result_path), qt_api="pyside2")
    result = result_path.read_text(encoding="utf-8") if result_path.exists() else ""
    if completed.returncode == 0 and result.strip() == "SKIP":
        pytest.skip("PySide2 is absent")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert result.strip() == "OK"
