"""Backend switch for control-cbcs. No farm or lab calls."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / ".cursor/skills/verify-cbcs/scripts"
sys.path.insert(0, str(SCRIPTS))

import farm_backend  # noqa: E402

pytestmark = pytest.mark.unit


def test_default_backend_is_farm():
    backend, argv = farm_backend.resolve_backend(["launch", "--source"], {})
    assert backend == "farm"
    assert argv == ["launch", "--source"]


def test_backend_flag_wins_over_env_in_any_position():
    backend, argv = farm_backend.resolve_backend(
        ["doctor", "sid", "--backend", "lab"],
        {"CBCS_VERIFY_BACKEND": "farm"},
    )
    assert backend == "lab"
    assert argv == ["doctor", "sid"]


def test_unknown_backend_is_refused():
    with pytest.raises(SystemExit):
        farm_backend.resolve_backend(["--backend", "mac"], {})


def test_held_env_is_not_a_new_lease():
    assert farm_backend.holds_farm_env({"CBFARM_ENV": "e5xj"}) is True
    assert farm_backend.holds_farm_env({}) is False
    assert farm_backend.holds_farm_env({"CBFARM_ENV": "  "}) is False


def test_ctl_payload_does_not_set_timeout(monkeypatch):
    monkeypatch.setenv("CBFARM_ENV", "e5xj")
    monkeypatch.delenv("CBFARM_MACHINE", raising=False)
    payload = farm_backend.do_payload(
        ["ctl", "cbcs-verify-1", "screenshot", "--target", "app", "--out", "welcome"],
        timeout=90,
    )
    assert payload["env"] == "e5xj"
    assert payload["machine"] == "net1"
    assert payload["verb"] == "ctl"
    assert payload["args"][0] == "cbcs-verify-1"
    assert "timeout_s" not in payload
    assert os.environ["CBFARM_ENV"] == "e5xj"


def test_launch_sid_keeps_the_suffix_cbapp_appends():
    text = (
        "cbcs-verify-20261104Tfarmproof-20261104T180009Z-d569b5\n"
        "[stderr]\nstate: running\n"
    )
    assert (
        farm_backend.launch_sid(text, "cbcs-verify-20261104Tfarmproof")
        == "cbcs-verify-20261104Tfarmproof-20261104T180009Z-d569b5"
    )


def test_app_run_payload_carries_timeout(monkeypatch):
    monkeypatch.setenv("CBFARM_ENV", "e5xj")
    payload = farm_backend.do_payload(
        ["app-run", "/mnt/cbprobe/incoming/demo/run_editor.py", "--wait-ready", "90"],
        timeout=180,
    )
    assert payload["verb"] == "app"
    assert payload["args"][0] == "app-run"
    assert payload["timeout_s"] == 180
