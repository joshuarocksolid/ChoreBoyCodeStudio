"""Unit tests for run-config helper utilities."""

from __future__ import annotations

import pytest

from app.core import constants
from app.project.run_configs import RunConfiguration, parse_run_config, parse_run_configs, upsert_run_config

pytestmark = pytest.mark.unit


def test_parse_run_config_normalizes_payload() -> None:
    config = parse_run_config(
        {
            "name": "Debug Main",
            "entry_file": "app/main.py",
            "mode": constants.RUN_MODE_PYTHON_DEBUG,
            "argv": ["--verbose"],
        }
    )

    assert config.name == "Debug Main"
    assert config.entry_file == "app/main.py"
    assert config.mode == constants.RUN_MODE_PYTHON_DEBUG
    assert config.argv == ["--verbose"]


def test_parse_run_configs_skips_invalid_and_duplicate_names() -> None:
    configs = parse_run_configs(
        [
            {"name": "Default", "entry_file": "run.py", "mode": constants.RUN_MODE_PYTHON_SCRIPT, "argv": []},
            {"name": "", "entry_file": "bad.py"},
            {"name": "Default", "entry_file": "alt.py", "mode": constants.RUN_MODE_PYTHON_SCRIPT, "argv": []},
        ]
    )

    assert len(configs) == 1
    assert configs[0].entry_file == "run.py"


def test_upsert_run_config_replaces_by_name() -> None:
    existing = [
        RunConfiguration(name="Default", entry_file="run.py", mode=constants.RUN_MODE_PYTHON_SCRIPT, argv=[]),
    ]
    updated = RunConfiguration(name="Default", entry_file="app/main.py", mode=constants.RUN_MODE_QT_APP, argv=[])

    merged = upsert_run_config(existing, updated)

    assert len(merged) == 1
    assert merged[0].entry_file == "app/main.py"
