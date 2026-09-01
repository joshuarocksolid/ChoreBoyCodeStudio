from pathlib import Path

import pytest

from tools.dune.check import run

pytestmark = pytest.mark.unit


def _write_manifest(repo_root: Path, body: str) -> None:
    (repo_root / "dune.yaml").write_text(body, encoding="utf-8")


def _plant(repo_root: Path, relative_path: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_unowned_app_file_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(
        tmp_path,
        "owners:\n"
        "  platform.core:\n"
        "    - app/core/**\n",
    )
    tracked_files = ["app/core/owned.py", "app/new/unowned.py"]
    for relative_path in tracked_files:
        _plant(tmp_path, relative_path)

    exit_code = run(tmp_path, tracked_files)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "unowned: app/new/unowned.py\n"


def test_overlapping_ownership_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(
        tmp_path,
        "owners:\n"
        "  platform.core:\n"
        "    - app/core/**\n"
        "  platform.shared:\n"
        "    - app/core/**\n",
    )
    tracked_files = ["app/core/owned_twice.py"]
    _plant(tmp_path, tracked_files[0])

    exit_code = run(tmp_path, tracked_files)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "overlap: app/core/owned_twice.py "
        "(platform.core, platform.shared)\n"
    )
