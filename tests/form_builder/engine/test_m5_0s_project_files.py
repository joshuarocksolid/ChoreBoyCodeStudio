"""The project file index: .qrc and .py files, cached by directory mtime, never outside the project."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.features.form_builder.engine.project.project_files import ProjectFileIndex

pytestmark = [pytest.mark.unit]


def _touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _age(root: Path) -> None:
    """Put every mtime well in the past so a listing counts as settled, not racy."""
    past = time.time() - 3600
    for current, directories, names in os.walk(root):
        for name in directories + names:
            os.utime(os.path.join(current, name), (past, past), follow_symlinks=False)
        os.utime(current, (past, past))


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    _touch(root / "main.py")
    _touch(root / "forms" / "resources.qrc")
    _touch(root / "forms" / "pictures" / "logo.png")
    _touch(root / "widgets" / "till_display.py")
    _touch(root / "widgets" / "notes.txt")
    _touch(root / ".hidden" / "secret.py")
    _touch(root / "forms" / ".draft.qrc")
    _touch(root / "vendor" / "lib.py")
    _touch(root / "vendor_py311" / "lib.py")
    _touch(root / "venv" / "lib.py")
    _touch(root / "tools_env" / "pyvenv.cfg")
    _touch(root / "tools_env" / "lib.py")
    _touch(root / "pkg" / "__pycache__" / "x.py")
    _age(root)
    return root


def test_lists_qrc_and_py_files_and_skips_hidden_vendor_and_venv(tmp_path: Path) -> None:
    index = ProjectFileIndex(str(_project(tmp_path)))
    assert index.files(".py") == ("main.py", "widgets/till_display.py")
    assert index.files(".qrc") == ("forms/resources.qrc",)
    with pytest.raises(ValueError):
        index.files(".png")


def test_a_second_call_lists_nothing_and_a_change_lists_only_its_directory(tmp_path: Path) -> None:
    root = _project(tmp_path)
    index = ProjectFileIndex(str(root))
    index.files(".py")
    first = index.listings
    assert first > 0
    index.files(".qrc")
    assert index.listings == first
    _touch(root / "widgets" / "extra.py")
    os.utime(root / "widgets", (time.time() - 3000, time.time() - 3000))
    assert index.files(".py") == ("main.py", "widgets/extra.py", "widgets/till_display.py")
    assert index.listings == first + 1
    (root / "widgets" / "extra.py").unlink()
    os.utime(root / "widgets", (time.time() - 2000, time.time() - 2000))
    assert index.files(".py") == ("main.py", "widgets/till_display.py")


def test_a_directory_changed_just_now_is_read_again_even_if_its_mtime_did_not_move(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    _touch(root / "a.py")
    index = ProjectFileIndex(str(root))
    assert index.files(".py") == ("a.py",)
    stamp = os.stat(root).st_mtime
    _touch(root / "b.py")
    os.utime(root, (stamp, stamp))
    assert index.files(".py") == ("a.py", "b.py")


def test_nothing_outside_the_project_is_listed_or_entered(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    _touch(outside / "stolen.py")
    _touch(outside / "stolen.qrc")
    root = _project(tmp_path)
    os.symlink(outside, root / "linked_dir")
    os.symlink(outside / "stolen.py", root / "linked_file.py")
    os.symlink(root / "main.py", root / "inside_link.py")
    index = ProjectFileIndex(str(root))
    assert index.files(".py") == ("inside_link.py", "main.py", "widgets/till_display.py")
    assert index.files(".qrc") == ("forms/resources.qrc",)
    assert index.resolve("../elsewhere/stolen.py") == ""
    assert index.resolve("widgets/till_display.py") == str(root / "widgets" / "till_display.py")
    assert ProjectFileIndex(str(tmp_path / "missing")).files(".py") == ()
