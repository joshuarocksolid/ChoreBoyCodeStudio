from __future__ import annotations

import json
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
EXPECTED_PROMPT = (
    "Change an existing setting in ChoreBoy Code Studio and prove the editor "
    "remains responsive while the new setting is active."
)
EXPECTED_VERIFY_COMMAND = (
    ".cursor/skills/cbcs-quality-loop/scripts/measure-smoke "
    "--repo /Users/local/Projects/ChoreBoyCodeStudio"
)


def _load_case() -> dict[str, object]:
    return json.loads(CASE_PATH.read_text(encoding="utf-8"))


def test_case_freezes_candidate_prompt() -> None:
    assert _load_case().get("prompt") == EXPECTED_PROMPT


def test_case_freezes_verify_command() -> None:
    assert _load_case().get("verify_command") == EXPECTED_VERIFY_COMMAND


def test_candidate_prompt_does_not_disclose_eval() -> None:
    prompt = _load_case()["prompt"]

    assert isinstance(prompt, str)
    assert "eval" not in prompt.casefold()
