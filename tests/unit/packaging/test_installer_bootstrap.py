"""Unit tests for the standalone installer bootstrap."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


pytestmark = pytest.mark.unit


def _load_bootstrap_module(module_name: str = "installer_bootstrap_test") -> ModuleType:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "packaging" / "bootstrap.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_bootstrap_runs_installer_from_package_root_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_bootstrap_module("installer_bootstrap_success")
    package_root = tmp_path / "package"
    installer_root = package_root / "installer"
    installer_root.mkdir(parents=True)
    marker_path = package_root / "install_marker.json"
    (installer_root / "install.py").write_text(
        "import json, os\n"
        f"with open({str(marker_path)!r}, 'w', encoding='utf-8') as handle:\n"
        "    json.dump({'cwd': os.getcwd(), 'root': os.environ.get('CBCS_PACKAGE_ROOT', '')}, handle)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(module.PACKAGE_ROOT_ENV, str(package_root))
    monkeypatch.chdir(tmp_path)

    module.main()

    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    diagnostic = json.loads((package_root / module.DIAGNOSTIC_FILENAME).read_text(encoding="utf-8"))
    assert marker["cwd"] == str(installer_root)
    assert marker["root"] == str(package_root)
    assert diagnostic["stage"] == "bootstrap_entered"
    assert diagnostic["root_source"] == "env"


def test_bootstrap_reports_missing_installer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_bootstrap_module("installer_bootstrap_missing")
    package_root = tmp_path / "package"
    (package_root / "installer").mkdir(parents=True)
    monkeypatch.setenv(module.PACKAGE_ROOT_ENV, str(package_root))

    with pytest.raises(RuntimeError, match="Installer entry missing"):
        module.main()

    diagnostic = json.loads((package_root / module.DIAGNOSTIC_FILENAME).read_text(encoding="utf-8"))
    assert diagnostic["stage"] == "bootstrap_error"
    assert "Installer entry missing" in diagnostic["error"]
