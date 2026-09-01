from __future__ import annotations

from pathlib import Path

import pytest

from tools.dune.check import run

pytestmark = pytest.mark.unit


def _write_manifest(repo_root: Path) -> None:
    (repo_root / "dune.yaml").write_text(
        "owners:\n"
        "  shell:\n"
        "    - app/shell/**\n",
        encoding="utf-8",
    )


def _handles_path(repo_root: Path) -> Path:
    return (
        repo_root
        / ".cursor"
        / "skills"
        / "verify-cbcs"
        / "references"
        / "handles.md"
    )


def _write_handles(repo_root: Path, *names: str) -> None:
    path = _handles_path(repo_root)
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(f"`#{name}`" for name in names) + "\n",
        encoding="utf-8",
    )


def _write_source(repo_root: Path, source: str) -> str:
    relative_path = "app/shell/widget.py"
    path = repo_root / relative_path
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    return relative_path


def test_documented_handle_missing_from_code_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(tmp_path)
    _write_handles(tmp_path, "shell.welcome")
    relative_path = _write_source(tmp_path, "class Widget:\n    pass\n")

    exit_code = run(tmp_path, [relative_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "handles: shell.welcome is documented but has no setObjectName in app\n"
    )


def test_code_handle_missing_from_documentation_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(tmp_path)
    _write_handles(tmp_path, "shell.welcome")
    relative_path = _write_source(
        tmp_path,
        "class Widget:\n"
        "    def build(self):\n"
        '        self.setObjectName("shell.welcome")\n'
        '        self.setObjectName("shell.brandNew")\n',
    )

    exit_code = run(tmp_path, [relative_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "handles: app/shell/widget.py:4: shell.brandNew is not documented in "
        ".cursor/skills/verify-cbcs/references/handles.md\n"
    )


def test_duplicate_allowlist_growth_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(tmp_path)
    _write_handles(tmp_path, "shell.welcome.onboardingActionBtn")
    relative_path = _write_source(
        tmp_path,
        "class Widget:\n"
        "    def build(self):\n"
        + '        self.setObjectName("shell.welcome.onboardingActionBtn")\n' * 6,
    )

    exit_code = run(tmp_path, [relative_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "handles: app/shell/widget.py:8: "
        "shell.welcome.onboardingActionBtn has 6 setObjectName assignments; "
        "duplicate allowlist permits 5\n"
    )


def test_abbreviated_documented_handle_missing_from_code_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_manifest(tmp_path)
    path = _handles_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        "`#shell.findBar.nextBtn` / `prevBtn`\n",
        encoding="utf-8",
    )
    relative_path = _write_source(
        tmp_path,
        "class Widget:\n"
        "    def build(self):\n"
        '        self.setObjectName("shell.findBar.nextBtn")\n',
    )

    exit_code = run(tmp_path, [relative_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "handles: shell.findBar.prevBtn is documented but has no "
        "setObjectName in app\n"
    )
