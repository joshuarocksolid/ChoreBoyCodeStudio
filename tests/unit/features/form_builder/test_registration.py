"""The form builder installs only when the active binding is PySide6."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.run.runtime_launch import build_runpy_bootstrap_payload

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[4]

_CHILD = r"""
import os
import sys

api = sys.argv[1]
os.environ["CBCS_QT_API"] = api
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
os.environ.pop("CBCS_FORM_BUILDER", None)

from app.features.spec import FEATURE_SPECS, feature_is_enabled

spec = next(item for item in FEATURE_SPECS if item.key == "form-builder")
enabled = feature_is_enabled(spec)
wanted = api == "pyside6"
if enabled != wanted:
    raise SystemExit("enabled on %s -> %s" % (api, enabled))

if wanted:
    os.environ["CBCS_FORM_BUILDER"] = "0"
    if feature_is_enabled(spec):
        raise SystemExit("kill switch left the feature on")
    os.environ.pop("CBCS_FORM_BUILDER", None)

roots = ("PySide2", "PySide6", "shiboken2", "shiboken6")
leaked = sorted(name for name in sys.modules if name.split(".", 1)[0] in roots)
if leaked:
    raise SystemExit("enabled() imported " + ",".join(leaked))

if not wanted:
    raise SystemExit(0)

from app.shell.tab_content_providers import TabContentProviderRegistry, TabMatchContext

class _Window:
    def __init__(self):
        self._tab_content_registry = TabContentProviderRegistry()

class _Ctx:
    def __init__(self, window):
        self.w = window

window = _Window()
spec.install(_Ctx(window))
registry = window._tab_content_registry
ui = registry.provider_for("invoice.ui", TabMatchContext(project_root=None))
if ui is None or ui.provider_id != "form-builder.ui":
    raise SystemExit("missing .ui provider")
if registry.provider_for("invoice.UI", TabMatchContext(project_root=None)) is None:
    raise SystemExit("extension match is case sensitive")
forced = registry.provider_for(
    "invoice.ui",
    TabMatchContext(project_root=None, forced_text=True),
)
if forced is not None:
    raise SystemExit("forced text still matched")
if registry.provider_for("main.py", TabMatchContext(project_root=None)) is not None:
    raise SystemExit("non-ui matched")
"""


def _binding_installed(qt_api: str) -> bool:
    name = "PySide6" if qt_api == "pyside6" else "PySide2"
    return importlib.util.find_spec(name) is not None


def _run(script: Path, qt_api: str) -> subprocess.CompletedProcess[str]:
    payload = build_runpy_bootstrap_payload(
        script_path=str(script),
        path_entries=(str(_REPO_ROOT), str(_REPO_ROOT / "vendor")),
        argv=[str(script), qt_api],
    )
    env = os.environ.copy()
    env.pop("CBCS_FORM_BUILDER", None)
    entries = [str(_REPO_ROOT), str(_REPO_ROOT / "vendor")]
    if env.get("PYTHONPATH"):
        entries.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env.pop("PYTEST_CURRENT_TEST", None)
    return subprocess.run(
        [sys.executable, "-c", payload],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("qt_api", ["pyside2", "pyside6"])
def test_form_builder_registers_only_on_pyside6(qt_api: str, tmp_path: Path) -> None:
    if not _binding_installed(qt_api):
        pytest.skip("%s is not installed" % qt_api)
    script = tmp_path / "form_builder_register.py"
    script.write_text(_CHILD, encoding="utf-8")
    completed = _run(script, qt_api)
    assert completed.returncode == 0, completed.stdout + completed.stderr
