"""Shared settings root versus the local state root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.bootstrap import paths, state_roots
from app.bootstrap.startup_problems import SHARED_SETTINGS_PROBLEM_ID, assemble_startup_problems
from app.core import constants

pytestmark = pytest.mark.unit


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CBCS_STATE_ROOT", raising=False)
    local = tmp_path / "FreeCAD" / "CBCS" / "state"
    monkeypatch.setattr(
        paths,
        "DEFAULT_PRODUCT_STATE_LAYOUT",
        paths.ProductStateLayout(
            install_base=local.parent,
            state_root=local,
            occupancy_filename=constants.GLOBAL_SETTINGS_FILENAME,
            migrating_suffix=constants.STATE_MIGRATING_SUFFIX,
            legacy_leaf=constants.GLOBAL_STATE_DIRNAME,
        ),
    )
    return fake_home


def test_unreachable_shared_root_falls_back_and_records_problem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    blocked = tmp_path / "not_a_directory"
    blocked.write_text("file", encoding="utf-8")
    monkeypatch.setenv("CBCS_STATE_ROOT", str(blocked / "settings"))
    local = Path(os.path.abspath(str(paths.DEFAULT_PRODUCT_STATE_LAYOUT.state_root)))

    choice = state_roots.resolve_settings_root()

    assert choice.fell_back_to_local
    assert choice.path == local
    problems = assemble_startup_problems(
        degraded_issues=[],
        history_folder="",
        symbol_folder="",
        settings_choice=choice,
        migration=None,
    )
    assert len(problems) == 1
    assert problems[0].problem_id == SHARED_SETTINGS_PROBLEM_ID
    assert problems[0].title == "Shared settings are not available"
    assert str(blocked / "settings") in problems[0].folder


def test_legacy_symlink_outside_share_stays_a_leftover(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_home = _isolate(monkeypatch, tmp_path)
    target = tmp_path / "private_settings"
    target.mkdir()
    link = fake_home / constants.GLOBAL_STATE_DIRNAME
    link.symlink_to(target, target_is_directory=True)
    local = Path(os.path.abspath(str(paths.DEFAULT_PRODUCT_STATE_LAYOUT.state_root)))

    choice = state_roots.resolve_settings_root()

    assert choice.source == "local"
    assert choice.path == local
