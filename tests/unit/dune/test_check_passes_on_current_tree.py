from pathlib import Path

import pytest

from tools.dune.check import run

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_check_passes_on_current_tree(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run(REPO_ROOT)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "dune check ok\n"
    assert captured.err == ""
