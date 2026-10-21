"""import app.features must not pull the Qt binding that is not selected."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]

_CHILD = r"""
import os
import sys

api = sys.argv[1]
blocked = [name for name in sys.argv[2].split(",") if name]
os.environ["CBCS_QT_API"] = api
attempted = []

class _Recorder:
    def find_spec(self, fullname, path, target=None):
        root = fullname.split(".", 1)[0]
        if root in blocked:
            attempted.append(fullname)
        return None

recorder = _Recorder()
sys.meta_path.insert(0, recorder)
probe_name = blocked[0] + ".QtCore"
if recorder.find_spec(probe_name, None) is not None:
    raise SystemExit("finder returned a spec for " + probe_name)
if attempted != [probe_name]:
    raise SystemExit("finder did not record " + probe_name)
attempted.clear()

import app.features
from app.features.spec import FEATURE_SPECS, feature_is_enabled

for spec in FEATURE_SPECS:
    feature_is_enabled(spec)

blocked_roots = set(blocked)
leaked = sorted(name for name in sys.modules if name.split(".", 1)[0] in blocked_roots)
if leaked:
    raise SystemExit("leaked " + ",".join(leaked))
if attempted:
    raise SystemExit("attempted " + ",".join(attempted))
"""


@pytest.mark.parametrize(
    ("qt_api", "blocked"),
    [
        ("pyside2", ("PySide6", "shiboken6")),
        ("pyside6", ("PySide2", "shiboken2")),
    ],
)
def test_import_app_features_does_not_import_the_other_binding(
    qt_api: str,
    blocked: tuple[str, ...],
) -> None:
    env = os.environ.copy()
    env["CBCS_QT_API"] = qt_api
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_REPO_ROOT), env["PYTHONPATH"]] if env.get("PYTHONPATH") else [str(_REPO_ROOT)]
    )
    env.pop("PYTEST_CURRENT_TEST", None)
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD, qt_api, ",".join(blocked)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
