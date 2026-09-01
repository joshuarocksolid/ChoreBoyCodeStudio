from pathlib import Path

import pytest

from scripts import new_feature
from tools.dune.ownership import parse_ownership_manifest

pytestmark = pytest.mark.unit

_FEATURE_SPEC = """from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    ownership_globs: tuple[str, ...]


FEATURE_SPECS: tuple[FeatureSpec, ...] = ()


__all__ = ["FEATURE_SPECS", "FeatureSpec"]
"""
_MANIFEST = """owners:
  platform.features:
    - app/features/**
"""
_EXPECTED_PATHS = [
    "app/features/spec.py",
    "app/features/demo-feature",
    "tests/unit/features/demo-feature",
    ".cursor/skills/verify-cbcs/features/demo-feature.md",
    "dune.yaml",
]


def _repo(tmp_path: Path) -> Path:
    spec_path = tmp_path / "app" / "features" / "spec.py"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(_FEATURE_SPEC, encoding="utf-8")
    (tmp_path / "dune.yaml").write_text(_MANIFEST, encoding="utf-8")
    return tmp_path


def test_dry_run_prints_paths_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = _repo(tmp_path)

    exit_code = new_feature.run(repo_root, "demo-feature", dry_run=True)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.splitlines() == _EXPECTED_PATHS
    assert captured.err == ""
    assert (repo_root / "app" / "features" / "spec.py").read_text() == _FEATURE_SPEC
    assert (repo_root / "dune.yaml").read_text() == _MANIFEST
    assert not (repo_root / "app" / "features" / "demo-feature").exists()
    assert not (repo_root / "tests" / "unit" / "features" / "demo-feature").exists()
    assert not (
        repo_root
        / ".cursor"
        / "skills"
        / "verify-cbcs"
        / "features"
        / "demo-feature.md"
    ).exists()


def test_write_creates_feature_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = _repo(tmp_path)

    exit_code = new_feature.run(repo_root, "demo-feature", dry_run=False)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.splitlines() == _EXPECTED_PATHS
    assert captured.err == ""
    assert (repo_root / "app" / "features" / "demo-feature").is_dir()
    assert (repo_root / "tests" / "unit" / "features" / "demo-feature").is_dir()

    spec_text = (repo_root / "app" / "features" / "spec.py").read_text()
    assert 'key="demo-feature"' in spec_text
    assert 'ownership_globs=("app/features/demo-feature/**",)' in spec_text

    owners = parse_ownership_manifest((repo_root / "dune.yaml").read_text())
    assert owners["platform.features"] == [
        "app/features/__init__.py",
        "app/features/spec.py",
    ]
    assert owners["demo-feature"] == ["app/features/demo-feature/**"]

    verify_text = (
        repo_root
        / ".cursor"
        / "skills"
        / "verify-cbcs"
        / "features"
        / "demo-feature.md"
    ).read_text()
    assert verify_text.startswith("# Demo feature\n")
    assert [line for line in verify_text.splitlines() if line.startswith("## ")] == [
        "## Sub-features",
        "## How to get to it (user POV)",
        "## Driving it with control-cbcs",
        "## Gotchas",
    ]


def test_duplicate_exits_one_without_changes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = _repo(tmp_path)
    assert new_feature.run(repo_root, "demo-feature", dry_run=False) == 0
    capsys.readouterr()
    spec_path = repo_root / "app" / "features" / "spec.py"
    manifest_path = repo_root / "dune.yaml"
    verify_path = (
        repo_root
        / ".cursor"
        / "skills"
        / "verify-cbcs"
        / "features"
        / "demo-feature.md"
    )
    before = (
        spec_path.read_text(),
        manifest_path.read_text(),
        verify_path.read_text(),
    )

    exit_code = new_feature.run(repo_root, "demo-feature", dry_run=False)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "new feature error: demo-feature already exists\n"
    assert (
        spec_path.read_text(),
        manifest_path.read_text(),
        verify_path.read_text(),
    ) == before


def test_existing_spec_key_exits_one_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = _repo(tmp_path)
    spec_path = repo_root / "app" / "features" / "spec.py"
    spec_text = _FEATURE_SPEC.replace(
        "FEATURE_SPECS: tuple[FeatureSpec, ...] = ()",
        "FEATURE_SPECS: tuple[FeatureSpec, ...] = (\n"
        "    FeatureSpec('demo-feature', ('app/features/demo-feature/**',)),\n"
        ")",
    )
    spec_path.write_text(spec_text, encoding="utf-8")

    exit_code = new_feature.run(repo_root, "demo-feature", dry_run=False)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "new feature error: demo-feature already exists\n"
    assert spec_path.read_text() == spec_text
    assert not (repo_root / "app" / "features" / "demo-feature").exists()


def test_existing_owner_overlap_exits_one_without_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = _repo(tmp_path)
    manifest_path = repo_root / "dune.yaml"
    manifest_text = (
        _MANIFEST + "  legacy-feature:\n" + "    - app/features/demo-feature/**\n"
    )
    manifest_path.write_text(manifest_text, encoding="utf-8")

    exit_code = new_feature.run(repo_root, "demo-feature", dry_run=False)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "new feature error: dune.yaml owner conflict: "
        "overlap: app/features/demo-feature/__init__.py "
        "(legacy-feature, demo-feature)\n"
    )
    assert manifest_path.read_text() == manifest_text
    assert not (repo_root / "app" / "features" / "demo-feature").exists()
