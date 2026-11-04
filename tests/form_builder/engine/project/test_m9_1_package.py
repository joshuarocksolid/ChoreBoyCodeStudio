"""The package list includes a form the app loads at runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.packaging.packager import package_project

_RUNTIME = frozenset({"PySide6"})


def _package(root: Path, output: Path):
    return package_project(
        project_root=str(root),
        project_name="Login",
        entry_file="main.py",
        output_dir=str(output),
        known_runtime_modules=_RUNTIME,
    )


@pytest.mark.pain("P-10")
def test_loaded_form_is_in_the_package_and_missing_fails_the_step(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "cbcs").mkdir()
    (root / "cbcs" / "project.json").write_text('{"name":"Login"}\n', encoding="utf-8")
    created = create_form(str(root), "login", OsFileSystem(), template="widget")
    assert created.refused is None
    (root / "main.py").write_text(
        "def open_form():\n"
        "    from PySide6.QtUiTools import QUiLoader\n"
        '    return QUiLoader().load("forms/login.ui")\n',
        encoding="utf-8",
    )
    shipped = _package(root, tmp_path / "exports")
    assert shipped.success, [issue.summary for issue in shipped.validation.issue_report.issues]
    manifest = json.loads(Path(shipped.manifest_path).read_text(encoding="utf-8"))
    listed = [item["relative_path"] for item in manifest["checksums"]]
    assert any(path.endswith("forms/login.ui") for path in listed)
    (root / "forms" / "login.ui").unlink()
    failed = _package(root, tmp_path / "exports-missing")
    assert failed.success is False
    missing = [
        issue
        for issue in failed.validation.issue_report.issues
        if issue.issue_id == "package.form.loaded_ui_missing"
    ]
    assert [issue.summary for issue in missing] == ["forms/login.ui is not in the package."]
    assert missing[0].is_blocking
