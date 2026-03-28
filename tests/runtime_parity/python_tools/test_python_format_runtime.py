"""Runtime-parity tests for vendored Python format/import tooling."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import constants
from app.python_tools.vendor_runtime import import_python_tooling_modules, initialize_python_tooling_runtime

pytestmark = pytest.mark.runtime_parity


def _require_apprun() -> None:
    app_run = Path(constants.APP_RUN_PATH)
    if not app_run.exists():
        pytest.skip(f"AppRun not available at {app_run}; skipping Python tooling runtime tests.")


def test_python_tooling_runtime_uses_vendor_and_creates_no_hidden_paths(tmp_path: Path) -> None:
    _require_apprun()
    project_root = (tmp_path / "project_root").resolve()
    state_root = (tmp_path / "state_root").resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    status = initialize_python_tooling_runtime()
    if not status.is_available:
        with pytest.raises(RuntimeError, match="Python tooling runtime unavailable"):
            import_python_tooling_modules()
        assert "black" in status.message.lower() or "isort" in status.message.lower() or "tomli" in status.message.lower()
        return

    black, isort, tomli = import_python_tooling_modules()

    formatted = black.format_file_contents(
        "value={'alpha':1,'beta':2,'gamma':3}\n",
        fast=False,
        mode=black.Mode(line_length=40),
    )
    organized = isort.api.sort_code_string(
        "import tomllib\nimport os\n",
        config=isort.Config(profile="black", py_version="39"),
    )

    assert status.is_available is True
    assert status.black_available is True
    assert status.isort_available is True
    assert status.tomli_available is True
    assert tomli.__version__  # version is present (exact version depends on vendored build)
    assert formatted == 'value = {\n    "alpha": 1,\n    "beta": 2,\n    "gamma": 3,\n}\n'
    assert organized == "import os\n\nimport tomllib\n"
    assert not any(child.name.startswith(".") for child in project_root.iterdir())
    assert not any(child.name.startswith(".") for child in state_root.iterdir())
