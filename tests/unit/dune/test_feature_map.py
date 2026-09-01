from __future__ import annotations

from pathlib import Path

import pytest

from tools.dune.check import run

pytestmark = pytest.mark.unit


def _write_file(repo_root: Path, relative_path: str, text: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_manifest(repo_root: Path) -> None:
    _write_file(
        repo_root,
        "dune.yaml",
        "owners:\n"
        "  platform.shell:\n"
        "    - app/shell/**\n",
    )


def test_feature_file_without_owner_line_fails_with_feature_map(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(tmp_path)
    _write_file(
        tmp_path,
        ".cursor/skills/verify-cbcs/features/not-a-feature.md",
        "# Not a feature\n",
    )

    exit_code = run(tmp_path, [], baseline_root=tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "feature-map: .cursor/skills/verify-cbcs/features/not-a-feature.md: "
        "missing dune owners\n"
    )


def test_feature_file_with_missing_acceptance_id_fails_with_feature_map(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(tmp_path)
    _write_file(
        tmp_path,
        ".cursor/skills/verify-cbcs/features/run.md",
        "# Run\n\n"
        "<!-- dune-owners: platform.shell -->\n\n"
        "Owns AT-999.\n",
    )
    _write_file(
        tmp_path,
        "docs/ACCEPTANCE_TESTS.md",
        "## AT-01 — Existing acceptance test\n",
    )

    exit_code = run(tmp_path, [], baseline_root=tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "feature-map: .cursor/skills/verify-cbcs/features/run.md: "
        "missing acceptance id AT-999\n"
    )


def test_shared_acceptance_id_is_legal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(tmp_path)
    for filename in ("debug.md", "test-explorer.md"):
        _write_file(
            tmp_path,
            f".cursor/skills/verify-cbcs/features/{filename}",
            f"# {filename}\n\n"
            "<!-- dune-owners: platform.shell -->\n\n"
            "Owns AT-62.\n",
        )
    _write_file(
        tmp_path,
        "docs/ACCEPTANCE_TESTS.md",
        "## AT-62 — Shared acceptance test\n",
    )

    exit_code = run(tmp_path, [], baseline_root=tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "dune check ok\n"
    assert captured.err == ""
