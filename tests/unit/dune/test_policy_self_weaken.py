from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tools.dune.check import run

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_checker_tree(repo_root: Path, manifest: str) -> None:
    dune_root = repo_root / "tools" / "dune"
    dune_root.parent.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "tools" / "dune", dune_root)
    (repo_root / "dune.yaml").write_text(manifest, encoding="utf-8")


def _write_app_file(repo_root: Path, relative_path: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _core_manifest(*, include_new: bool = False) -> str:
    manifest = (
        "owners:\n"
        "  platform.core:\n"
        "    - app/core/**\n"
    )
    if include_new:
        manifest += (
            "  platform.new:\n"
            "    - app/new/**\n"
        )
    return manifest


def test_checker_edit_with_baseline_violation_fails_policy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    _write_checker_tree(baseline_root, _core_manifest())
    _write_checker_tree(current_root, _core_manifest(include_new=True))
    checker_path = current_root / "tools" / "dune" / "ownership.py"
    checker_path.write_text(
        checker_path.read_text(encoding="utf-8")
        + '\nPOLICY_TEST_EDIT = "changed"\n',
        encoding="utf-8",
    )
    tracked_files = ["app/core/owned.py", "app/new/unowned.py"]
    for relative_path in tracked_files:
        _write_app_file(current_root, relative_path)

    exit_code = run(
        current_root,
        tracked_files,
        baseline_root=baseline_root,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "policy: judge edit would fail baseline checker: "
        "unowned: app/new/unowned.py\n"
    )


def test_checker_only_green_change_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    manifest = _core_manifest()
    _write_checker_tree(baseline_root, manifest)
    _write_checker_tree(current_root, manifest)
    checker_path = current_root / "tools" / "dune" / "ownership.py"
    checker_path.write_text(
        checker_path.read_text(encoding="utf-8")
        + '\nPOLICY_TEST_EDIT = "changed"\n',
        encoding="utf-8",
    )
    tracked_files = ["app/core/owned.py"]
    _write_app_file(current_root, tracked_files[0])

    exit_code = run(
        current_root,
        tracked_files,
        baseline_root=baseline_root,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "dune check ok\n"
    assert captured.err == ""


def test_violation_without_judge_edit_uses_existing_law(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    manifest = _core_manifest()
    _write_checker_tree(baseline_root, manifest)
    _write_checker_tree(current_root, manifest)
    tracked_files = ["app/core/owned.py", "app/new/unowned.py"]
    for relative_path in tracked_files:
        _write_app_file(current_root, relative_path)

    exit_code = run(
        current_root,
        tracked_files,
        baseline_root=baseline_root,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "unowned: app/new/unowned.py\n"


def test_budget_edit_with_baseline_violation_fails_policy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    manifest = _core_manifest()
    _write_checker_tree(baseline_root, manifest)
    _write_checker_tree(current_root, manifest)
    baseline_budget = baseline_root / "package.py"
    current_budget = current_root / "package.py"
    baseline_budget.write_text(
        "ARCHIVE_BUDGET_BYTES = 15 * 1024\n",
        encoding="utf-8",
    )
    current_budget.write_text(
        "ARCHIVE_BUDGET_BYTES = 16 * 1024\n",
        encoding="utf-8",
    )
    tracked_files = ["app/core/owned.py", "app/new/unowned.py"]
    for relative_path in tracked_files:
        _write_app_file(current_root, relative_path)

    exit_code = run(
        current_root,
        tracked_files,
        baseline_root=baseline_root,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "unowned: app/new/unowned.py\n"
        "policy: judge edit would fail baseline checker: "
        "unowned: app/new/unowned.py\n"
    )


def test_checker_edit_fails_closed_when_baseline_cannot_load(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    baseline_root.mkdir()
    _write_checker_tree(current_root, _core_manifest())
    checker_path = current_root / "tools" / "dune" / "ownership.py"
    checker_path.write_text(
        checker_path.read_text(encoding="utf-8")
        + '\nPOLICY_TEST_EDIT = "changed"\n',
        encoding="utf-8",
    )
    tracked_files = ["app/core/owned.py"]
    _write_app_file(current_root, tracked_files[0])

    exit_code = run(
        current_root,
        tracked_files,
        baseline_root=baseline_root,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "policy: cannot load baseline checker: "
        "baseline tools/dune/check.py is missing\n"
    )


def test_checker_tree_without_git_or_explicit_baseline_fails_policy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_checker_tree(tmp_path, _core_manifest())
    tracked_files = ["app/core/owned.py"]
    _write_app_file(tmp_path, tracked_files[0])

    exit_code = run(tmp_path, tracked_files)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.startswith(
        "policy: cannot load baseline checker: git diff "
    )


def test_current_checker_error_does_not_suppress_policy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    _write_checker_tree(baseline_root, _core_manifest())
    _write_checker_tree(current_root, "invalid\n")
    checker_path = current_root / "tools" / "dune" / "ownership.py"
    checker_path.write_text(
        checker_path.read_text(encoding="utf-8")
        + '\nPOLICY_TEST_EDIT = "changed"\n',
        encoding="utf-8",
    )
    tracked_files = ["app/core/owned.py", "app/new/unowned.py"]
    for relative_path in tracked_files:
        _write_app_file(current_root, relative_path)

    exit_code = run(
        current_root,
        tracked_files,
        baseline_root=baseline_root,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "dune check error: line 1: expected owners:\n"
        "policy: judge edit would fail baseline checker: "
        "unowned: app/new/unowned.py\n"
    )


def test_handles_law_and_checker_cannot_hide_removed_object_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_root = tmp_path / "baseline"
    current_root = tmp_path / "current"
    manifest = (
        "owners:\n"
        "  shell:\n"
        "    - app/shell/**\n"
    )
    _write_checker_tree(baseline_root, manifest)
    _write_checker_tree(current_root, manifest)

    relative_app_path = "app/shell/welcome_widget.py"
    app_source = (
        "class WelcomeWidget:\n"
        "    def configure(self) -> None:\n"
        '        self.setObjectName("shell.welcome")\n'
        "        pass\n"
    )
    for root in (baseline_root, current_root):
        app_path = root / relative_app_path
        app_path.parent.mkdir(parents=True)
        app_path.write_text(app_source, encoding="utf-8")
        handles_path = (
            root
            / ".cursor"
            / "skills"
            / "verify-cbcs"
            / "references"
            / "handles.md"
        )
        handles_path.parent.mkdir(parents=True)
        handles_path.write_text(
            "| Handle | What |\n"
            "| --- | --- |\n"
            "| `#shell.welcome` | Welcome pane |\n",
            encoding="utf-8",
        )

    checker_path = current_root / "tools" / "dune" / "check.py"
    checker_source = checker_path.read_text(encoding="utf-8")
    weakened_checker = checker_source.replace(
        "        violations.extend(find_handle_violations(repo_root, app_files))\n",
        "",
    )
    assert weakened_checker != checker_source
    checker_path.write_text(weakened_checker, encoding="utf-8")

    app_path = current_root / relative_app_path
    app_path.write_text(
        app_source.replace(
            '        self.setObjectName("shell.welcome")\n',
            "",
        ),
        encoding="utf-8",
    )
    handles_path = (
        current_root
        / ".cursor"
        / "skills"
        / "verify-cbcs"
        / "references"
        / "handles.md"
    )
    handles_path.write_text(
        handles_path.read_text(encoding="utf-8").replace(
            "| `#shell.welcome` | Welcome pane |\n",
            "",
        ),
        encoding="utf-8",
    )

    exit_code = run(
        current_root,
        [relative_app_path],
        baseline_root=baseline_root,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "policy: judge edit would fail baseline checker: "
        "handles: shell.welcome is documented but has no setObjectName in app\n"
    )
