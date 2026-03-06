"""Unit tests for editor tab manager behavior."""

import os
from pathlib import Path
import time

import pytest

from app.editors.editor_manager import EditorManager

pytestmark = pytest.mark.unit


def test_open_file_is_deduplicated_and_marks_active_tab(tmp_path: Path) -> None:
    """Opening the same path twice should reuse one tab instance."""
    file_path = tmp_path / "run.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")
    manager = EditorManager()

    first = manager.open_file(str(file_path))
    second = manager.open_file(str(file_path))

    assert first.was_already_open is False
    assert second.was_already_open is True
    assert len(manager.open_paths()) == 1
    assert manager.active_tab() is first.tab


def test_open_file_preview_marks_preview_state(tmp_path: Path) -> None:
    file_path = tmp_path / "preview.py"
    file_path.write_text("print('preview')\n", encoding="utf-8")
    manager = EditorManager()

    opened = manager.open_file(str(file_path), preview=True)

    assert opened.tab.is_preview is True
    assert manager.preview_tab() is opened.tab


def test_opening_second_preview_replaces_existing_preview(tmp_path: Path) -> None:
    first_path = tmp_path / "first.py"
    second_path = tmp_path / "second.py"
    first_path.write_text("print('first')\n", encoding="utf-8")
    second_path.write_text("print('second')\n", encoding="utf-8")
    manager = EditorManager()

    first_open = manager.open_file(str(first_path), preview=True)
    second_open = manager.open_file(str(second_path), preview=True)

    assert first_open.closed_preview_path is None
    assert second_open.closed_preview_path == str(first_path.resolve())
    assert manager.get_tab(str(first_path.resolve())) is None
    assert manager.get_tab(str(second_path.resolve())) is not None
    assert manager.preview_tab() is second_open.tab


def test_opening_existing_preview_permanently_promotes_tab(tmp_path: Path) -> None:
    file_path = tmp_path / "promote.py"
    file_path.write_text("print('promote')\n", encoding="utf-8")
    manager = EditorManager()
    manager.open_file(str(file_path), preview=True)

    reopened = manager.open_file(str(file_path), preview=False)

    assert reopened.was_already_open is True
    assert reopened.promoted_from_preview is True
    assert reopened.tab.is_preview is False
    assert manager.preview_tab() is None


def test_update_tab_content_marks_tab_dirty(tmp_path: Path) -> None:
    """Updating content should toggle dirty state."""
    file_path = tmp_path / "run.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")
    manager = EditorManager()
    opened = manager.open_file(str(file_path))

    assert opened.tab.is_dirty is False
    manager.update_tab_content(str(file_path), "print('edited')\n")
    assert opened.tab.is_dirty is True


def test_save_tab_persists_content_and_clears_dirty_state(tmp_path: Path) -> None:
    """Saving a dirty tab should write content and clear dirty flag."""
    file_path = tmp_path / "run.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")
    manager = EditorManager()
    opened = manager.open_file(str(file_path))
    manager.update_tab_content(str(file_path), "print('saved')\n")

    manager.save_tab(str(file_path))

    assert file_path.read_text(encoding="utf-8") == "print('saved')\n"
    assert opened.tab.is_dirty is False


def test_save_all_persists_only_dirty_tabs(tmp_path: Path) -> None:
    """Save all should skip clean tabs and persist modified tabs."""
    alpha_path = tmp_path / "alpha.py"
    beta_path = tmp_path / "beta.py"
    alpha_path.write_text("a=1\n", encoding="utf-8")
    beta_path.write_text("b=1\n", encoding="utf-8")
    manager = EditorManager()
    manager.open_file(str(alpha_path))
    manager.open_file(str(beta_path))
    manager.update_tab_content(str(beta_path), "b=2\n")

    saved_tabs = manager.save_all()

    assert [tab.file_path for tab in saved_tabs] == [str(beta_path.resolve())]
    assert alpha_path.read_text(encoding="utf-8") == "a=1\n"
    assert beta_path.read_text(encoding="utf-8") == "b=2\n"


def test_open_file_rejects_binary_or_non_utf8_content(tmp_path: Path) -> None:
    """Non-UTF8 file contents should raise actionable error."""
    file_path = tmp_path / "binary.bin"
    file_path.write_bytes(b"\xff\xfe\xfd")
    manager = EditorManager()

    with pytest.raises(ValueError, match="not valid UTF-8 text"):
        manager.open_file(str(file_path))


def test_remap_paths_for_move_updates_open_tabs_and_active_file(tmp_path: Path) -> None:
    """Moving paths should remap tab keys and preserve active-tab state."""
    root = tmp_path / "project"
    (root / "pkg").mkdir(parents=True)
    source = root / "pkg" / "module.py"
    source.write_text("x=1\n", encoding="utf-8")
    manager = EditorManager()
    manager.open_file(str(source))

    remapped = manager.remap_paths_for_move(str(root / "pkg"), str(root / "renamed"))

    new_path = str((root / "renamed" / "module.py").resolve())
    assert list(remapped.values()) == [new_path]
    assert manager.get_tab(new_path) is not None
    assert manager.active_tab() is manager.get_tab(new_path)


def test_remap_paths_for_move_updates_preview_tracking(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "pkg").mkdir(parents=True)
    source = root / "pkg" / "module.py"
    source.write_text("x=1\n", encoding="utf-8")
    manager = EditorManager()
    manager.open_file(str(source), preview=True)

    manager.remap_paths_for_move(str(root / "pkg"), str(root / "renamed"))

    preview = manager.preview_tab()
    assert preview is not None
    assert preview.file_path == str((root / "renamed" / "module.py").resolve())


def test_close_file_removes_tab_and_reassigns_active(tmp_path: Path) -> None:
    """Closing an active file should promote previous tab as active."""
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("a=1\n", encoding="utf-8")
    second.write_text("b=2\n", encoding="utf-8")
    manager = EditorManager()
    manager.open_file(str(first))
    manager.open_file(str(second))

    manager.close_file(str(second))

    assert manager.get_tab(str(second.resolve())) is None
    assert manager.active_tab() is manager.get_tab(str(first.resolve()))


def test_open_file_records_last_known_disk_mtime(tmp_path: Path) -> None:
    """Opening file should capture baseline disk mtime for change detection."""
    file_path = tmp_path / "mtime.py"
    file_path.write_text("value = 1\n", encoding="utf-8")
    manager = EditorManager()

    opened = manager.open_file(str(file_path))

    assert opened.tab.last_known_mtime is not None


def test_acknowledge_disk_mtime_updates_tab_snapshot(tmp_path: Path) -> None:
    """Acknowledging disk mtime should update per-tab mtime snapshot."""
    file_path = tmp_path / "snapshot.py"
    file_path.write_text("value = 1\n", encoding="utf-8")
    manager = EditorManager()
    opened = manager.open_file(str(file_path))

    manager.acknowledge_disk_mtime(str(file_path), 123.0)

    assert opened.tab.last_known_mtime == 123.0


def test_stale_open_paths_reports_disk_modified_files(tmp_path: Path) -> None:
    """Manager should detect open tabs whose disk mtime changed."""
    file_path = tmp_path / "stale.py"
    file_path.write_text("value = 1\n", encoding="utf-8")
    manager = EditorManager()
    opened = manager.open_file(str(file_path))

    assert manager.stale_open_paths() == []

    file_path.write_text("value = 2\n", encoding="utf-8")
    baseline = opened.tab.last_known_mtime or time.time()
    os.utime(file_path, (baseline + 5.0, baseline + 5.0))
    stale = manager.stale_open_paths()
    assert stale == [str(file_path.resolve())]

    manager.acknowledge_disk_mtime(str(file_path), manager.current_disk_mtime(str(file_path)))
    assert manager.stale_open_paths() == []
