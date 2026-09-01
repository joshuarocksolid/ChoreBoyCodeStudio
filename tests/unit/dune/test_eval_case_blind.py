from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
CASE_PATH = (
    REPO_ROOT
    / ".cursor"
    / "skills"
    / "cbcs-quality-loop"
    / "evals"
    / "cases"
    / "01-settings-toggle-no-ui-block.json"
)


def _load_case() -> dict[str, object]:
    return json.loads(CASE_PATH.read_text(encoding="utf-8"))


def test_case_has_blinded_candidate_prompt() -> None:
    prompt = _load_case().get("prompt")

    assert isinstance(prompt, str)
    assert prompt.strip()
    assert "eval" not in prompt.casefold()


def test_case_verify_command_names_existing_repo_path() -> None:
    verify_command = _load_case().get("verify_command")

    assert isinstance(verify_command, str)
    assert verify_command.strip()

    command_path = (REPO_ROOT / shlex.split(verify_command)[0]).resolve()
    assert REPO_ROOT in command_path.parents
    assert command_path.exists()
