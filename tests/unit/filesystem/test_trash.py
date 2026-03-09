"""Unit tests for trash backend behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from app.filesystem import trash as trash_module
from app.filesystem.trash import TrashMoveResult, move_path_to_trash

pytestmark = pytest.mark.unit


def _raise_unavailable(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    raise trash_module._TrashBackendUnavailable("unavailable")


def _raise_oserror(message: str) -> Callable[..., TrashMoveResult]:
    def _raiser(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError(message)

    return _raiser


def test_move_path_to_trash_uses_freedesktop_layout_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trash_module, "_move_with_send2trash", _raise_unavailable)
    xdg_data_home = tmp_path / "xdg_data"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))

    source = tmp_path / "project" / "report draft.txt"
    source.parent.mkdir(parents=True)
    source.write_text("content\n", encoding="utf-8")

    result = move_path_to_trash(source)

    assert result.backend == "system_freedesktop"
    assert source.exists() is False
    assert result.destination_path is not None
    destination = Path(result.destination_path)
    assert destination.exists() is True
    info_path = xdg_data_home / "Trash" / "info" / f"{destination.name}.trashinfo"
    assert info_path.exists() is True
    info_contents = info_path.read_text(encoding="utf-8")
    assert "[Trash Info]" in info_contents
    assert "DeletionDate=" in info_contents
    assert "Path=" in info_contents


def test_move_path_to_trash_uses_app_fallback_when_system_backends_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trash_module, "_move_with_send2trash", _raise_unavailable)
    monkeypatch.setattr(trash_module, "_move_with_freedesktop_trash", _raise_oserror("freedesktop unavailable"))

    source = tmp_path / "project" / "plugin_bundle"
    source.mkdir(parents=True)
    (source / "plugin.json").write_text("{}", encoding="utf-8")
    state_root = (tmp_path / "state").resolve()

    result = move_path_to_trash(source, state_root=state_root)

    assert result.backend == "app_fallback"
    assert source.exists() is False
    assert result.destination_path is not None
    destination = Path(result.destination_path)
    assert destination.exists() is True
    assert destination.parent == state_root / "trash" / "files"
    info_path = state_root / "trash" / "info" / f"{destination.name}.trashinfo"
    assert info_path.exists() is True


def test_move_path_to_trash_allocates_unique_name_on_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trash_module, "_move_with_send2trash", _raise_unavailable)
    monkeypatch.setattr(trash_module, "_move_with_freedesktop_trash", _raise_oserror("freedesktop unavailable"))
    state_root = (tmp_path / "state").resolve()

    source_one = tmp_path / "one" / "same_name.py"
    source_one.parent.mkdir(parents=True)
    source_one.write_text("print('one')\n", encoding="utf-8")
    source_two = tmp_path / "two" / "same_name.py"
    source_two.parent.mkdir(parents=True)
    source_two.write_text("print('two')\n", encoding="utf-8")

    result_one = move_path_to_trash(source_one, state_root=state_root)
    result_two = move_path_to_trash(source_two, state_root=state_root)

    assert result_one.destination_path is not None
    assert result_two.destination_path is not None
    first_name = Path(result_one.destination_path).name
    second_name = Path(result_two.destination_path).name
    assert first_name == "same_name.py"
    assert second_name == "same_name.py.1"
