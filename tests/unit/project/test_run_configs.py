"""Unit tests for run-config helper utilities."""

from __future__ import annotations

import pytest

from app.project.run_configs import (
    RunConfiguration,
    env_overrides_to_text,
    parse_env_overrides_text,
    parse_run_config,
    parse_run_configs,
    remove_run_config,
    upsert_run_config,
)

pytestmark = pytest.mark.unit


def test_parse_run_config_normalizes_payload() -> None:
    config = parse_run_config(
        {
            "name": "Debug Main",
            "entry_file": "app/main.py",
            "argv": ["--verbose"],
        }
    )

    assert config.name == "Debug Main"
    assert config.entry_file == "app/main.py"
    assert config.argv == ["--verbose"]
    assert config.working_directory is None
    assert config.env_overrides == {}
    assert config.safe_mode is None


def test_parse_run_config_normalizes_optional_overrides() -> None:
    config = parse_run_config(
        {
            "name": "Config",
            "entry_file": "run.py",
            "argv": [],
            "working_directory": "app",
            "env_overrides": {"APP_ENV": "dev"},
            "safe_mode": False,
        }
    )

    assert config.working_directory == "app"
    assert config.env_overrides == {"APP_ENV": "dev"}
    assert config.safe_mode is False


def test_parse_run_configs_skips_invalid_and_duplicate_names() -> None:
    configs = parse_run_configs(
        [
            {"name": "Default", "entry_file": "run.py", "argv": []},
            {"name": "", "entry_file": "bad.py"},
            {"name": "Default", "entry_file": "alt.py", "argv": []},
        ]
    )

    assert len(configs) == 1
    assert configs[0].entry_file == "run.py"


def test_upsert_run_config_replaces_by_name() -> None:
    existing = [
        RunConfiguration(name="Default", entry_file="run.py", argv=[]),
    ]
    updated = RunConfiguration(name="Default", entry_file="app/main.py", argv=[])

    merged = upsert_run_config(existing, updated)

    assert len(merged) == 1
    assert merged[0].entry_file == "app/main.py"


def test_parse_env_overrides_text_round_trip() -> None:
    parsed = parse_env_overrides_text("A=1, B= two")
    assert parsed == {"A": "1", "B": "two"}
    assert env_overrides_to_text(parsed) == "A=1, B=two"


def test_parse_env_overrides_text_rejects_missing_equals() -> None:
    with pytest.raises(ValueError, match="KEY=VALUE"):
        parse_env_overrides_text("A=1, INVALID")


def test_remove_run_config_removes_matching_name_only() -> None:
    existing = [
        RunConfiguration(name="Default", entry_file="run.py", argv=[]),
        RunConfiguration(name="Debug", entry_file="run.py", argv=[]),
    ]

    remaining = remove_run_config(existing, "Default")

    assert [config.name for config in remaining] == ["Debug"]
